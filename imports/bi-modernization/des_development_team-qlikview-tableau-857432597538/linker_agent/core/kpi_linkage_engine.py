"""
Enhanced KPI Linkage System - Semantic Matching Approach
Uses LLM-based semantic understanding instead of pure fuzzy matching
"""

from linker_agent.utils.llm_factory import get_azure_chat_client
from linker_agent.utils.logger import configure_logger
from linker_agent.models.data_schema import DataSchema
from linker_agent.models.kpi import KPI
from typing import List, Dict, Optional, Tuple, Any, Set
from linker_agent.config import CACHE_DIR
from pydantic import BaseModel, Field
from uuid import UUID, uuid5, NAMESPACE_OID
import json
from pathlib import Path
from datetime import datetime
import asyncio
from tqdm import tqdm
import time
from collections import defaultdict
import re

logger = configure_logger(__file__)


# ============================================================================
# DATA MODELS
# ============================================================================

class LinkedAttr(BaseModel):
    table_name: str
    table_id: UUID
    attribute_name: str
    attribute_description: str
    attribute_datatype: str
    confidence_score: float = Field(ge=0, le=100)
    matched_kpi_component: str
    matching_rationale: str = ""


class KPIDependency(BaseModel):
    dependent_kpi_id: UUID
    dependent_kpi_name: str
    dependency_type: str
    required_for_component: str


class LinkedKPI(BaseModel):
    kpi_id: UUID
    kpi_name: str
    kpi_definition: str
    kpi_formula: str
    is_able_to_generate: bool
    attribute_mappings: List[LinkedAttr] = Field(default_factory=list)
    missing_attributes: List[str] = Field(default_factory=list)
    kpi_dependencies: List[KPIDependency] = Field(default_factory=list)
    missing_kpi_dependencies: List[str] = Field(default_factory=list)
    linkage_notes: str = Field(default="")
    linkage_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class LinkageResult(BaseModel):
    linked_kpis: List[LinkedKPI]
    summary: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# RATE LIMITER
# ============================================================================

class AdaptiveRateLimiter:
    def __init__(self, calls_per_minute: int = 120, burst_size: int = 30):
        self.calls_per_minute = calls_per_minute
        self.burst_size = burst_size
        self.tokens = burst_size
        self.last_update = time.time()
        self.lock = asyncio.Lock()
        self.consecutive_errors = 0
        self.backoff_multiplier = 1.0
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        
    async def acquire(self):
        async with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst_size, self.tokens + elapsed * (self.calls_per_minute / 60.0))
            self.last_update = now
            
            if self.tokens < 1:
                wait_time = (1 - self.tokens) * (60.0 / self.calls_per_minute) * self.backoff_multiplier
                await asyncio.sleep(wait_time)
                self.tokens = 1
            
            self.tokens -= 1
            self.total_calls += 1
    
    def record_success(self):
        self.consecutive_errors = 0
        self.successful_calls += 1
        self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.9)
    
    def record_error(self):
        self.consecutive_errors += 1
        self.failed_calls += 1
        self.backoff_multiplier = min(5.0, self.backoff_multiplier * 1.5)
    
    def get_health(self):
        success_rate = (self.successful_calls / self.total_calls * 100) if self.total_calls > 0 else 0
        return {
            "total_calls": self.total_calls,
            "successful": self.successful_calls,
            "failed": self.failed_calls,
            "success_rate": round(success_rate, 2),
            "backoff_multiplier": round(self.backoff_multiplier, 2)
        }


# ============================================================================
# CACHING
# ============================================================================

def get_cache_path(cache_name: str) -> Path:
    cache_dir = Path(CACHE_DIR) / "linkage"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_name}.json"


def load_from_cache(cache_name: str) -> Optional[LinkageResult]:
    cache_path = get_cache_path(cache_name)
    if cache_path.exists():
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            logger.info(f"✓ Loaded from cache: {cache_name}")
            return LinkageResult(**data)
        except Exception as e:
            logger.warning(f"Cache load failed: {e}")
    return None


def save_to_cache(cache_name: str, result: LinkageResult):
    try:
        with open(get_cache_path(cache_name), 'w') as f:
            json.dump(result.model_dump(mode='json'), f, indent=2, default=str)
        logger.info(f"✓ Saved to cache: {cache_name}")
    except Exception as e:
        logger.error(f"Cache save failed: {e}")


def save_stage_cache(stage: str, data: Any, cache_name: str):
    try:
        with open(get_cache_path(f"{cache_name}_{stage}"), 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Stage cache save failed: {e}")


def load_stage_cache(stage: str, cache_name: str) -> Optional[Any]:
    cache_path = get_cache_path(f"{cache_name}_{stage}")
    if cache_path.exists():
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Stage cache load failed: {e}")
    return None


# ============================================================================
# SCHEMA INDEXING
# ============================================================================

class SchemaIndex:
    def __init__(self, data_schema: DataSchema):
        self.data_schema = data_schema
        self._table_index = {}
        self._keyword_index = defaultdict(set)
        self._build_indices()
    
    def _build_indices(self):
        logger.info("Building schema indices...")
        for table in self.data_schema.tables:
            self._table_index[table.table_name.lower()] = {
                "table_name": table.table_name,
                "table_id": str(table.id),
                "description": table.description or "",
                "attributes": [
                    {"name": a.name, "description": a.description or "", "data_type": a.data_type}
                    for a in table.attributes
                ]
            }
            
            keywords = self._extract_keywords(f"{table.table_name} {table.description or ''}")
            for kw in keywords:
                self._keyword_index[kw].add(table.table_name)
        
        logger.info(f"✓ Indexed {len(self._table_index)} tables")
    
    def _extract_keywords(self, text: str) -> Set[str]:
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with'}
        words = text.lower().split()
        return {w for w in words if len(w) > 3 and w not in stopwords}
    
    def find_relevant_tables(self, kpi: KPI, top_k: int = 15) -> List[Dict]:
        """Find tables relevant to KPI - increased to 15 for better coverage"""
        kpi_keywords = self._extract_keywords(f"{kpi.name} {kpi.formula} {kpi.category}")
        
        table_scores = defaultdict(float)
        for keyword in kpi_keywords:
            if keyword in self._keyword_index:
                for table_name in self._keyword_index[keyword]:
                    table_scores[table_name] += 1.0
        
        sorted_tables = sorted(table_scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for table_name, score in sorted_tables[:top_k]:
            if table_name.lower() in self._table_index:
                info = self._table_index[table_name.lower()].copy()
                info['relevance_score'] = score
                results.append(info)
        
        # Fill remaining slots with any tables (guard against fewer tables than top_k)
        for table_info in list(self._table_index.values()):
            if len(results) >= top_k:
                break
            if not any(r['table_name'] == table_info['table_name'] for r in results):
                info = table_info.copy()
                info['relevance_score'] = 0
                results.append(info)
        
        return results[:top_k]
    
    def get_table_by_id(self, table_id: UUID) -> Optional[Dict]:
        for info in self._table_index.values():
            if info['table_id'] == str(table_id):
                return info
        return None


# ============================================================================
# LLM UTILITIES
# ============================================================================

async def safe_llm_call(agent_func, prompt: str, rate_limiter: AdaptiveRateLimiter, name: str, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            await rate_limiter.acquire()
            response = await agent_func(prompt)
            text = response.text if hasattr(response, 'text') else str(response)
            rate_limiter.record_success()
            return text
        except Exception as e:
            rate_limiter.record_error()
            if attempt < retries - 1:
                await asyncio.sleep((2 ** attempt) * rate_limiter.backoff_multiplier)
            else:
                logger.error(f"{name} failed: {e}")
    return None


def parse_json(response: str) -> Optional[Dict]:
    if not response:
        return None
    
    # Try direct parsing
    try:
        return json.loads(response.strip())
    except:
        pass
    
    # Try extracting from markdown
    for marker in ['```json', '```']:
        if marker in response:
            try:
                parts = response.split(marker)
                if len(parts) >= 2:
                    return json.loads(parts[1].split('```')[0].strip())
            except:
                continue
    
    # Try regex extraction
    matches = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
    for match in reversed(matches):
        try:
            parsed = json.loads(match)
            if isinstance(parsed, dict):
                return parsed
        except:
            continue
    
    return None


# ============================================================================
# SEMANTIC MATCHING APPROACH
# ============================================================================

async def semantic_attribute_mapping(
    kpi: KPI,
    schema_index: SchemaIndex,
    selected_tables: List[Dict],
    model,
    rate_limiter: AdaptiveRateLimiter
) -> Tuple[List[LinkedAttr], List[str]]:
    """
    NEW APPROACH: Use LLM to semantically understand KPI and match to schema
    Instead of fuzzy string matching, we let the LLM understand the meaning
    """
    
    # Extract components from formula
    components = []
    if kpi.formula_components:
        components = kpi.formula_components
    else:
        # Fallback: extract from formula
        pattern = r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
        components.extend(re.findall(pattern, kpi.formula))
        
        # Also get identifiers
        pattern2 = r'\b[A-Za-z_][A-Za-z0-9_]{2,}\b'
        stopwords = {'sum', 'avg', 'count', 'max', 'min', 'total', 'value', 'and', 'or'}
        for match in re.findall(pattern2, kpi.formula):
            if match.lower() not in stopwords and match not in components:
                components.append(match)
    
    if not components:
        return [], []
    
    # Prepare schema information for LLM
    schema_context = []
    for table in selected_tables:
        table_attrs = []
        for attr in table['attributes'][:20]:  # Limit attributes per table
            table_attrs.append({
                "name": attr['name'],
                "type": attr['data_type'],
                "description": attr['description'][:100] if attr['description'] else ""
            })
        
        schema_context.append({
            "table": table['table_name'],
            "table_id": table['table_id'],
            "description": table['description'][:150] if table['description'] else "",
            "attributes": table_attrs
        })
    
    # Create semantic matching prompt
    prompt = f"""You are a data mapping expert specializing in financial KPIs and Basel III regulations.

**TASK**: Map KPI formula components to database schema attributes using semantic understanding.

**KPI INFORMATION**:
- Name: {kpi.name}
- Definition: {kpi.definition}
- Formula: {kpi.formula}
- Category: {kpi.category}
- Components to Map: {json.dumps(components)}

**AVAILABLE DATABASE SCHEMA**:
{json.dumps(schema_context, indent=2)}

**MAPPING RULES**:
1. Match components based on MEANING, not just name similarity
2. Consider financial domain knowledge (e.g., "Replacement Cost" relates to derivative valuation)
3. For compound terms like "Replacement Cost", find attributes that represent the complete concept
4. Consider data types - numerical components need numeric attributes
5. If multiple attributes could match, choose the most semantically appropriate
6. Confidence score 0-100 based on match quality
7. If no good match exists, mark as unmapped

**EXAMPLES OF GOOD MATCHING**:
- "Alpha" → "alpha_multiplier" or "alpha_factor" (confidence: 90)
- "Replacement Cost" → "replacement_cost_amount" (confidence: 95)
- "Aggregate Add-on" → "aggregate_addon_value" (confidence: 85)
- "Net Interest Income" → "net_interest_income" or "nii" (confidence: 90)

**OUTPUT FORMAT** (JSON only, no markdown):
{{
  "mappings": [
    {{
      "component": "Alpha",
      "mapped": true,
      "table": "Risk Exposure Time Series",
      "table_id": "823b2e62-5490-48c3-b93f-08dfb4d25455",
      "attribute": "alpha_multiplier",
      "confidence": 90,
      "rationale": "Alpha multiplier used in exposure calculations"
    }},
    {{
      "component": "Replacement Cost",
      "mapped": false,
      "confidence": 0,
      "rationale": "No attribute found representing complete replacement cost concept"
    }}
  ]
}}

Return ONLY the JSON object. No explanations, no markdown formatting."""

    agent = model.create_agent(
        name="semantic_mapper",
        instructions="You are a precise data mapping expert. Output only valid JSON."
    )
    
    response = await safe_llm_call(lambda p: agent.run(p), prompt, rate_limiter, f"SemanticMap-{kpi.name}")
    
    logger.info("="*80)
    logger.info(f"Semantic mapping for: {kpi.name}")
    logger.info(f"Components: {components}")
    logger.info(f"Response: {response[:800] if response else 'None'}")
    logger.info("="*80)
    
    validated = []
    missing = []
    
    if response:
        result = parse_json(response)
        if result and "mappings" in result:
            for mapping in result['mappings']:
                component = mapping.get('component', '')
                
                if mapping.get('mapped') and mapping.get('confidence', 0) >= 60:
                    # Find table info
                    table_id = UUID(mapping['table_id'])
                    table_info = schema_index.get_table_by_id(table_id)
                    
                    if table_info:
                        # Find attribute details
                        attr_name = mapping['attribute']
                        attr_details = next(
                            (a for a in table_info['attributes'] if a['name'] == attr_name),
                            None
                        )
                        
                        if attr_details:
                            validated.append(LinkedAttr(
                                table_name=mapping['table'],
                                table_id=table_id,
                                attribute_name=attr_name,
                                attribute_description=attr_details['description'],
                                attribute_datatype=attr_details['data_type'],
                                confidence_score=float(mapping['confidence']),
                                matched_kpi_component=component,
                                matching_rationale=mapping.get('rationale', '')[:200]
                            ))
                        else:
                            missing.append(component)
                    else:
                        missing.append(component)
                else:
                    missing.append(component)
        else:
            # Failed to parse - all components missing
            missing = components
    else:
        # No response - all components missing
        missing = components
    
    return validated, missing


# ============================================================================
# BATCH PROCESSING
# ============================================================================

async def process_kpi_batch(
    batch: List[KPI],
    schema_index: SchemaIndex,
    table_selections: Dict[str, List[Dict]],
    model,
    rate_limiter: AdaptiveRateLimiter
) -> List[LinkedKPI]:
    
    tasks = [
        semantic_attribute_mapping(
            kpi,
            schema_index,
            table_selections.get(kpi.name, []),
            model,
            rate_limiter
        )
        for kpi in batch
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    linked_kpis = []
    for i, result in enumerate(results):
        kpi = batch[i]
        if isinstance(result, Exception):
            logger.error(f"Error processing {kpi.name}: {result}")
            linked_kpis.append(LinkedKPI(
                kpi_id=uuid5(NAMESPACE_OID, kpi.name),
                kpi_name=kpi.name,
                kpi_definition=kpi.definition,
                kpi_formula=kpi.formula,
                is_able_to_generate=False,
                linkage_notes=f"Error: {str(result)[:100]}"
            ))
        else:
            mappings, missing = result
            linked_kpis.append(LinkedKPI(
                kpi_id=uuid5(NAMESPACE_OID, kpi.name),
                kpi_name=kpi.name,
                kpi_definition=kpi.definition,
                kpi_formula=kpi.formula,
                is_able_to_generate=len(missing) == 0,
                attribute_mappings=mappings,
                missing_attributes=missing,
                linkage_notes=f"Mapped {len(mappings)}/{len(mappings) + len(missing)} components"
            ))
    
    return linked_kpis


async def stage1_linkage(
    kpis: List[KPI],
    schema_index: SchemaIndex,
    model,
    rate_limiter: AdaptiveRateLimiter,
    cache_name: str,
    batch_size: int = 20  # Smaller batches for semantic approach
) -> Dict[UUID, LinkedKPI]:
    
    logger.info(f"[STAGE 1] Semantic attribute linkage for {len(kpis)} KPIs")
    
    cached = load_stage_cache("stage1_semantic", cache_name)
    if cached:
        logger.info("✓ Loaded Stage 1 from cache")
        return {UUID(k): LinkedKPI(**v) for k, v in cached.items()}
    
    logger.info("Selecting relevant tables...")
    table_selections = {}
    for kpi in tqdm(kpis, desc="Table selection"):
        table_selections[kpi.name] = schema_index.find_relevant_tables(kpi, top_k=15)
    
    logger.info("Performing semantic mapping...")
    linked_kpis = {}
    
    for i in tqdm(range(0, len(kpis), batch_size), desc="Processing batches"):
        batch = kpis[i:i+batch_size]
        batch_results = await process_kpi_batch(
            batch,
            schema_index,
            table_selections,
            model,
            rate_limiter
        )
        for kpi in batch_results:
            linked_kpis[kpi.kpi_id] = kpi
        
        # Small delay between batches
        await asyncio.sleep(0.5)
    
    save_stage_cache("stage1_semantic", {str(k): v.model_dump(mode='json') for k, v in linked_kpis.items()}, cache_name)
    
    fully = sum(1 for kpi in linked_kpis.values() if kpi.is_able_to_generate)
    logger.info(f"✓ Stage 1: {fully}/{len(linked_kpis)} KPIs fully mapped")
    
    return linked_kpis


# ============================================================================
# STAGE 2: DEPENDENCIES
# ============================================================================

async def analyze_dependencies(
    batch: List[Tuple[UUID, LinkedKPI]],
    all_kpis: Dict[UUID, LinkedKPI],
    model,
    rate_limiter: AdaptiveRateLimiter
) -> List[Tuple[UUID, List[KPIDependency], List[str]]]:
    
    if not batch:
        return []
    
    current = [{"name": kpi.kpi_name, "formula": kpi.kpi_formula[:200], "missing": kpi.missing_attributes[:5]} for _, kpi in batch]
    available = [{"name": kpi.kpi_name, "formula": kpi.kpi_formula[:120]} for kpi in list(all_kpis.values())[:200]]
    
    prompt = f"""Analyze KPI dependencies for Basel III risk calculations.

Current KPIs: {json.dumps(current, indent=2)}
Available KPIs (sample): {json.dumps(available, indent=2)}

Identify which KPIs depend on other KPIs. For example:
- RWA calculations often depend on exposure and risk weight KPIs
- Leverage ratios depend on capital and exposure KPIs

Output JSON only:
{{
  "dependencies": {{
    "KPI_NAME": [{{"kpi": "dependent_kpi_name", "type": "input|intermediate|prerequisite", "reason": "brief explanation"}}]
  }}
}}"""
    
    agent = model.create_agent(name="dep_analyzer", instructions="Output only JSON.")
    response = await safe_llm_call(lambda p: agent.run(p), prompt, rate_limiter, "Dependencies")
    
    if not response:
        return [(kpi_id, [], []) for kpi_id, _ in batch]
    
    result = parse_json(response)
    if not result or "dependencies" not in result:
        return [(kpi_id, [], []) for kpi_id, _ in batch]
    
    kpi_index = {kpi.kpi_name.lower(): (kpi_id, kpi) for kpi_id, kpi in all_kpis.items()}
    dep_dict = result["dependencies"]
    results = []
    
    for kpi_id, kpi in batch:
        dependencies = []
        missing = []
        
        if kpi.kpi_name in dep_dict:
            for dep_info in dep_dict[kpi.kpi_name]:
                dep_name = dep_info.get('kpi', '').lower()
                if dep_name in kpi_index:
                    dep_id, dep_kpi = kpi_index[dep_name]
                    dependencies.append(KPIDependency(
                        dependent_kpi_id=dep_id,
                        dependent_kpi_name=dep_kpi.kpi_name,
                        dependency_type=dep_info.get('type', 'prerequisite'),
                        required_for_component=dep_info.get('reason', '')[:100]
                    ))
                else:
                    missing.append(dep_info.get('kpi', ''))
        
        results.append((kpi_id, dependencies, missing))
    
    return results


async def stage2_dependencies(
    linked_kpis: Dict[UUID, LinkedKPI],
    model,
    rate_limiter: AdaptiveRateLimiter,
    cache_name: str
) -> Dict[UUID, LinkedKPI]:
    
    logger.info(f"[STAGE 2] Dependency analysis for {len(linked_kpis)} KPIs")
    
    cached = load_stage_cache("stage2", cache_name)
    if cached:
        for kpi_id_str, dep_data in cached.items():
            kpi_id = UUID(kpi_id_str)
            if kpi_id in linked_kpis:
                linked_kpis[kpi_id].kpi_dependencies = [KPIDependency(**d) for d in dep_data['dependencies']]
                linked_kpis[kpi_id].missing_kpi_dependencies = dep_data['missing']
                if dep_data['missing']:
                    linked_kpis[kpi_id].is_able_to_generate = False
        return linked_kpis
    
    batch_size = 20
    kpi_items = list(linked_kpis.items())
    dep_cache = {}
    
    for i in tqdm(range(0, len(kpi_items), batch_size), desc="Analyzing deps"):
        batch = kpi_items[i:i+batch_size]
        try:
            results = await analyze_dependencies(batch, linked_kpis, model, rate_limiter)
            for kpi_id, dependencies, missing in results:
                linked_kpis[kpi_id].kpi_dependencies = dependencies
                linked_kpis[kpi_id].missing_kpi_dependencies = missing
                if missing:
                    linked_kpis[kpi_id].is_able_to_generate = False
                dep_cache[str(kpi_id)] = {
                    'dependencies': [d.model_dump(mode='json') for d in dependencies],
                    'missing': missing
                }
        except Exception as e:
            logger.error(f"Batch failed: {e}")
    
    save_stage_cache("stage2", dep_cache, cache_name)
    
    with_deps = sum(1 for kpi in linked_kpis.values() if kpi.kpi_dependencies)
    logger.info(f"✓ Stage 2: {with_deps} KPIs have dependencies")
    
    return linked_kpis


# ============================================================================
# MAIN PROCESSING
# ============================================================================

async def process_linkage(
    data_schema: DataSchema,
    kpis: List[KPI],
    use_cache: bool = True,
    cache_name: str = "linkage_semantic_v1",
    calls_per_minute: int = 100,  # Slightly lower for semantic approach
    burst_size: int = 25,
    parallel_batch_size: int = 20
) -> LinkageResult:
    """
    Process KPI linkage using semantic understanding approach
    
    NEW: Uses LLM to understand meaning instead of fuzzy string matching
    Better for complex financial terms and Basel III terminology
    """
    
    logger.info("=" * 80)
    logger.info(f"KPI SEMANTIC LINKAGE: {len(kpis)} KPIs × {len(data_schema.tables)} tables")
    logger.info(f"Approach: LLM-based semantic matching")
    logger.info(f"Rate: {calls_per_minute}/min | Burst: {burst_size} | Parallel: {parallel_batch_size}")
    logger.info("=" * 80)
    
    if use_cache:
        cached = load_from_cache(cache_name)
        if cached:
            logger.info("✓ Loaded complete result from cache")
            return cached
    
    model = get_azure_chat_client()
    rate_limiter = AdaptiveRateLimiter(calls_per_minute, burst_size)
    schema_index = SchemaIndex(data_schema)
    
    start = time.time()
    
    logger.info("\n[STAGE 1] SEMANTIC ATTRIBUTE MAPPING")
    linked_kpis_dict = await stage1_linkage(
        kpis,
        schema_index,
        model,
        rate_limiter,
        cache_name,
        parallel_batch_size
    )
    
    logger.info("\n[STAGE 2] KPI DEPENDENCY ANALYSIS")
    linked_kpis_dict = await stage2_dependencies(
        linked_kpis_dict,
        model,
        rate_limiter,
        cache_name
    )
    
    linked_kpis_list = list(linked_kpis_dict.values())
    
    # Calculate statistics
    total_mapped = sum(len(kpi.attribute_mappings) for kpi in linked_kpis_list)
    total_missing = sum(len(kpi.missing_attributes) for kpi in linked_kpis_list)
    
    kpis_with_mappings = [kpi for kpi in linked_kpis_list if kpi.attribute_mappings]
    avg_confidence = (
        sum(sum(a.confidence_score for a in kpi.attribute_mappings) / len(kpi.attribute_mappings) for kpi in kpis_with_mappings) / len(kpis_with_mappings)
        if kpis_with_mappings else 0
    )
    
    fully = sum(1 for kpi in linked_kpis_list if kpi.is_able_to_generate)
    partial = sum(1 for kpi in linked_kpis_list if not kpi.is_able_to_generate and kpi.attribute_mappings)
    not_linked = sum(1 for kpi in linked_kpis_list if not kpi.attribute_mappings)
    
    health = rate_limiter.get_health()
    
    summary = {
        "total_kpis": len(linked_kpis_list),
        "total_tables": len(data_schema.tables),
        "approach": "semantic_matching",
        "fully_linked": fully,
        "partially_linked": partial,
        "not_linked": not_linked,
        "total_attribute_mappings": total_mapped,
        "total_missing_attributes": total_missing,
        "total_dependencies": sum(len(kpi.kpi_dependencies) for kpi in linked_kpis_list),
        "kpis_with_dependencies": sum(1 for kpi in linked_kpis_list if kpi.kpi_dependencies),
        "avg_confidence_score": round(avg_confidence, 2),
        "processing_time_seconds": round(time.time() - start, 1),
        "processing_time_minutes": round((time.time() - start) / 60, 2),
        "api_calls_total": health['total_calls'],
        "api_calls_successful": health['successful'],
        "api_success_rate": health['success_rate'],
        "timestamp": datetime.utcnow().isoformat()
    }
    
    result = LinkageResult(linked_kpis=linked_kpis_list, summary=summary)
    
    if use_cache:
        save_to_cache(cache_name, result)
    
    logger.info("\n" + "=" * 80)
    logger.info("SEMANTIC LINKAGE COMPLETE!")
    logger.info("=" * 80)
    logger.info(f"Total KPIs: {summary['total_kpis']}")
    logger.info(f"Fully linked: {fully} ({fully/len(linked_kpis_list)*100:.1f}%)")
    logger.info(f"Partially linked: {partial} ({partial/len(linked_kpis_list)*100:.1f}%)")
    logger.info(f"Not linked: {not_linked} ({not_linked/len(linked_kpis_list)*100:.1f}%)")
    logger.info(f"Attribute mappings: {total_mapped}")
    logger.info(f"Dependencies: {summary['total_dependencies']}")
    logger.info(f"Avg confidence: {summary['avg_confidence_score']}%")
    logger.info(f"Processing time: {summary['processing_time_minutes']} min")
    logger.info(f"API calls: {summary['api_calls_total']} ({summary['api_success_rate']}% success)")
    logger.info("=" * 80)
    
    return result