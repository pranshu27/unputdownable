# Phase 1 parsers (QlikView-specific format)
from output_parser import (
    qlik_data_core_output_parser, 
    hierarchy_output_parser, 
    visualization_output_parser, 
    filter_output_parser, 
    parameter_variable_output_parser,
    sheet_output_parser,
    dashboard_output_parser
)

# Phase 2 parsers (Common Model format) - QlikView-specific file
from output_parser_qlikview import (
    common_data_sources_output_parser,
    common_relationships_output_parser,
    common_tables_output_parser,
    common_calculations_output_parser
)

EXTRACTION_PROMPTS = {
    "dataextractor": f"""
        You are a QlikView metadata extraction expert. Your task is to extract detailed data source, data model, and data transformations information from the provided QlikView `LoadScript`.
        Add data types to the fields/columns.
        Use the above instructions to generate the final JSON output for the provided single node from the QlikView files.  
        {qlik_data_core_output_parser.get_format_instructions()}
        Use your knowledge of QlikView syntax (`ODBC CONNECT`, `SQL SELECT`, `FROM`, `LIB CONNECT TO`, etc.),
        and analyze XML fields in `DocProperties` and `QlikViewProject` to enrich the metadata.
        Provide each transformation as a different object.
        If any field is unknown, use an empty string but do not omit the field.
    """,
    "visualizations" : f"""
      You are a QlikView dashboard visualization expert. Your task is to analyze QlikView project files related to visual components 
      (e.g., chart objects like CH*, CS*, TB* files) and extract detailed metadata about each visualization.

      You are provided with:
      1. The full content of a **QlikViewProject.xml** file, which contains a list of all valid visualization object IDs (e.g., 'Document\\CH01', 'Document\\TB01').
      2. The full content of a **corresponding visualization object XML file** (such as CH01.xml, TB01.xml, etc.) that includes properties of a single visualization object.
      3. The **specific Object ID** associated with the visualization file being processed (e.g., "CH01").

      Your task is to:
      - Check whether the provided Object ID exists in the list from QlikViewProject.xml.
      - If it exists, extract the full metadata for that visualization according to the format described below.
      - If it does not exist, return an empty list for `visualizations`.

      Use the structure defined below to format your output:

      {visualization_output_parser.get_format_instructions()}

      ### Guidelines:
      - Determine the **type of visualization** (e.g., "Scatter Plot", "Straight Table") from the XML content.
      - For Straight table, show straight_table_columns, (measures and dimensions)
      - Populate specific fields depending on type:
        - For **Straight Tables**:
          - Populate `dimensions`, `measures, `straight_table_columns` with ordered list of columns (name + expression).
        - For **Charts** (bar chart, combo chart, scatter chart, etc.):
          - Populate `dimensions`, `measures`, and `chart_mappings`.
          - show `chart_mappings` for combo chart.
        - For **Text Objects**:
          - Show measures, dimensions, chart_mappings as null.
      - secondary_y_axis is must be blank for scatter plot, but not for combo chart.
      - Your JSON output should include:
        - `formatting`: styling info (border, font, etc.)
        - `interactivity`: minimize/maximize, export options
      - For "Sub-Grouping by Profit, Sales and Quantity" columns are Sub-Grouping, Profit, Sales, Quantity.
      ### Output Notes:
      - The object ID must match one listed in QlikViewProject.xml.
      - Return the metadata inside a `visualizations` array.
    """,
    "filters": f"""
        You are a QlikView filter expert. Your task is to extract detailed metadata for filters from the provided QlikView project files.
        You are provided with:
        1. The full content of a **QlikViewProject.xml** file, which contains filter object IDs (e.g., 'Document\\LB01').
        2. The full content of a **corresponding filter object XML file** (such as LB01.xml) that includes properties of the filter object.
        
        Your task is to:
        - Parse the filter object XML in detail to extract:
          - The filter type (e.g., "List Box").
          - The columns used in the filter.
          - Formatting options (font, size, style).
          - Interactivity options (e.g., allow resize, search).
          - Sorting options.
          - Background color and other UI attributes.

        Use the structure defined below to format your output:

        {filter_output_parser.get_format_instructions()}
    """,
    "parameters_variables": f"""
        You are a QlikView parameter/variable expert. Your task is to extract detailed metadata for parameters and variables from the provided QlikView project files.
        You are provided with:
        1. The full content of a **QlikViewProject.xml** file, which contains parameter/variable details (e.g., 'LongDayNames').
        
        Your task is to:
        - Parse the project file to extract:
          - The name of the parameter/variable.
          - The type of the parameter/variable (e.g., Variable).
          - Any associated calculation (if available).

        Use the structure defined below to format your output:

        {parameter_variable_output_parser.get_format_instructions()}
    """,
    "sheets": f"""
        You are a QlikView sheet extraction expert. Your task is to extract detailed metadata for sheets from the provided QlikView project files.
        You are provided with:
        1. The full content of a **QlikViewProject.xml** file, which contains Chart IDs (e.g., 'Document\\CH01').
        
        Your task is to:
        - Parse the project file to extract:
          - The ID and name of each sheet.
        
        Use the structure defined below to format your output:

        {sheet_output_parser.get_format_instructions()}
    """,
    "dashboards": f"""
      You are a QlikView dashboard expert. Your task is to extract detailed metadata for a single dashboard from the provided QlikView project files.

      You are provided with:
      1. The full content of a **QlikViewProject.xml** file, which contains the definition for one dashboard (sheet) with ID like 'Document\\SH01'.
      2. The full content of the corresponding dashboard XML file (e.g., SH01.xml), which contains layout and positioning details for child visual objects such as charts, listboxes, text objects, and containers.
      3. Sending a dictionary with keys object_id and value name. Make sure the name of component must be the name from this json.
      Your task is to:
      - Extract the following metadata for the single dashboard:
        - Dashboard ID (e.g., SH01), name (if available), width, and height.
        - A list of all visual components (child objects) used on the dashboard.
          - For each component, extract:
            - name of the component.
            - Object ID (e.g., CH01, LB01, CS01, TX01)
            - Positioning: top, left, width, height

      - Extract only the main dashboard, ignore all other.

      Use the following structured format to return your response:

      {dashboard_output_parser.get_format_instructions()}
  """,
    "hierarchies": f"""
        You are a QlikView hierarchy expert. Your task is to extract detailed metadata for hierarchies/ groups from the provided QlikView project files.
        You are provided with:
        1. The full content of a **QlikViewProject.xml** file, which contains hierarchy definitions (e.g., 'Grouping and Sub-Grouping').
        
        Your task is to:
        - Parse the project file to extract:
          - The name of each hierarchy.
          - The members associated with each hierarchy.
        Output must be:
          "hierarchies": [
          {{
            "name": "Grouping, Sub-Grouping",
            "members": [
              "[Grouping, Sub-Grouping - Split 1]",
              "[Grouping, Sub-Grouping - Split 2]",
              "[Region]"
            ]
          }},
          {{
            "name": "State, City, Postal Code",
            "members": [
              "[Country, State, City, Postal Code - Split 1]",
              "[Country, State, City, Postal Code - Split 2]",
              "[Country, State, City, Postal Code - Split 3]"
            ]
          }}
        ]
        
        Use the structure defined below to format your output:

        {hierarchy_output_parser.get_format_instructions()}
    """,
    
    # ============================================================================
    # PHASE 2: DIRECT COMMON MODEL EXTRACTION
    # These prompts output Common Model format directly (no transformation needed)
    # ============================================================================
    
    "data_sources_common": f"""
        You are a QlikView data source extraction expert. Your task is to extract data source information
        in COMMON MODEL FORMAT.

        **CRITICAL: Output must match the Common Model schema exactly - this will be used directly without transformation.**

        You are provided with:
        1. The **Data Sources** section from Phase 1 extraction (QlikView format)
        2. The **LoadScript.txt** content showing connection strings and file paths

        **COMMON MODEL OUTPUT FORMAT:**
        You MUST output data sources in this exact JSON structure:
        
        {{
          "data_sources": [
            {{
              "id": "ds_<sanitized_source_name>",
              "name": "<original_source_name>",
              "source_type": "file|database|api|inline",
              "connection_mode": "import|direct_query",
              "authentication_method": "file_system|windows|sql|oauth|null",
              "server": "server_name_or_null",
              "database": "database_name_or_null",
              "schema": "schema_name_or_null",
              "path": "file_path_or_null",
              "gateway": null,
              "refresh_frequency": "refresh_schedule_or_null",
              "connection_details": "additional_connection_info_or_null",
              "is_published": true|false|null
            }}
          ]
        }}
        
        **ID Generation Rules:**
        - source id: "ds_<lowercase_source_name_with_underscores>" (e.g., "ds_sales_qvd", "ds_sql_server")
        - Sanitize names: lowercase, replace spaces/special chars with underscores
        
        **Field Guidelines:**
        - `name`: Original source name (file name, table name, etc.)
        - `source_type`: 
          - "file" for QVD, CSV, Excel, TXT files
          - "database" for SQL Server, Oracle, ODBC connections
          - "api" for REST, Web connectors
          - "inline" for INLINE LOAD statements
        - `connection_mode`: "import" (QlikView loads data into memory)
        - `authentication_method`:
          - "file_system" for file sources
          - "windows" for Windows authentication
          - "sql" for SQL authentication
          - null if not applicable
        - `server`: Database server name (null for files)
        - `database`: Database name (null for files)
        - `schema`: Schema name (null for files)
        - `path`: Full file path for file sources (null for databases)
        - `gateway`: null (QlikView doesn't use gateways like Power BI)
        - `refresh_frequency`: Extract from LoadScript comments or set to null
        - `connection_details`: Any additional connection info
        - `is_published`: null (not applicable to QlikView)
        
        **Important:**
        - Extract ALL data sources mentioned in LoadScript
        - Match source names to what tables reference
        - Use null for fields that don't apply to QlikView
        
        **Output Format:**
        {common_data_sources_output_parser.get_format_instructions()}
    """,
    
    "relationships": f"""
        You are a QlikView relationship extraction expert. Your task is to analyze QlikView LoadScript and data model usage 
        to identify and extract ALL table relationships in COMMON MODEL FORMAT.

        **CRITICAL: Output must match the Common Model schema exactly - this will be used directly without transformation.**

        You are provided with:
        1. The full QlikView **LoadScript.txt** content, which contains LOAD statements, JOIN operations, and table definitions.
        2. The **Data Model** section showing which tables exist and their fields.
        3. The **Visualizations** section showing how tables are used together in charts.

        Your task is to identify relationships by analyzing:
        
        **A. Explicit Joins in LoadScript:**
        - Look for JOIN, LEFT JOIN, RIGHT JOIN, INNER JOIN, OUTER JOIN keywords
        - Extract the join conditions (ON clauses or implicit key matching)
        - Example: `LEFT JOIN (Sales) LOAD CustomerID, CustomerName FROM Customers;`
          → Relationship: Sales.CustomerID → Customers.CustomerID
        
        **B. Implicit Key Matching (QlikView Associative Model):**
        - QlikView automatically creates associations when tables share identically-named fields
        - Example: If both "Sales" and "Products" tables have a "ProductID" field, they are automatically related
        - Identify these by finding common field names across tables
        
        **C. Field Name Pattern Matching:**
        - Look for foreign key patterns: CustomerID, Customer_ID, Cust_ID, etc.
        - Match these to primary keys in dimension tables
        - Example: Sales.CustomerID likely relates to Customer.CustomerID or Customer.ID
        
        **D. Usage Patterns in Visualizations:**
        - If a visualization uses fields from multiple tables together, they must be related
        - Example: A chart showing [Customer.Name] and [Sales.Amount] implies Customer ↔ Sales relationship
        
        **E. Cardinality Detection:**
        - Determine cardinality based on field names and table types:
          - Fact table → Dimension table = many_to_one
          - Dimension → Dimension (via bridge) = many_to_many
          - ID fields with same name = one_to_one or one_to_many
        
        **COMMON MODEL OUTPUT FORMAT:**
        You MUST output relationships in this exact JSON structure:
        
        {{
          "relationships": [
            {{
              "id": "rel_<left_table>_<right_table>",
              "left_table_id": "tbl_<sanitized_left_table_name>",
              "left_column": "<column_name>",
              "right_table_id": "tbl_<sanitized_right_table_name>",
              "right_column": "<column_name>",
              "cardinality": "one_to_one|one_to_many|many_to_one|many_to_many",
              "join_type": "inner|left|right|full",
              "active": true|false,
              "filter_direction": "bidirectional|single",
              "enforced_integrity": true|false|null,
              "relationship_type": "dimension_lookup|bridge|date_relationship",
              "note": "Optional explanation of how this relationship was inferred"
            }}
          ]
        }}
        
        **ID Generation Rules:**
        - relationship id: "rel_<left_table>_<right_table>" (e.g., "rel_sales_customer")
        - table ids: "tbl_<lowercase_table_name_with_underscores>" (e.g., "tbl_sales", "tbl_customer_detail")
        - Sanitize names: lowercase, replace spaces/special chars with underscores
        
        **Field Guidelines:**
        - `cardinality`: Analyze table types and field usage to determine accurately
        - `join_type`: "left" for most QlikView relationships (unless explicit JOIN type found)
        - `active`: true (QlikView relationships are active by default)
        - `filter_direction`: "bidirectional" for QlikView's associative model
        - `enforced_integrity`: false (QlikView doesn't enforce referential integrity)
        - `relationship_type`: 
          - "dimension_lookup" for fact → dimension
          - "bridge" for many-to-many via bridge table
          - "date_relationship" for date field relationships
        - `note`: Explain how you inferred this (e.g., "Inferred from field name match: CustomerID")
        
        **Important:** 
        - Return ALL relationships you can identify
        - If no explicit relationships exist, infer them from field names and usage patterns
        - An empty list is only acceptable if tables are truly isolated
        - Do NOT include denormalized attribute relationships (e.g., Region appearing in multiple tables)
        
        **Output Format:**
        {common_relationships_output_parser.get_format_instructions()}
    """,
    
    "enhanced_tables": f"""
        You are a QlikView table metadata enrichment expert. Your task is to analyze the existing Data Model 
        and output it in COMMON MODEL FORMAT with detailed column-level metadata, table classification, and ingestion steps.

        **CRITICAL: Output must match the Common Model schema exactly - this will be used directly without transformation.**

        You are provided with:
        1. The **Data Model** section with basic table and field information
        2. The **LoadScript.txt** content showing how each table is loaded and transformed
        3. The **Data Transformations** section showing calculated fields
        4. The **Visualizations** section showing how fields are used
        5. The **Data Sources** section showing source file/database information

        Your task is to enhance each table with:

        **A. Table Classification:**
        - Classify each table as: `fact`, `dimension`, `bridge`, or `lookup`
        - **Fact tables**: Contain measures/metrics and foreign keys (e.g., Sales, Transactions, Orders)
        - **Dimension tables**: Contain descriptive attributes (e.g., Customer, Product, Date)
        - **Bridge tables**: Connect many-to-many relationships (e.g., OrderItems linking Orders and Products)
        - **Lookup tables**: Small reference tables (e.g., Status codes, Categories)
        
        **B. Column Metadata Enhancement:**
        For each column, determine by analyzing actual usage in the workbook:
        - `semantic_role`: 
          - "primary_key" if it's the unique identifier for this table
          - "foreign_key" if it references another table
          - "dimension" if it's a descriptive attribute
          - "measure" if it's a numeric metric
          - "date" if it's a date/time field
          - "identifier" if it's a unique ID but not used in relationships
        
        **CRITICAL - Analyze actual usage to set these flags accurately:**
        - `used_in_relationships`: 
          - Set to true ONLY if this column appears in the Relationships section OR in explicit JOINs in LoadScript
          - If not found in any relationship, set to false
          - Do NOT guess - verify actual usage
        
        - `used_in_filters`: 
          - Set to true ONLY if this column is used in WHERE clauses in LoadScript OR appears in the Filters section
          - If not found in any filter, set to false
          - Do NOT guess - verify actual usage
        
        - `used_in_groupby`: 
          - Set to true ONLY if this column is used as a dimension in the Visualizations section
          - Check the "dimensions" array in each visualization
          - If not found as a dimension, set to false
          - Do NOT guess - verify actual usage
        
        - `used_in_calculations`: 
          - Set to true ONLY if this column is referenced in calculated fields (Data Transformations or Calculation Dependencies)
          - Search for the column name in calculation expressions
          - If not found in any calculation, set to false
          - Do NOT guess - verify actual usage
        
        - `distinct_count_high`: 
          - Set to true if this is likely a high-cardinality field (IDs, names, dates, timestamps)
          - Set to false for low-cardinality fields (status codes, categories, flags)
        
        - `data_type`: Infer from QlikView field usage: string, integer, decimal, date, datetime, boolean
        - `nullable`: Infer from LoadScript (if there are null checks or default values), otherwise set to null
        
        **IMPORTANT**: If you cannot determine a flag value from the provided data, set it to null instead of guessing true/false.
        
        **C. Ingestion Steps Extraction:**
        For each table, extract the transformation pipeline from LoadScript:
        
        **Step Types:**
        - `read`: Initial data load (LOAD ... FROM, SQL SELECT)
        - `filter`: WHERE clauses, conditional loads
        - `join`: JOIN, LEFT JOIN, KEEP, etc.
        - `aggregate`: GROUP BY operations
        - `derive`: Calculated columns, expressions in LOAD
        - `rename`: AS clauses, field renaming
        - `change_type`: Type conversions (Date#, Num#, Text)
        - `split_to_rows`: SubField() operations
        - `merge`: CONCATENATE operations
        - `reference`: RESIDENT load from another table
        
        **COMMON MODEL OUTPUT FORMAT:**
        You MUST output tables in this exact JSON structure:
        
        {{
          "tables": [
            {{
              "id": "tbl_<sanitized_table_name>",
              "name": "<original_table_name>",
              "table_type": "fact|dimension|bridge|lookup",
              "source_data_source_id": "ds_<sanitized_source_name>",
              "is_materialized": true|false|null,
              "description": "Brief description of table purpose",
              "columns": [
                {{
                  "name": "<column_name>",
                  "data_type": "string|integer|decimal|date|datetime|boolean",
                  "nullable": true|false|null,
                  "hidden": false,
                  "semantic_role": "primary_key|foreign_key|dimension|measure|date|identifier|null",
                  "used_in_relationships": true|false|null,
                  "used_in_filters": true|false|null,
                  "used_in_groupby": true|false|null,
                  "used_in_calculations": true|false|null,
                  "distinct_count_high": true|false|null,
                  "description": "Optional column description"
                }}
              ],
              "ingestion": {{
                "steps": [
                  {{
                    "order": 1,
                    "step_type": "read|filter|join|aggregate|derive|rename|change_type|split_to_rows|merge|reference",
                    "description": "Human-readable description of this step",
                    "native_expressions": {{
                      "qlikview": "Original QlikView LoadScript code for this step"
                    }},
                    "columns_affected": ["column1", "column2"]
                  }}
                ]
              }}
            }}
          ]
        }}
        
        **ID Generation Rules:**
        - table id: "tbl_<lowercase_table_name_with_underscores>" (e.g., "tbl_sales", "tbl_customer_detail")
        - source id: "ds_<lowercase_source_name_with_underscores>" (match from Data Sources section)
        - Sanitize names: lowercase, replace spaces/special chars with underscores
        
        **Field Guidelines:**
        - `table_type`: Analyze structure and usage to classify accurately
          - **fact**: Contains measures and foreign keys (Sales, Transactions, Orders)
          - **dimension**: Contains descriptive attributes (Customer, Product, Date)
          - **bridge**: Connects many-to-many relationships
          - **lookup**: Small reference tables (Status codes, Categories)
        
        - `source_data_source_id`: Match to a data source from the Data Sources section
          - If loaded from file: find matching file name in Data Sources
          - If RESIDENT load: set to null and add note in description
        
        - `is_materialized`: true for most QlikView tables (data is loaded into memory)
        
        - `semantic_role`: Analyze actual usage, not just field names
          - "primary_key": Unique identifier for this table
          - "foreign_key": References another table (check Relationships section)
          - "dimension": Descriptive attribute
          - "measure": Numeric metric
          - "date": Date/time field
          - "identifier": Unique ID not used in relationships
          - null: Cannot determine
        
        - `used_in_*` flags: **VERIFY from actual usage, do NOT guess**
          - `used_in_relationships`: Check if column appears in Relationships section
          - `used_in_filters`: Check if used in WHERE clauses or Filters section
          - `used_in_groupby`: Check if used as dimension in Visualizations
          - `used_in_calculations`: Check if referenced in calculation expressions
          - Set to null if you cannot verify
        
        - `distinct_count_high`: 
          - true: High-cardinality (IDs, names, dates, timestamps)
          - false: Low-cardinality (status codes, categories, flags)
          - null: Cannot determine
        
        - `ingestion.steps`: Extract from LoadScript in order
          - Include native QlikView code in `native_expressions.qlikview`
          - List affected columns if applicable
          - If no LoadScript found, return empty steps array
        
        **Example LoadScript Analysis:**
        ```qlikview
        Sales:
        LOAD 
            OrderID,
            Date(OrderDate) as OrderDate,
            CustomerID,
            ProductID,
            Quantity * Price as Revenue
        FROM [Sales.qvd] (qvd)
        WHERE Year(OrderDate) >= 2020;
        ```
        
        **Extracted Ingestion Steps:**
        ```json
        "ingestion": {{
          "steps": [
            {{
              "order": 1,
              "step_type": "read",
              "description": "Load from Sales.qvd file",
              "native_expressions": {{
                "qlikview": "LOAD OrderID, Date(OrderDate) as OrderDate, CustomerID, ProductID, Quantity * Price as Revenue FROM [Sales.qvd] (qvd)"
              }}
            }},
            {{
              "order": 2,
              "step_type": "change_type",
              "description": "Convert OrderDate to date format",
              "columns_affected": ["OrderDate"],
              "native_expressions": {{
                "qlikview": "Date(OrderDate) as OrderDate"
              }}
            }},
            {{
              "order": 3,
              "step_type": "derive",
              "description": "Calculate Revenue as Quantity * Price",
              "columns_affected": ["Revenue"],
              "native_expressions": {{
                "qlikview": "Quantity * Price as Revenue"
              }}
            }},
            {{
              "order": 4,
              "step_type": "filter",
              "description": "Filter to orders from 2020 onwards",
              "native_expressions": {{
                "qlikview": "WHERE Year(OrderDate) >= 2020"
              }}
            }}
          ]
        }}
        ```
        
        **Important:** 
        - Analyze the LoadScript carefully to extract the exact transformation sequence
        - Use null for unknown values instead of guessing
        - Match source_data_source_id to actual Data Sources entries
        - Verify all usage flags from provided context
        
        **Output Format:**
        {common_tables_output_parser.get_format_instructions()}
    """,
    
    "calculation_dependencies": f"""
        You are a QlikView calculation dependency expert. Your task is to analyze all calculated fields, 
        expressions, and measures and output them in COMMON MODEL FORMAT.

        **CRITICAL: Output must match the Common Model schema exactly - this will be used directly without transformation.**

        You are provided with:
        1. The **Data Transformations** section with calculated fields
        2. The **Visualizations** section with chart expressions and measures
        3. The **Parameters or Variables** section with variable definitions
        4. The **LoadScript.txt** with inline calculations

        Your task is to extract ALL calculations and identify their dependencies:

        **A. Types of Calculations to Extract:**
        
        1. **Chart Expressions** (from Visualizations):
           - Measures in charts: `Sum(Sales)`, `Count(DISTINCT CustomerID)`
           - Calculated dimensions: `Year(OrderDate)`, `If(Amount > 1000, 'High', 'Low')`
        
        2. **Derived Fields** (from Data Transformations):
           - Fields created in LoadScript: `Quantity * Price as Revenue`
           - Conditional fields: `If(Status='Active', 1, 0) as IsActive`
        
        3. **Variables** (from Parameters or Variables):
           - Variable definitions: `vCurrentYear = Year(Today())`
           - Variables used in expressions: `Sum(Sales) / $(vTotalSales)`
        
        **B. Dependency Analysis:**
        
        For each calculation, identify:
        - `depends_on_columns`: List of base table columns used (e.g., ["Sales.Amount", "Sales.Quantity"])
        - `depends_on_measures`: List of other calculations/variables used (e.g., ["Total Sales", "vCurrentYear"])
        
        **Example:**
        ```
        Expression: Sum(Sales.Amount) / Sum(Sales.Quantity)
        → depends_on_columns: ["Sales.Amount", "Sales.Quantity"]
        → depends_on_measures: []
        
        Expression: Sum(Sales.Amount) / $(vTotalSales)
        → depends_on_columns: ["Sales.Amount"]
        → depends_on_measures: ["vTotalSales"]
        ```
        
        **C. Semantic Classification:**
        
        - `semantic_type`:
          - "sum" for Sum(), Total()
          - "count" for Count(), Count(DISTINCT)
          - "avg" for Avg()
          - "ratio" for division operations
          - "growth_rate" for year-over-year, CAGR calculations
          - "custom" for complex expressions
        
        - `aggregation_behavior`:
          - "additive": Can be summed across all dimensions (e.g., Sum(Sales))
          - "semi_additive": Can be summed across some dimensions but not time (e.g., Inventory Balance)
          - "non_additive": Cannot be summed (e.g., ratios, percentages, averages)
        
        - `is_base_measure`:
          - true: Direct aggregation of a column (e.g., Sum(Amount))
          - false: Derived from other measures (e.g., Profit Margin = Profit / Revenue)
        
        **COMMON MODEL OUTPUT FORMAT:**
        You MUST output calculations in this exact JSON structure:
        
        {{
          "calculations": [
            {{
              "id": "calc_<sanitized_name>",
              "name": "<calculation_name>",
              "description": "Brief description of what this calculates",
              "semantic_type": "sum|count|avg|ratio|growth_rate|custom",
              "aggregation_behavior": "additive|semi_additive|non_additive",
              "data_type": "string|integer|decimal|date|datetime|boolean",
              "format_string": "#,##0.00|0.00%|#,##0|null",
              "is_base_measure": true|false,
              "reusable": true|false,
              "depends_on_columns": ["Table.Column1", "Table.Column2"],
              "depends_on_measures": ["Measure1", "Variable1"],
              "display": {{
                "folder": "Folder Name",
                "hidden": false,
                "tags": ["tag1", "tag2"]
              }},
              "expressions": {{
                "qlikview": "Original QlikView expression",
                "dax": "",
                "tableau": ""
              }}
            }}
          ]
        }}
        
        **ID Generation Rules:**
        - calculation id: "calc_<lowercase_name_with_underscores>" (e.g., "calc_total_sales", "calc_profit_margin")
        - Sanitize names: lowercase, replace spaces/special chars with underscores
        
        **Field Guidelines:**
        - `name`: Use the original calculation name from QlikView
        - `description`: Explain what business metric this represents
        - `semantic_type`: Classify based on the operation type
        - `aggregation_behavior`: Determine if it can be summed
        - `data_type`: Infer from the calculation result type
        - `format_string`: 
          - "#,##0.00" for currency/decimal
          - "0.00%" for percentages
          - "#,##0" for integers
          - null if unknown
        - `is_base_measure`: true if it directly aggregates a column, false if it uses other measures
        - `reusable`: true (most QlikView calculations are reusable)
        - `depends_on_columns`: List table.column format (e.g., "Sales.Amount")
        - `depends_on_measures`: List other calculation/variable names
        - `display.folder`: Group related calculations (e.g., "Sales KPIs", "Financial Metrics")
        - `display.tags`: Add relevant tags for searchability
        - `expressions.qlikview`: Store the original QlikView expression
        - `expressions.dax`: Leave empty (will be converted later)
        - `expressions.tableau`: Leave empty (will be converted later)
        
        **Important:**
        - Extract EVERY calculation, even simple ones like Sum(Amount)
        - Build the full dependency chain (if Calc C depends on Calc B which depends on Calc A, show all links)
        - Use QlikView syntax knowledge: Set Analysis, Aggr(), If(), Pick(), etc.
        - If a calculation uses a variable ($(varName)), list it in depends_on_measures
        - Set fields to null if you cannot determine them (don't guess)
        
        **Output Format:**
        {common_calculations_output_parser.get_format_instructions()}
    """
}
