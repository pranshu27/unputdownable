import pandas as pd
from pydantic import BaseModel, Field
from typing import List, Optional
from uuid import UUID, uuid4
from pathlib import Path
import json
from linker_agent.config import CACHE_DIR
from linker_agent.utils.llm_factory import get_azure_chat_client
from linker_agent.utils.logger import configure_logger


logger = configure_logger(__file__)


class Attribute(BaseModel):
    name: str
    description: str
    data_type: str
    key_type: Optional[str] = None  # "Primary", "Foreign", or None
    

class Table(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    table_name: str
    description: str
    attributes: List[Attribute]


class DataSchema(BaseModel):
    tables: List[Table]
    
    def to_dict(self):
        return {
            "tables": [
                {
                    "id": str(table.id),
                    "table_name": table.table_name,
                    "description": table.description,
                    "attributes": [
                        {
                            "name": attr.name,
                            "description": attr.description,
                            "data_type": attr.data_type,
                            "key_type": attr.key_type
                        }
                        for attr in table.attributes
                    ]
                }
                for table in self.tables
            ]
        }


async def process_data_schema(
    data_source: str = "./asserts/data_schema.csv",
    use_cache: bool = True
) -> DataSchema:
    """
    Process data schema from CSV file and optionally enhance with LLM.
    
    Args:
        data_source: Path to the CSV file
        use_cache: Whether to use cached results
        
    Returns:
        DataSchema object containing all tables and attributes
    """
    logger.info(f"Starting data schema processing from: {data_source}")
    logger.info(f"Cache enabled: {use_cache}")
    
    cache_file = Path(CACHE_DIR) / "processed_schema.json"
    
    # Check cache
    if use_cache and cache_file.exists():
        logger.info(f"Loading schema from cache: {cache_file}")
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached_data = json.load(f)
                schema = DataSchema(**cached_data)
                logger.info(f"Successfully loaded {len(schema.tables)} tables from cache")
                return schema
        except Exception as e:
            logger.warning(f"Failed to load from cache: {e}. Will process from source.")
    
    # Read CSV
    logger.info(f"Reading CSV file: {data_source}")
    try:
        df = pd.read_csv(data_source)
        logger.info(f"CSV loaded successfully. Shape: {df.shape}")
        logger.debug(f"Columns: {df.columns.tolist()}")
    except FileNotFoundError:
        logger.error(f"CSV file not found: {data_source}")
        raise
    except Exception as e:
        logger.error(f"Error reading CSV: {e}")
        raise
    
    # Strip whitespace from headers
    df.columns = df.columns.str.strip()
    logger.debug(f"Columns after stripping whitespace: {df.columns.tolist()}")
    
    # Validate required columns
    required_cols = ['Entity Name', 'Entity Description', 'Attribute Name', 
                     'Attribute Description', 'Data Type', 'Primary/Foreign Key']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.error(f"Missing required columns: {missing_cols}")
        raise ValueError(f"Missing required columns: {missing_cols}")
    
    # Initialize LLM early for description generation
    logger.info("Initializing LLM for description generation")
    try:
        model = get_azure_chat_client()
        logger.info("LLM client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to create LLM client: {e}")
        raise
    
    # Group by entity to create tables
    logger.info("Grouping data by entity to create tables")
    tables = []
    
    for entity_name, group in df.groupby('Entity Name'):
        logger.debug(f"Processing entity: {entity_name} with {len(group)} attributes")
        
        # Collect attribute metadata
        attributes_metadata = []
        for idx, row in group.iterrows():
            try:
                attributes_metadata.append({
                    'name': row['Attribute Name'].strip(),
                    'data_type': row['Data Type'].strip(),
                    'key_type': row['Primary/Foreign Key'].strip() if pd.notna(row['Primary/Foreign Key']) and row['Primary/Foreign Key'].strip() else None
                })
                logger.debug(f"  Collected metadata for attribute: {attributes_metadata[-1]['name']}")
            except Exception as e:
                logger.error(f"Error processing attribute at row {idx}: {e}")
                logger.error(f"Row data: {row.to_dict()}")
                raise
        
        # Generate descriptions using LLM based on Basel framework
        logger.info(f"Generating Basel-compliant descriptions for table: {entity_name}")
        
        attr_list = "\n".join([
            f"- {attr['name']} ({attr['data_type']}){' [' + attr['key_type'] + ']' if attr['key_type'] else ''}"
            for attr in attributes_metadata
        ])
        
        description_prompt = f"""You are a banking domain expert familiar with the Basel regulatory framework (Basel I, II, III, IV).

Generate descriptions for the following database table and its attributes in the context of banking regulatory compliance and risk management.

Table Name: {entity_name}
Attributes:
{attr_list}

Please provide:
1. A comprehensive table description (2-3 sentences) explaining its purpose in the Basel framework context
2. For each attribute, provide a clear, concise description (1-2 sentences) explaining its role in regulatory reporting, risk management, or compliance

Format your response as JSON:
{{
  "table_description": "...",
  "attributes": {{
    "attribute_name": "description",
    ...
  }}
}}

Focus on Basel-relevant aspects such as:
- Credit risk, market risk, operational risk
- Capital adequacy requirements
- Risk-weighted assets (RWA)
- Liquidity coverage ratio (LCR)
- Net stable funding ratio (NSFR)
- Counterparty credit risk
- Regulatory capital calculations
- Exposure calculations
"""
        
        try:
            logger.debug(f"Sending description generation request to LLM for {entity_name}")
            desc_agent = model.create_agent(
                name=f"desc_generator",
                instructions="You are a banking domain expert familiar with the Basel regulatory framework. Generate Basel-compliant descriptions. Return only valid JSON with no markdown."
            )
            response = await desc_agent.run(description_prompt)
            response_text = response.text
            logger.debug(f"Received LLM response for {entity_name}")
            
            # Parse JSON response
            # Remove markdown code blocks if present
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            descriptions = json.loads(response_text)
            table_description = descriptions["table_description"]
            attr_descriptions = descriptions["attributes"]
            
            logger.info(f"Successfully generated descriptions for {entity_name}")
            
        except Exception as e:
            logger.error(f"Failed to generate descriptions for {entity_name}: {e}")
            logger.warning(f"Falling back to generic descriptions")
            table_description = f"Table containing {entity_name} data for regulatory reporting"
            attr_descriptions = {attr['name']: f"{attr['name']} field" for attr in attributes_metadata}
        
        # Create attributes with LLM-generated descriptions
        attributes = []
        for attr_meta in attributes_metadata:
            attr_name = attr_meta['name']
            attr_desc = attr_descriptions.get(attr_name, f"{attr_name} field")
            
            attr = Attribute(
                name=attr_name,
                description=attr_desc,
                data_type=attr_meta['data_type'],
                key_type=attr_meta['key_type']
            )
            attributes.append(attr)
            logger.debug(f"  Created attribute: {attr.name} with generated description")
        
        # Create table with LLM-generated description
        table = Table(
            table_name=entity_name.strip(),
            description=table_description,
            attributes=attributes
        )
        tables.append(table)
        logger.info(f"Created table: {table.table_name} with {len(attributes)} attributes and Basel-compliant descriptions")
    
    schema = DataSchema(tables=tables)
    logger.info(f"Schema created with {len(schema.tables)} tables")
    
    # Generate overall schema analysis
    logger.info("Generating overall schema analysis with Basel framework focus")
    try:
        agent = model.create_agent(
            name="Basel Schema Analyst",
            instructions="""You are a Basel regulatory framework expert specializing in banking risk management and compliance. 
            
Analyze database schemas from a Basel perspective, focusing on:
- Regulatory capital requirements (Basel III/IV)
- Risk-weighted assets calculations
- Credit, market, and operational risk metrics
- Liquidity and funding ratios (LCR, NSFR)
- Counterparty credit risk and exposures
- Regulatory reporting requirements
- Data quality and consistency for compliance"""
        )
        logger.info("Basel analyst agent created successfully")
    except Exception as e:
        logger.error(f"Failed to create LLM agent: {e}")
        raise
    
    # Prepare schema summary for LLM
    logger.debug("Preparing schema summary for LLM analysis")
    schema_summary = "\n\n".join([
        f"Table: {table.table_name}\n"
        f"Description: {table.description}\n"
        f"Attributes:\n" + 
        "\n".join([
            f"  - {attr.name} ({attr.data_type}){' [' + attr.key_type + ']' if attr.key_type else ''}: {attr.description}"
            for attr in table.attributes
        ])
        for table in schema.tables
    ])
    
    prompt = f"""Review this database schema in the context of Basel regulatory framework compliance:

{schema_summary}

Please analyze from a Basel perspective:
1. Completeness for regulatory reporting (Basel III/IV requirements)
2. Key risk metrics coverage (credit risk, market risk, operational risk)
3. Data quality and consistency for capital adequacy calculations
4. Missing attributes critical for RWA calculations
5. Relationship recommendations for regulatory reporting workflows
6. Compliance with Basel data standards and taxonomies"""
    
    logger.info("Sending schema to LLM for Basel compliance analysis")
    try:
        response = (await agent.run(prompt)).text
        logger.info(f"Received Basel compliance analysis ({len(response)} characters)")
    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        raise
    
    # Cache results
    logger.info("Caching processed schema")
    try:
        Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)
        
        # Save schema with UTF-8 encoding
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(schema.model_dump(), f, indent=2, default=str, ensure_ascii=False)
        logger.info(f"Schema cached to: {cache_file}")
        
        # Store LLM insights separately with UTF-8 encoding
        insights_file = Path(CACHE_DIR) / "basel_compliance_analysis.txt"
        with open(insights_file, 'w', encoding='utf-8') as f:
            f.write(response)
        logger.info(f"Basel compliance analysis saved to: {insights_file}")
        
    except Exception as e:
        logger.error(f"Failed to cache results: {e}")
        # Don't raise - caching failure shouldn't stop the process
    
    logger.info("Data schema processing completed successfully")
    return schema


async def get_table_by_name(schema: DataSchema, table_name: str) -> Optional[Table]:
    """Helper function to retrieve a specific table by name."""
    logger.debug(f"Searching for table: {table_name}")
    for table in schema.tables:
        if table.table_name.lower() == table_name.lower():
            logger.debug(f"Found table: {table.table_name}")
            return table
    logger.warning(f"Table not found: {table_name}")
    return None