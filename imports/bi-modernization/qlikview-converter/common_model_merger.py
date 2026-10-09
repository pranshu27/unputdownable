"""
Common Model Merger

Merges Phase 1 (QlikView-specific) and Phase 2 (Common Model) extraction results
into a single Common Model JSON output.

NO GUESSING - NO HARDCODED DEFAULTS - NO TRANSFORMATION OF DATA VALUES

This merger only:
1. Combines Phase 1 + Phase 2 results
2. Adds system metadata (model_id, extracted_at, etc.)
3. Transforms Phase 1 visualizations/dashboards structure (not data)
4. Generates stable IDs where needed

Author: Data Economy AI
Date: 2026-04-24
"""

import json
import uuid
import re
from datetime import datetime
from typing import Dict, List, Any, Optional


class CommonModelMerger:
    """
    Merges QlikView Phase 1 and Phase 2 extraction results into Common Model format.
    
    Phase 1 (QlikView format): Visualizations, Dashboards, Filters, etc.
    Phase 2 (Common Model format): Data Sources, Tables, Relationships, Calculations
    
    Output: Complete Common Model JSON
    """
    
    def __init__(self, phase1_output: Dict[str, Any], phase2_output: Dict[str, Any]):
        """
        Initialize merger with Phase 1 and Phase 2 results.
        
        Args:
            phase1_output: QlikView-specific extraction (7 agents)
            phase2_output: Common Model extraction (4 agents)
        """
        self.phase1 = phase1_output
        self.phase2 = phase2_output
        self.model_id = str(uuid.uuid4())
        self.extracted_at = datetime.now().isoformat()
    
    def merge(self) -> Dict[str, Any]:
        """
        Main merge method - combines all results into Common Model.
        
        Returns:
            Dictionary in Common Model format
        """
        print("\n" + "="*80)
        print("Common Model Merger - Combining Phase 1 + Phase 2 Results")
        print("="*80 + "\n")
        
        common_model = {
            "_comment_schema": "Tool-agnostic semantic model. Each section is self-contained and cross-referenced by stable IDs.",
            "schema_version": "1.0",
            "model_id": self.model_id,
            "name": self._extract_model_name(),
            "source_tool": "qlikview",
            "extracted_at": self.extracted_at,
            
            # Phase 2 results (already in Common Model format - just copy)
            "data_sources": self.phase2.get("data_sources", []),
            "tables": self.phase2.get("tables", []),
            "relationships": self.phase2.get("relationships", []),
            "calculations": self.phase2.get("calculations", []),
            
            # Phase 1 results (need light structural transformation)
            "visualizations": self._transform_visualizations(),
            "dashboards": self._transform_dashboards(),
            "filters": self._transform_filters(),
            "hierarchies": self._transform_hierarchies()
        }
        
        print("✅ Merge complete!")
        print(f"   - Model ID: {self.model_id}")
        print(f"   - Data Sources: {len(common_model['data_sources'])}")
        print(f"   - Tables: {len(common_model['tables'])}")
        print(f"   - Relationships: {len(common_model['relationships'])}")
        print(f"   - Calculations: {len(common_model['calculations'])}")
        print(f"   - Visualizations: {len(common_model['visualizations'])}")
        print(f"   - Dashboards: {len(common_model['dashboards'])}")
        print(f"   - Filters: {len(common_model['filters'])}")
        print(f"   - Hierarchies: {len(common_model['hierarchies'])}")
        print("="*80 + "\n")
        
        return common_model
    
    # ============================================================================
    # SYSTEM METADATA EXTRACTION
    # ============================================================================
    
    # def _extract_model_name(self) -> str:
    #     """
    #     Extract model name from Phase 1 executive summary or generate from tables.
    #     NO GUESSING - uses available data or creates descriptive name.
    #     """
    #     # Try executive summary first
    #     if 'executivesummary' in self.phase1:
    #         summary = self.phase1['executivesummary']
    #         if isinstance(summary, str) and 'Title:' in summary:
    #             lines = summary.split('\n')
    #             for line in lines:
    #                 if 'Title:' in line or 'title:' in line.lower():
    #                     title = line.split(':', 1)[1].strip().strip('"\'')
    #                     if title:
    #                         return title
        
    #     # Try to get from Phase 2 tables
    #     tables = self.phase2.get("tables", [])
    #     if tables:
    #         table_names = [t.get('name', '') for t in tables[:3]]
    #         return f"QlikView Model - {', '.join(table_names)}"
        
    #     # Default descriptive name
    #     return "QlikView Data Model"
    
    def _get_title_from_summary(self, summary: str) -> str:
        """Helper to reduce complexity of the main extraction logic."""
        if not isinstance(summary, str) or 'Title:' not in summary:
            return ""
            
        for line in summary.split('\n'):
            if 'title:' in line.lower():
                title = line.split(':', 1)[1].strip().strip('"\'')
                if title:
                    return title
        return ""

    def _extract_model_name(self) -> str:
        """
        Extract model name from Phase 1 executive summary or generate from tables.
        NO GUESSING - uses available data or creates descriptive name.
        """
        # 1. Try executive summary first
        summary = self.phase1.get('executivesummary')
        if summary:
            title = self._get_title_from_summary(summary)
            if title:
                return title

        # 2. Try to get from Phase 2 tables
        tables = self.phase2.get("tables", [])
        if tables:
            table_names = [t.get('name', '') for t in tables[:3]]
            return f"QlikView Model - {', '.join(table_names)}"

        # 3. Default descriptive name
        return "QlikView Data Model"
    # ============================================================================
    # PHASE 1 TRANSFORMATIONS (Structure Only - No Data Guessing)
    # ============================================================================
    
    def _transform_visualizations(self) -> List[Dict[str, Any]]:
        """
        Transform Phase 1 visualizations to Common Model structure.
        ONLY restructures - does NOT add defaults or guess values.
        """
        print("📊 Transforming Visualizations (structure only)...")
        
        qv_visualizations = self.phase1.get('Visualizations', [])
        transformed = []
        
        for viz in qv_visualizations:
            # Generate stable ID
            viz_id = f"viz_{self._sanitize_id(viz.get('object_id', viz.get('name', '')))}"
            
            # Copy data as-is, only add ID
            transformed_viz = {
                "id": viz_id,
                "object_id": viz.get("object_id"),
                "name": viz.get("name"),
                "type": viz.get("type"),
                "dimensions": viz.get("dimensions"),  # Can be None
                "measures": viz.get("measures"),  # Can be None
                "filters": viz.get("filters", []),
                "chart_mappings": viz.get("chart_mappings"),  # Can be None
                "straight_table_columns": viz.get("straight_table_columns"),  # Can be None
                "formatting": viz.get("formatting", {})
            }
            
            transformed.append(transformed_viz)
        
        print(f"   ✅ Transformed {len(transformed)} visualizations")
        return transformed
    
    def _transform_dashboards(self) -> List[Dict[str, Any]]:
        """
        Transform Phase 1 dashboards to Common Model structure.
        ONLY restructures - does NOT add defaults or guess values.
        """
        print("📋 Transforming Dashboards (structure only)...")
        
        qv_dashboards = self.phase1.get('Dashboards', [])
        transformed = []
        
        for dashboard in qv_dashboards:
            # Generate stable ID
            dash_id = f"dash_{self._sanitize_id(dashboard.get('object_id', dashboard.get('name', '')))}"
            
            # Transform components to reference visualization IDs
            components = []
            for comp in dashboard.get('components', []):
                component = {
                    "name": comp.get("name"),
                    "object_id": comp.get("object_id"),
                    "visualization_id": f"viz_{self._sanitize_id(comp.get('object_id', ''))}",  # Link to viz
                    "position": comp.get("position", {}),
                    "font_size": comp.get("font_size"),
                    "color": comp.get("color")
                }
                components.append(component)
            
            # Copy data as-is, only add ID and transform components
            transformed_dash = {
                "id": dash_id,
                "object_id": dashboard.get("object_id"),
                "name": dashboard.get("name"),
                "width": dashboard.get("width"),
                "height": dashboard.get("height"),
                "background_color": dashboard.get("background_color"),
                "components": components
            }
            
            transformed.append(transformed_dash)
        
        print(f"   ✅ Transformed {len(transformed)} dashboards")
        return transformed
    
    def _transform_filters(self) -> List[Dict[str, Any]]:
        """
        Transform Phase 1 filters to Common Model structure.
        ONLY restructures - does NOT add defaults or guess values.
        """
        print("🔍 Transforming Filters (structure only)...")
        
        qv_filters = self.phase1.get('Filters', [])
        transformed = []
        
        for filter_obj in qv_filters:
            # Generate stable ID
            filter_id = f"filter_{self._sanitize_id(filter_obj.get('object_id', filter_obj.get('name', '')))}"
            
            # Copy data as-is, only add ID
            transformed_filter = {
                "id": filter_id,
                "object_id": filter_obj.get("object_id"),
                "name": filter_obj.get("name"),
                "type": filter_obj.get("type"),
                "columns": filter_obj.get("columns", []),
                "formatting": filter_obj.get("formatting", {}),
                "background_color": filter_obj.get("background_color")
            }
            
            transformed.append(transformed_filter)
        
        print(f"   ✅ Transformed {len(transformed)} filters")
        return transformed
    
    def _transform_hierarchies(self) -> List[Dict[str, Any]]:
        """
        Transform Phase 1 hierarchies to Common Model structure.
        ONLY restructures - does NOT add defaults or guess values.
        """
        print("🌳 Transforming Hierarchies (structure only)...")
        
        qv_hierarchies = self.phase1.get('Hierarchies', [])
        transformed = []
        
        for hierarchy in qv_hierarchies:
            # Generate stable ID
            hier_id = f"hier_{self._sanitize_id(hierarchy.get('name', ''))}"
            
            # Copy data as-is, only add ID
            transformed_hier = {
                "id": hier_id,
                "name": hierarchy.get("name"),
                "members": hierarchy.get("members", [])
            }
            
            transformed.append(transformed_hier)
        
        print(f"   ✅ Transformed {len(transformed)} hierarchies")
        return transformed
    
    # ============================================================================
    # HELPER METHODS (ID Generation Only - No Data Logic)
    # ============================================================================
    
    def _sanitize_id(self, name: str) -> str:
        """
        Sanitize a name to create a valid ID.
        This is FORMATTING only - not data transformation.
        """
        if not name:
            return "unknown"
        
        # Remove special characters, replace spaces with underscores
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', str(name).lower())
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Remove leading/trailing underscores
        return sanitized.strip('_')


def merge_qlikview_results(phase1_output: Dict[str, Any], phase2_output: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to merge QlikView Phase 1 and Phase 2 results.
    
    Args:
        phase1_output: QlikView-specific extraction results
        phase2_output: Common Model extraction results
    
    Returns:
        Complete Common Model JSON
    """
    merger = CommonModelMerger(phase1_output, phase2_output)
    return merger.merge()


def merge_from_files(phase1_file: str, phase2_file: str, output_file: str) -> None:
    """
    Merge results from JSON files and save to output file.
    
    Args:
        phase1_file: Path to Phase 1 JSON file
        phase2_file: Path to Phase 2 JSON file
        output_file: Path to save merged Common Model JSON
    """
    print(f"\n📂 Loading Phase 1 from: {phase1_file}")
    with open(phase1_file, 'r', encoding='utf-8') as f:
        phase1_output = json.load(f)
    
    print(f"📂 Loading Phase 2 from: {phase2_file}")
    with open(phase2_file, 'r', encoding='utf-8') as f:
        phase2_output = json.load(f)
    
    # Merge
    common_model = merge_qlikview_results(phase1_output, phase2_output)
    
    # Save
    print(f"\n💾 Saving Common Model to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(common_model, f, indent=2, ensure_ascii=False)
    
    print("✅ Common Model saved successfully!")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 3:
        print("Usage: python common_model_merger.py <phase1_file> <phase2_file> [output_file]")
        print("\nExample:")
        print("  python common_model_merger.py phase1_qlikview.json phase2_common.json common_model_output.json")
        sys.exit(1)
    
    phase1_file = sys.argv[1]
    phase2_file = sys.argv[2]
    output_file = sys.argv[3] if len(sys.argv) > 3 else "common_model_qlikview.json"
    
    merge_from_files(phase1_file, phase2_file, output_file)
