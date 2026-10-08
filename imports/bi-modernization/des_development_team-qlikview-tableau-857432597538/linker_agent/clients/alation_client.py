"""
Client for connecting to your Swagger/Middleware API that proxies Alation

This client handles the business glossary terms and technical column mapping
"""

import asyncio
import aiohttp
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from linker_agent.utils.logger import configure_logger
from linker_agent.utils.html_cleaner import clean_html_description as _clean_html

logger = configure_logger(__file__)


class SwaggerAPIConfig(BaseModel):
    """Configuration for your Swagger API"""
    base_url: str = "https://dataeconomy-2025-nfr.mtse.alationcloud.com"
    api_token: Optional[str] = None
    auth_header_type: str = "TOKEN"  # "TOKEN" or "Authorization" or "Bearer"
    verify_ssl: bool = True
    timeout: int = 60
    glossary_id: int = 2  # Default glossary ID


class SwaggerAPIClient:
    """
    Client for your custom Swagger API that provides Alation data
    
    Handles:
    - GET /terms (business glossary)
    - GET /columns/{id} (technical columns)
    - GET /tables/{id} (tables)
    - GET /schemas/{id} (schemas)
    """
    
    def __init__(self, config: SwaggerAPIConfig):
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.session: Optional[aiohttp.ClientSession] = None
        
        # Set up authentication headers
        self.headers = {"Accept": "application/json"}
        
        if config.api_token:
            # Swagger middleware uses TOKEN header
            self.headers["TOKEN"] = config.api_token
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            headers=self.headers,
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def _get(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Make GET request"""
        if not self.session:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        url = f"{self.base_url}{endpoint}"

        try:
            logger.debug(f"GET {url} with params: {params}")

            async with self.session.get(
                url,
                params=params,
                ssl=self.config.verify_ssl
            ) as response:
                response.raise_for_status()
                data = await response.json()

                logger.debug(f"Response: {len(data) if isinstance(data, list) else 'single object'}")
                return data

        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP {e.status} error for {url}: {e.message}")
            raise
        except Exception as e:
            logger.error(f"Request failed for {url}: {e}")
            raise

    async def _put(self, endpoint: str, json_payload: Any) -> Any:
        """Make PUT request"""
        if not self.session:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        url = f"{self.base_url}{endpoint}"
        try:
            logger.debug(f"PUT {url} payload={json_payload}")
            async with self.session.put(
                url, json=json_payload, ssl=self.config.verify_ssl
            ) as response:
                response.raise_for_status()
                try:
                    return await response.json()
                except Exception:
                    return {"status_code": response.status, "detail": "Update accepted"}
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP {e.status} error for PUT {url}: {e.message}")
            raise
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error for PUT {url}: {e}")
            raise
        except asyncio.TimeoutError:
            logger.error(f"Timeout for PUT {url}")
            raise

    async def _resolve_template_id(
        self, term_id: int, template_id: Optional[int]
    ) -> Optional[int]:
        """Auto-fetch template_id from the term object if not explicitly provided."""
        if template_id is not None:
            return template_id
        try:
            result = await self._get("/integration/v2/term/", {"id": term_id})
            if isinstance(result, list) and result:
                return result[0].get("template_id")
        except Exception as exc:
            logger.warning(f"Could not auto-fetch template_id for term {term_id}: {exc}")
        return None
    
    # ========================================================================
    # BUSINESS GLOSSARY TERMS
    # ========================================================================
    
    async def get_terms(
        self,
        glossary_id: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get business glossary terms
        
        Args:
            glossary_id: Filter by glossary ID
            limit: Maximum number of results
            
        Returns:
            List of term objects with business descriptions
        """
        endpoint = "/integration/v2/term/"
        
        params = {}
        if glossary_id:
            params["glossary_id"] = glossary_id
        if limit:
            params["limit"] = limit
        
        return await self._get(endpoint, params)
    
    def extract_data_asset_oid(self, term: Dict[str, Any]) -> Optional[int]:
        """
        Extract column ID from "Data Asset" custom field
        
        Args:
            term: Business term object
            
        Returns:
            Column ID (oid) or None if not linked
        """
        custom_fields = term.get("custom_fields", [])
        
        for field in custom_fields:
            if field.get("field_name") == "Data Asset":
                value = field.get("value", [])
                if isinstance(value, list) and len(value) > 0:
                    asset = value[0]
                    if asset.get("otype") == "attribute":
                        return asset.get("oid")
        
        return None
    
    @staticmethod
    def clean_html_description(html_text: str) -> str:
        return _clean_html(html_text)
    
    # ========================================================================
    # TECHNICAL COLUMNS
    # ========================================================================
    
    async def get_all_columns(
        self,
        limit: Optional[int] = None,
        max_concurrent: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get ALL columns from Alation (not just linked ones)
        
        This is needed for Tier 2 semantic matching where we need to match
        unlinked business terms to any available column.
        
        Args:
            limit: Maximum number of columns to fetch (None = all)
            max_concurrent: Maximum concurrent requests for pagination
            
        Returns:
            List of all column objects
        """
        endpoint = "/integration/v2/column/"
        params = {}
        
        if limit:
            params["limit"] = limit
        
        logger.info(f"Fetching all columns from Alation...")
        
        try:
            columns = await self._get(endpoint, params)
            
            if isinstance(columns, list):
                logger.info(f"✓ Fetched {len(columns)} columns")
                return columns
            else:
                logger.warning(f"Unexpected response type: {type(columns)}")
                return [columns] if columns else []
                
        except Exception as e:
            logger.error(f"Failed to fetch all columns: {e}")
            return []
    
    async def get_column_by_id(self, column_id: int) -> Dict[str, Any]:
        """
        Get column details by ID
        
        Args:
            column_id: Alation column ID (oid from Data Asset)
            
        Returns:
            Column object with name, type, table_id, etc.
        """
        endpoint = f"/integration/v2/column/"
        params = {"id": column_id}
        
        result = await self._get(endpoint, params)
        # API returns a list, get first item
        return result[0] if isinstance(result, list) and result else result
    
    async def get_columns_batch(
        self,
        column_ids: List[int],
        max_concurrent: int = 10
    ) -> Dict[int, Dict[str, Any]]:
        """
        Get multiple columns concurrently
        
        Args:
            column_ids: List of column IDs
            max_concurrent: Maximum concurrent requests
            
        Returns:
            Dictionary mapping column_id -> column object
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_column(col_id: int):
            async with semaphore:
                try:
                    column = await self.get_column_by_id(col_id)
                    return col_id, column
                except Exception as e:
                    logger.error(f"Failed to fetch column {col_id}: {e}")
                    return col_id, None
        
        logger.info(f"Fetching {len(column_ids)} columns (max {max_concurrent} concurrent)...")
        
        tasks = [fetch_column(cid) for cid in column_ids]
        results = await asyncio.gather(*tasks)
        
        return {col_id: col_data for col_id, col_data in results if col_data is not None}
    
    # ========================================================================
    # SCHEMAS
    # ========================================================================
    
    async def get_schema_by_id(self, schema_id: int) -> Dict[str, Any]:
        """
        Get schema details by ID
        
        Args:
            schema_id: Schema ID
            
        Returns:
            Schema object
        """
        endpoint = f"/integration/v2/schema/"
        params = {"id": schema_id}
        
        result = await self._get(endpoint, params)
        # API returns a list, get first item
        return result[0] if isinstance(result, list) and result else result
    
    # ========================================================================
    # TABLES
    # ========================================================================
    
    async def get_table_by_id(self, table_id: int) -> Dict[str, Any]:
        """
        Get table details by ID
        
        Args:
            table_id: Alation table ID
            
        Returns:
            Table object
        """
        endpoint = f"/integration/v2/table/"
        params = {"id": table_id}
        
        result = await self._get(endpoint, params)
        # API returns a list, get first item
        return result[0] if isinstance(result, list) and result else result
    
    async def get_tables_batch(
        self,
        table_ids: List[int],
        max_concurrent: int = 10
    ) -> Dict[int, Dict[str, Any]]:
        """
        Get multiple tables concurrently
        
        Args:
            table_ids: List of table IDs
            max_concurrent: Maximum concurrent requests
            
        Returns:
            Dictionary mapping table_id -> table object
        """
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def fetch_table(tbl_id: int):
            async with semaphore:
                try:
                    table = await self.get_table_by_id(tbl_id)
                    return tbl_id, table
                except Exception as e:
                    logger.error(f"Failed to fetch table {tbl_id}: {e}")
                    return tbl_id, None
        
        logger.info(f"Fetching {len(table_ids)} tables (max {max_concurrent} concurrent)...")
        
        tasks = [fetch_table(tid) for tid in table_ids]
        results = await asyncio.gather(*tasks)
        
        return {tbl_id: tbl_data for tbl_id, tbl_data in results if tbl_data is not None}
    
    # ========================================================================
    # WRITE-BACK TO ALATION
    # ========================================================================

    async def update_term_description(
        self,
        term_id: int,
        description: str,
        template_id: Optional[int] = None,
    ) -> dict:
        """PUT /integration/v2/term/ — update a glossary term's description.

        Args:
            term_id: Alation term ID.
            description: HTML-formatted description content.
            template_id: Optional template ID for custom field context.

        Returns:
            The Alation API response as a dict.
        """
        item: Dict[str, Any] = {"id": term_id, "description": description}
        if template_id is not None:
            item["template_id"] = template_id
        return await self._put("/integration/v2/term/", [item])

    async def update_custom_field_values(self, updates: List[dict]) -> dict:
        """PUT /integration/v2/custom_field_value/ — batch-update custom field values.

        Args:
            updates: List of update dicts, each containing ``field_id``,
                ``otype``, ``oid``, and ``value``.

        Returns:
            The Alation API response as a dict.
        """
        return await self._put("/integration/v2/custom_field_value/", updates)

    # ========================================================================
    # ENRICHED TERM VIEWS
    # ========================================================================

    async def get_terms_with_columns(
        self, glossary_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Fetch glossary terms with their linked column details."""
        terms = await self.get_terms(glossary_id=glossary_id)
        result = []
        for term in terms:
            col_id = self.extract_data_asset_oid(term)
            col = None
            if col_id:
                try:
                    col = await self.get_column_by_id(col_id)
                except Exception:
                    pass
            result.append({
                "id": term["id"],
                "title": term["title"],
                "description": SwaggerAPIClient.clean_html_description(
                    term.get("description") or ""
                ),
                "column_id": col.get("id") if col else None,
                "column_name": col.get("name") if col else None,
                "column_data_type": col.get("column_type") if col else None,
            })
        return result

    async def get_glossary_tree(self, glossary_id: int) -> Dict[str, Any]:
        """Fetch all terms from a glossary AND its discovered sub-glossaries.

        Retrieves direct terms, then follows any ``glossary_ids`` references
        on those terms to pull in sub-glossary content as well.
        """
        direct_terms = await self.get_terms(glossary_id=glossary_id)

        all_glossary_ids = {glossary_id}
        for term in direct_terms:
            for gid in term.get("glossary_ids", []):
                all_glossary_ids.add(gid)

        all_terms = list(direct_terms)
        seen_ids = {t["id"] for t in all_terms}

        for gid in all_glossary_ids:
            if gid == glossary_id:
                continue
            sub_terms = await self.get_terms(glossary_id=gid)
            for t in sub_terms:
                if t["id"] not in seen_ids:
                    all_terms.append(t)
                    seen_ids.add(t["id"])

        result = [
            {
                "id": term["id"],
                "title": term["title"],
                "description": SwaggerAPIClient.clean_html_description(
                    term.get("description") or ""
                ),
                "glossary_ids": term.get("glossary_ids", []),
                "template_id": term.get("template_id"),
                "custom_fields": term.get("custom_fields", []),
            }
            for term in all_terms
        ]

        return {
            "status": "ok",
            "glossary_id": glossary_id,
            "term_count": len(result),
            "terms": result,
        }

    # ========================================================================
    # HIGH-LEVEL ORCHESTRATION
    # ========================================================================

    async def get_complete_glossary_with_technical_details(
        self,
        glossary_id: Optional[int] = None,
        max_concurrent: int = 10,
        fetch_all_columns: bool = True
    ) -> Dict[str, Any]:
        """
        Get complete business glossary with linked technical details
        
        This is the main method for fetching all data needed for term-column linking
        
        Process:
        1. Fetch all business terms
        2. Extract column IDs from "Data Asset" custom field (for Tier 1)
        3. Fetch those specific columns (for Tier 1)
        4. Fetch ALL columns (for Tier 2 semantic matching)
        5. Fetch table details for all columns
        6. Combine into unified structure
        
        Args:
            glossary_id: Filter by glossary ID
            max_concurrent: Maximum concurrent requests
            fetch_all_columns: If True, fetch all columns for Tier 2 (default: True)
            
        Returns:
            Dictionary with structure:
            {
                "terms": [...],  # All business terms
                "columns": [...],  # ALL columns (for Tier 2)
                "tables": [...],  # All tables
                "columns_by_id": {...},  # Column lookup dict
                "tables_by_id": {...},  # Table lookup dict
                "linked_terms": [  # Terms with Data Asset mapping (for reference)
                    {
                        "term": {...},
                        "column": {...},
                        "table": {...}
                    }
                ],
                "unlinked_terms": [...],  # Terms without Data Asset
                "stats": {...}
            }
        """
        logger.info("Fetching complete glossary with technical details...")
        
        # Step 1: Get all business terms
        logger.info("Step 1: Fetching business terms...")
        terms = await self.get_terms(glossary_id=glossary_id)
        logger.info(f"Found {len(terms)} business terms")
        
        # Step 2: Extract column IDs from Data Asset field
        logger.info("Step 2: Extracting Data Asset links...")
        linked_terms = []
        unlinked_terms = []
        linked_column_ids = []
        
        for term in terms:
            column_id = self.extract_data_asset_oid(term)
            if column_id:
                linked_terms.append(term)
                linked_column_ids.append(column_id)
            else:
                unlinked_terms.append(term)
        
        logger.info(f"Linked terms: {len(linked_terms)}, Unlinked terms: {len(unlinked_terms)}")
        
        # Step 3: Fetch the SPECIFIC linked columns (for Tier 1)
        logger.info("Step 3: Fetching linked columns...")
        linked_columns_map = await self.get_columns_batch(linked_column_ids, max_concurrent)
        logger.info(f"Fetched {len(linked_columns_map)} linked columns")
        
        # Step 4: Fetch ALL columns (for Tier 2 semantic matching)
        all_columns = []
        if fetch_all_columns:
            logger.info("Step 4: Fetching all columns for Tier 2 semantic matching...")
            all_columns = await self.get_all_columns()
            logger.info(f"Fetched {len(all_columns)} total columns")
        
        # Step 5: Build unified column dictionary
        columns_by_id = {}
        
        # Add linked columns first (priority)
        for col_id, col in linked_columns_map.items():
            columns_by_id[col_id] = col
        
        # Add all other columns
        for col in all_columns:
            col_id = col.get("id")
            if col_id and col_id not in columns_by_id:
                columns_by_id[col_id] = col
        
        logger.info(f"Total unique columns: {len(columns_by_id)}")
        
        # Step 6: Extract table IDs from ALL columns
        table_ids = set()
        for column in columns_by_id.values():
            table_id = column.get("table_id")
            if table_id:
                table_ids.add(table_id)
        
        # Step 7: Fetch tables
        logger.info(f"Step 5: Fetching {len(table_ids)} tables...")
        tables_map = await self.get_tables_batch(list(table_ids), max_concurrent)
        logger.info(f"Fetched {len(tables_map)} tables")
        
        # Step 8: Build enriched linked terms (for reference)
        logger.info("Step 6: Building enriched linked terms...")
        enriched_linked_terms = []
        
        for term in linked_terms:
            column_id = self.extract_data_asset_oid(term)
            column = columns_by_id.get(column_id)
            
            if column:
                table_id = column.get("table_id")
                table = tables_map.get(table_id) if table_id else None
                
                enriched_linked_terms.append({
                    "term": term,
                    "column": column,
                    "table": table,
                    "linkage_type": "direct",
                    "confidence_score": 100.0
                })
        
        stats = {
            "total_terms": len(terms),
            "linked_terms": len(enriched_linked_terms),
            "unlinked_terms": len(unlinked_terms),
            "total_columns": len(columns_by_id),
            "linked_columns": len(linked_columns_map),
            "unique_tables": len(tables_map),
            "linkage_coverage": round(len(enriched_linked_terms) / len(terms) * 100, 1) if terms else 0
        }
        
        logger.info(f"✓ Complete! {stats}")
        
        return {
            "terms": terms,
            "columns": list(columns_by_id.values()),
            "tables": list(tables_map.values()),
            "columns_by_id": columns_by_id,
            "tables_by_id": tables_map,
            "linked_terms": enriched_linked_terms,
            "unlinked_terms": unlinked_terms,
            "stats": stats
        }


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def example_usage():
    """Example of how to use the Swagger API client"""
    
    config = SwaggerAPIConfig(
        base_url="https://dataeconomy-2025-nfr.mtse.alationcloud.com",
        api_token="YOUR_API_TOKEN_HERE",  # Add your token
        auth_header_type="TOKEN",  # or "Authorization" or "Bearer"
        glossary_id=2
    )
    
    async with SwaggerAPIClient(config) as client:
        # Get complete glossary with technical details
        result = await client.get_complete_glossary_with_technical_details(glossary_id=2)
        
        print(f"Total terms: {result['stats']['total_terms']}")
        print(f"Linked: {result['stats']['linked_terms']}")
        print(f"Unlinked: {result['stats']['unlinked_terms']}")
        print(f"Coverage: {result['stats']['linkage_coverage']}%")
        
        # Show sample linked term
        if result['linked_terms']:
            sample = result['linked_terms'][0]
            print(f"\nSample linked term:")
            print(f"  Business Term: {sample['term']['title']}")
            print(f"  Column: {sample['column']['name']}")
            print(f"  Table: {sample['table']['name']}")
            print(f"  Confidence: {sample['confidence_score']}%")


if __name__ == "__main__":
    asyncio.run(example_usage())
