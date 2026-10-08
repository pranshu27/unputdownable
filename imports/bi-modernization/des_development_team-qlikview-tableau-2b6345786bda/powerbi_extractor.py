#!/usr/bin/env python3
"""
Power BI Model Extractor Utility
Extracts metadata, DAX, Power Query, relationships from .pbix files
"""

import json
from pathlib import Path
from datetime import datetime

try:
    from pbixray import PBIXRay
except ImportError as e:
    print(f"Warning: pbixray not installed - {e}")
    PBIXRay = None


class PowerBIExtractor:
    def __init__(self, pbix_path, output_dir, extract_table_data=False):
        self.pbix_path = pbix_path
        self.output_dir = Path(output_dir)
        self.extract_table_data = extract_table_data
        self.model = None
        self.extraction_summary = {
            "timestamp": datetime.now().isoformat(),
            "source_file": str(pbix_path),
            "extracted_components": [],
            "errors": []
        }
        
    def initialize_model(self):
        """Load the PBIX file.

        Some .pbix files are 'thin reports' — they contain only Report/Layout
        and connect to an external published semantic model, so there is no
        DataModel part inside the zip. pbixray raises when it can't find a
        DataModel. We must NOT propagate that failure: the report pages,
        diagram layout, and other zip-level artifacts can still be extracted
        and useful downstream. Mark the model as None and let each extractor
        skip gracefully."""
        if PBIXRay is None:
            raise ImportError("pbixray package is not installed")

        try:
            self.model = PBIXRay(self.pbix_path)
            self.extraction_summary["model_available"] = True
            return True
        except Exception as e:
            self.model = None
            self.extraction_summary["model_available"] = False
            self.extraction_summary["errors"].append(
                f"Data model not loaded (likely a thin report .pbix without an embedded "
                f"DataModel; pbixray says: {str(e)}). Continuing with report/layout-only "
                f"extraction."
            )
            print(
                "[powerbi_extractor] No embedded DataModel found in this .pbix "
                "(thin report). Skipping model-based extractors; will still "
                "extract Report/Layout and DiagramLayout if present."
            )
            return False
    
    def _safe_extract(self, name, extractor_func):
        """Safely extract data with error handling"""
        try:
            return extractor_func()
        except Exception as e:
            self.extraction_summary["errors"].append(f"{name} extraction: {str(e)}")
            return None

    def _model_required(self, name):
        """Skip a model-dependent extractor with a clear summary entry when
        the .pbix has no embedded DataModel (thin report)."""
        self.extraction_summary["errors"].append(
            f"{name} skipped: no embedded DataModel in this .pbix (thin report)."
        )
        return None
    
    def extract_metadata(self):
        """Extract basic metadata"""
        if self.model is None:
            return self._model_required("metadata")
        def _extract():
            metadata = {
                "size_bytes": self.model.size,
                "size_mb": round(self.model.size / (1024 * 1024), 2)
            }
            
            if hasattr(self.model, 'metadata') and self.model.metadata is not None:
                if hasattr(self.model.metadata, 'to_dict'):
                    metadata["metadata"] = self.model.metadata.to_dict(orient='records')
                else:
                    metadata["metadata"] = self.model.metadata
            
            output_path = self.output_dir / "metadata.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, default=str, ensure_ascii=False)
            
            self.extraction_summary["extracted_components"].append("metadata")
            return output_path
        
        return self._safe_extract("metadata", _extract)
    
    def extract_tables_list(self):
        """Extract list of all tables"""
        if self.model is None:
            return self._model_required("tables_list")
        def _extract():
            tables = self.model.tables
            if hasattr(tables, 'tolist'):
                tables = tables.tolist()
            else:
                tables = list(tables)
            
            output_path = self.output_dir / "tables_list.json"
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump({"tables": tables, "count": len(tables)}, f, indent=2, ensure_ascii=False)
            
            self.extraction_summary["extracted_components"].append("tables_list")
            self.extraction_summary["table_count"] = len(tables)
            return output_path
        
        return self._safe_extract("tables_list", _extract)

    def extract_power_query(self):
        """Extract Power Query (M code) expressions"""
        if self.model is None:
            return self._model_required("power_query")
        def _extract():
            pq_df = self.model.power_query
            
            if pq_df is not None and not pq_df.empty:
                output_path = self.output_dir / "power_query.json"
                pq_data = pq_df.to_dict(orient='records')
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(pq_data, f, indent=2, default=str, ensure_ascii=False)
                self.extraction_summary["extracted_components"].append("power_query")
                self.extraction_summary["power_query_count"] = len(pq_df)
                return output_path
            return None
        
        return self._safe_extract("power_query", _extract)
    
    def extract_dax_measures(self):
        """Extract DAX measures"""
        if self.model is None:
            return self._model_required("dax_measures")
        def _extract():
            measures_df = self.model.dax_measures

            if measures_df is not None and not measures_df.empty:
                output_path = self.output_dir / "dax_measures.json"
                measures_data = measures_df.to_dict(orient='records')
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(measures_data, f, indent=2, default=str, ensure_ascii=False)
                self.extraction_summary["extracted_components"].append("dax_measures")
                self.extraction_summary["dax_measures_count"] = len(measures_df)
                return output_path
            return None

        return self._safe_extract("dax_measures", _extract)

    def extract_rls(self):
        """Extract Row-Level Security (RLS) roles — role name, table, and the DAX
        filter expression — so the downstream can re-emit them as semantic-model
        roles. pbixray exposes these on `model.rls`."""
        if self.model is None:
            return self._model_required("rls")
        def _extract():
            df = self.model.rls
            if df is not None and not df.empty:
                output_path = self.output_dir / "rls.json"
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(df.to_dict(orient='records'), f, indent=2, default=str, ensure_ascii=False)
                self.extraction_summary["extracted_components"].append("rls")
                self.extraction_summary["rls_count"] = len(df)
                return output_path
            return None

        return self._safe_extract("rls", _extract)

    def extract_dax_tables(self):
        """Extract DAX-defined calculated tables (SUMMARIZE / CALCULATETABLE / Calendar / …).
        Includes Power BI's auto-generated LocalDateTable_* and DateTableTemplate_*
        which have no Power Query equivalent — only DAX bodies."""
        if self.model is None:
            return self._model_required("dax_tables")
        def _extract():
            df = self.model.dax_tables

            if df is not None and not df.empty:
                output_path = self.output_dir / "dax_tables.json"
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(df.to_dict(orient='records'), f, indent=2, default=str, ensure_ascii=False)
                self.extraction_summary["extracted_components"].append("dax_tables")
                self.extraction_summary["dax_tables_count"] = len(df)
                return output_path
            return None

        return self._safe_extract("dax_tables", _extract)

    def extract_dax_columns(self):
        """Extract DAX-defined calculated columns. Needed so calculated tables
        (and their hierarchies) get their column schema."""
        if self.model is None:
            return self._model_required("dax_columns")
        def _extract():
            df = self.model.dax_columns

            if df is not None and not df.empty:
                output_path = self.output_dir / "dax_columns.json"
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(df.to_dict(orient='records'), f, indent=2, default=str, ensure_ascii=False)
                self.extraction_summary["extracted_components"].append("dax_columns")
                self.extraction_summary["dax_columns_count"] = len(df)
                return output_path
            return None

        return self._safe_extract("dax_columns", _extract)

    def extract_diagram_layout(self):
        """Decode the DiagramLayout part of the PBIX (UTF-16 LE JSON) and save
        it as plain JSON for cross-reference / debugging."""
        def _extract():
            import zipfile
            with zipfile.ZipFile(self.pbix_path, "r") as z:
                if "DiagramLayout" not in z.namelist():
                    return None
                raw = z.read("DiagramLayout")

            text = None
            for enc in ("utf-16-le", "utf-16", "utf-8-sig", "utf-8"):
                try:
                    candidate = raw.decode(enc).strip().strip("\x00").lstrip("﻿")
                    if candidate.startswith("{"):
                        text = candidate
                        break
                except UnicodeDecodeError:
                    continue
            if not text:
                return None
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return None

            output_path = self.output_dir / "diagram_layout.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.extraction_summary["extracted_components"].append("diagram_layout")
            return output_path

        return self._safe_extract("diagram_layout", _extract)
    
    # Maps BIM dataType strings → standard data_type values
    _BIM_TYPE_MAP = {
        "int64": "integer", "int32": "integer", "int16": "integer",
        "double": "decimal", "decimal": "decimal", "currency": "decimal",
        "datetime": "datetime", "date": "datetime",
        "string": "string", "text": "string",
        "boolean": "boolean",
        "binary": "unknown", "variant": "unknown",
    }

    # Maps PBIXRay's PandasDataType strings → our standard data_type values
    _PANDAS_TYPE_MAP = {
        'Int64': 'integer', 'int64': 'integer', 'int32': 'integer',
        'int16': 'integer', 'int8': 'integer',
        'Float64': 'decimal', 'float64': 'decimal', 'float32': 'decimal',
        'decimal.Decimal': 'decimal',
        'datetime64[ns]': 'datetime', 'datetime64': 'datetime',
        'bool': 'boolean', 'boolean': 'boolean',
        'string': 'string',
        'object': 'string',   # pandas fallback for text columns
        'bytes': 'unknown',
    }

    def extract_schema(self):
        """Extract schema information"""
        if self.model is None:
            return self._model_required("schema")
        def _extract():
            schema_df = self.model.schema

            if schema_df is not None and not schema_df.empty:
                output_path = self.output_dir / "schema.json"
                schema_data = schema_df.to_dict(orient='records')
                # Normalise PandasDataType → data_type so the LLM sees standard names
                for row in schema_data:
                    pandas_type = str(row.get('PandasDataType', ''))
                    row['data_type'] = self._PANDAS_TYPE_MAP.get(pandas_type, 'unknown')
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(schema_data, f, indent=2, default=str, ensure_ascii=False)
                self.extraction_summary["extracted_components"].append("schema")
                return output_path
            return None

        return self._safe_extract("schema", _extract)
    
    def extract_bim_model(self):
        """Read DataModel BIM JSON directly for clean data types and format strings."""
        def _extract():
            import zipfile, shutil, tempfile
            tmp = Path(tempfile.mkdtemp())
            shutil.copy(self.pbix_path, tmp / "file.zip")
            bim = None
            try:
                with zipfile.ZipFile(tmp / "file.zip", "r") as z:
                    if "DataModel" in z.namelist():
                        raw = z.read("DataModel")
                        for enc in ("utf-16-le", "utf-16", "utf-8-sig", "utf-8"):
                            try:
                                text = raw.decode(enc).strip().strip('\x00')
                                if text and '{' in text:
                                    bim = json.loads(text)
                                    break
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                continue
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

            if not bim:
                return None

            model = bim.get("model", bim)
            tables = []
            for t in model.get("tables", []):
                cols = [
                    {
                        "name": c.get("name", ""),
                        "data_type": self._BIM_TYPE_MAP.get(
                            (c.get("dataType") or "").lower(), "unknown"
                        ),
                        "is_nullable": c.get("isNullable", True),
                    }
                    for c in t.get("columns", [])
                    if c.get("type") != "rowNumber"
                ]
                measures = [
                    {
                        "name": m.get("name", ""),
                        "expression": m.get("expression", ""),
                        "format_string": m.get("formatString", ""),
                        "description": m.get("description", ""),
                    }
                    for m in t.get("measures", [])
                ]
                tables.append({
                    "table": t.get("name", ""),
                    "columns": cols,
                    "measures": measures,
                })

            output_path = self.output_dir / "bim_model.json"
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump({"tables": tables}, f, indent=2, default=str)
            self.extraction_summary["extracted_components"].append("bim_model")
            return output_path

        return self._safe_extract("bim_model", _extract)

    def extract_relationships(self):
        """Extract model relationships"""
        if self.model is None:
            return self._model_required("relationships")
        def _extract():
            rel_df = self.model.relationships
            
            if rel_df is not None and not rel_df.empty:
                output_path = self.output_dir / "relationships.json"
                rel_data = rel_df.to_dict(orient='records')
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(rel_data, f, indent=2, default=str, ensure_ascii=False)
                self.extraction_summary["extracted_components"].append("relationships")
                self.extraction_summary["relationships_count"] = len(rel_df)
                return output_path
            return None
        
        return self._safe_extract("relationships", _extract)
    
    def save_summary(self):
        """Save extraction summary"""
        summary_path = self.output_dir / "extraction_summary.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(self.extraction_summary, f, indent=2, ensure_ascii=False)
        return summary_path
    
    def run(self):
        """Run the complete extraction process"""
        # Create output directory first
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.initialize_model()
        
        # Run all extractions
        extracted_files = []
        
        for extractor in [
            self.extract_metadata,
            self.extract_tables_list,
            self.extract_power_query,
            self.extract_dax_measures,
            self.extract_rls,
            self.extract_dax_tables,
            self.extract_dax_columns,
            self.extract_schema,
            self.extract_relationships,
            self.extract_bim_model,
            self.extract_diagram_layout,
        ]:
            result = extractor()
            if result:
                extracted_files.append(str(result))
        
        summary_path = self.save_summary()
        extracted_files.append(str(summary_path))
        
        return {
            "extracted_files": extracted_files,
            "summary": self.extraction_summary
        }


def extract_powerbi_model(pbix_path, output_dir):
    """
    Utility function to extract Power BI model metadata
    
    Args:
        pbix_path: Path to the .pbix file
        output_dir: Directory to save extracted JSON files
        
    Returns:
        dict with extracted_files list and summary
    """
    extractor = PowerBIExtractor(pbix_path, output_dir)
    return extractor.run()
