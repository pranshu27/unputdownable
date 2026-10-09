export interface Column {
    name: string;
    data_type: string;
    nullable: boolean;
    hidden: boolean;
    semantic_role: string | null;
    used_in_relationships: boolean;
    used_in_filters: boolean;
    used_in_groupby: boolean;
    used_in_calculations: boolean;
    distinct_count_high: boolean;
    description: string;
  }
  
  export interface IngestionStep {
    order: number;
    step_type: string;
    description: string;
    native_expressions: Record<string, string>;
  }
  
  export interface Table {
    id: string;
    name: string;
    table_type: 'fact' | 'dimension' | string;
    source_data_source_id: string;
    source_derived_from_table_id: string | null;
    is_materialized: boolean;
    description: string;
    columns: Column[];
    ingestion: { steps: IngestionStep[] };
  }
  
  export interface DataSource {
    id: string;
    name: string;
    source_type: string;
    connection_mode: string;
    authentication_method: string | null;
    server: string | null;
    database: string | null;
    schema: string | null;
    path: string | null;
    gateway: string | null;
    refresh_frequency: string | null;
  }
  
  export interface Relationship {
    id: string;
    left_table_id: string;
    left_column: string;
    right_table_id: string;
    right_column: string;
    cardinality: string;
    join_type: string;
    active: boolean;
    filter_direction: string;
    enforced_integrity: boolean;
    relationship_type: string;
    note: string;
  }
  
  export interface Calculation {
    id: string;
    name: string;
    description: string;
    semantic_type: string;
    aggregation_behavior: string;
    data_type: string;
    format_string: string;
    is_base_measure: boolean;
    reusable: boolean;
    depends_on_columns: string[];
    depends_on_measures: string[];
    display: { folder: string | null; hidden: boolean; tags: string[] };
    expressions: Record<string, string | null>;
  }
  export interface KpiLineageItem {
    kpi_name: string;
    kpi_id: string;
    description: string;
    formula: string;
    semantic_type: string;
    aggregation_behavior: string;
    data_type: string;
    format_string: string;
    is_base_measure: boolean;
    reusable: boolean;
    display: {
      folder: string;
      hidden: boolean;
      tags: string[];
    };
  
    depends_on_columns: {
      column_name: string;
      table_name: string;
      table_id: string;
      table_type: string;
      data_source: {
        name: string;
        source_type: string;
        connection_mode: string;
        path: string;
      };
    }[];
  
    depends_on_measures: {
      kpi_name: string;
      found: boolean;
      semantic_type: string;
    }[];
  }
  export interface ConsolidatedModel {
    schema_version: string;
    model_id: string;
    name: string;
    extracted_at: string;
  
    data_sources: DataSource[];
    tables: Table[];
    relationships: Relationship[];
    calculations: Calculation[];
  }
  export interface DataModel {
    data_sources: DataSource[];
    tables: Table[];
    relationships: Relationship[];
    calculations: Calculation[];
    technical_summary: string;
    consolidated_model: ConsolidatedModel;
    kpi_lineage: KpiLineageItem[];
    schema_version: string;
    model_id: string;
    name: string;
    extracted_at: string;
  }
  
 const sampleModel: DataModel = {
    "schema_version": "1.0",
    "model_id": "e734c521-c624-4b9f-b9eb-a92082c9c0e2",
    "name": "Secure Debit PBI",
    "extracted_at": "2026-04-24T12:16:40.908707",
    "data_sources": [
      {
        "id": "ds_dm_customer_detail_table",
        "name": "DM.Customer_Detail_Table.csv",
        "source_type": "CSV",
        "connection_mode": "import",
        "authentication_method": null,
        "server": null,
        "database": null,
        "schema": null,
        "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\DM.Customer_Detail_Table.csv",
        "gateway": null,
        "refresh_frequency": null
      },
      {
        "id": "ds_dm_insurance_agent_table",
        "name": "DM.Insurance_Agent_Table.csv",
        "source_type": "CSV",
        "connection_mode": "import",
        "authentication_method": null,
        "server": null,
        "database": null,
        "schema": null,
        "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\DM.Insurance_Agent_Table.csv",
        "gateway": null,
        "refresh_frequency": null
      },
      {
        "id": "ds_dm_policy_protection_plan",
        "name": "DM.Policy_Protection_Plan.csv",
        "source_type": "CSV",
        "connection_mode": "import",
        "authentication_method": null,
        "server": null,
        "database": null,
        "schema": null,
        "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\DM.Policy_Protection_Plan.csv",
        "gateway": null,
        "refresh_frequency": null
      },
      {
        "id": "ds_dm_policy_type",
        "name": "DM.Policy_Type.csv",
        "source_type": "CSV",
        "connection_mode": "import",
        "authentication_method": null,
        "server": null,
        "database": null,
        "schema": null,
        "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\DM.Policy_Type.csv",
        "gateway": null,
        "refresh_frequency": null
      },
      {
        "id": "ds_dm_regional_manager",
        "name": "DM.Regional_Manager.csv",
        "source_type": "CSV",
        "connection_mode": "import",
        "authentication_method": null,
        "server": null,
        "database": null,
        "schema": null,
        "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\DM.Regional_Manager.csv",
        "gateway": null,
        "refresh_frequency": null
      },
      {
        "id": "ds_dm_zonal_manager",
        "name": "DM.Zonal_Manager.csv",
        "source_type": "CSV",
        "connection_mode": "import",
        "authentication_method": null,
        "server": null,
        "database": null,
        "schema": null,
        "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\DM.Zonal_Manager.csv",
        "gateway": null,
        "refresh_frequency": null
      },
      {
        "id": "ds_fct_insurance_policy_table",
        "name": "FCT.Insurance_Policy_Table.csv",
        "source_type": "CSV",
        "connection_mode": "import",
        "authentication_method": null,
        "server": null,
        "database": null,
        "schema": null,
        "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv",
        "gateway": null,
        "refresh_frequency": null
      }
    ],
    "tables": [
      {
        "id": "DM_Customer_Detail_Table",
        "name": "DM Customer_Detail_Table",
        "table_type": "dimension",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Customer master / dimension",
        "columns": [
          {
            "name": "Customer ID",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Customer identifier / PK"
          },
          {
            "name": "Policy Holder Name",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Customer name"
          },
          {
            "name": "Gender",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Gender / demographic"
          },
          {
            "name": "Age at Entry",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Age when policy started"
          },
          {
            "name": "Current Age",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Current age of customer"
          },
          {
            "name": "Occupation",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Customer occupation"
          },
          {
            "name": "Smoker Status",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Smoker / non-smoker"
          },
          {
            "name": "Medical Exam Required",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Indicator if medical exam required"
          },
          {
            "name": "Nationality",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Nationality / country"
          },
          {
            "name": "State",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "State of customer"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Read CSV file DM.Customer_Detail_Table.csv from local file system using Csv.Document and File.Contents",
              "native_expressions": {
                "powerquery": "Source = Csv.Document(File.Contents(\"C:\\\\Users\\\\DELL\\\\Downloads\\\\Insurence Premium & Payout KPI Power Bi Dashboard\\\\Insurance Premium & Payout KPI Dashboard Dataset\\\\DM.Customer_Detail_Table.csv\"),[Delimiter=\",\", Columns=12, Encoding=1252, QuoteStyle=QuoteStyle.None])"
              }
            },
            {
              "order": 2,
              "step_type": "filter",
              "description": "Filter out rows where Column1 is empty or equals 'Customers Table' (removes header/metadata rows present in raw CSV)",
              "native_expressions": {
                "powerquery": "#\"Filtered Rows\" = Table.SelectRows(Source, each ([Column1] <> \"\" and [Column1] <> \"Customers Table\"))"
              }
            },
            {
              "order": 3,
              "step_type": "custom",
              "description": "Promote first qualifying row to headers (treats the current row as header row)",
              "native_expressions": {
                "powerquery": "#\"Promoted Headers\" = Table.PromoteHeaders(#\"Filtered Rows\", [PromoteAllScalars=true])"
              }
            },
            {
              "order": 4,
              "step_type": "remove_columns",
              "description": "Select only the required columns, removing any other columns from the promoted table",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(#\"Promoted Headers\",{\"Customer ID\", \"Policy Holder Name\", \"Gender\", \"Age at Entry\", \"Current Age\", \"Occupation\", \"Smoker Status\", \"Medical Exam Required\", \"Nationality\", \"State\"})"
              }
            }
          ]
        }
      },
      {
        "id": "DM_Insurance_Agent_Table",
        "name": "DM Insurance_Agent_Table",
        "table_type": "dimension",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Sales / agent dimension",
        "columns": [
          {
            "name": "Agent Code",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Agent identifier / PK"
          },
          {
            "name": "Sales Agent",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Agent name"
          },
          {
            "name": "Agent Mail",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Agent email"
          },
          {
            "name": "State",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Agent state"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Read CSV file DM.Insurance_Agent_Table.csv from local file system",
              "native_expressions": {
                "powerquery": "Source = Csv.Document(File.Contents(\"C:\\\\Users\\\\DELL\\\\Downloads\\\\Insurence Premium & Payout KPI Power Bi Dashboard\\\\Insurance Premium & Payout KPI Dashboard Dataset\\\\DM.Insurance_Agent_Table.csv\"),[Delimiter=\",\", Columns=12, Encoding=1252, QuoteStyle=QuoteStyle.None])"
              }
            },
            {
              "order": 2,
              "step_type": "custom",
              "description": "Remove top 4 rows (likely metadata/header rows before the actual header row)",
              "native_expressions": {
                "powerquery": "#\"Removed Top Rows\" = Table.Skip(Source,4)"
              }
            },
            {
              "order": 3,
              "step_type": "custom",
              "description": "Promote the first row of the remaining data to header row",
              "native_expressions": {
                "powerquery": "#\"Promoted Headers\" = Table.PromoteHeaders(#\"Removed Top Rows\", [PromoteAllScalars=true])"
              }
            },
            {
              "order": 4,
              "step_type": "remove_columns",
              "description": "Keep only the specified agent-related columns",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(#\"Promoted Headers\",{\"Agent Code\", \"Sales Agent\", \"Agent Mail\", \"State\"})"
              }
            }
          ]
        }
      },
      {
        "id": "DM_Policy_Protection_Plan",
        "name": "DM Policy_Protection_Plan",
        "table_type": "dimension",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Policy protection plan / product dimension",
        "columns": [
          {
            "name": "Policy Name",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Policy name / product"
          },
          {
            "name": "Policy Code",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Policy code / PK"
          },
          {
            "name": "Business Code",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Business code categorization"
          },
          {
            "name": "Number",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "identifier",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Auxiliary number field"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Read CSV file DM.Policy_Protection_Plan.csv from local file system",
              "native_expressions": {
                "powerquery": "Source = Csv.Document(File.Contents(\"C:\\\\Users\\\\DELL\\\\Downloads\\\\Insurence Premium & Payout KPI Power Bi Dashboard\\\\Insurance Premium & Payout KPI Dashboard Dataset\\\\DM.Policy_Protection_Plan.csv\"),[Delimiter=\",\", Columns=12, Encoding=1252, QuoteStyle=QuoteStyle.None])"
              }
            },
            {
              "order": 2,
              "step_type": "custom",
              "description": "Remove top 6 rows (drop non-data header/metadata rows)",
              "native_expressions": {
                "powerquery": "#\"Removed Top Rows\" = Table.Skip(Source,6)"
              }
            },
            {
              "order": 3,
              "step_type": "custom",
              "description": "Promote the first remaining row to be the column headers",
              "native_expressions": {
                "powerquery": "#\"Promoted Headers\" = Table.PromoteHeaders(#\"Removed Top Rows\", [PromoteAllScalars=true])"
              }
            },
            {
              "order": 4,
              "step_type": "remove_columns",
              "description": "Select only the policy protection plan columns needed",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(#\"Promoted Headers\",{\"Policy Name\", \"Policy Code\", \"Business Code\", \"Number\"})"
              }
            }
          ]
        }
      },
      {
        "id": "DM_Policy_Type",
        "name": "DM Policy_Type",
        "table_type": "dimension",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Policy type lookup",
        "columns": [
          {
            "name": "Policy Type Code",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Policy type code / PK"
          },
          {
            "name": "Policy Type",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Human-readable policy type"
          },
          {
            "name": "Number",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "identifier",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Auxiliary number field"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Read CSV file DM.Policy_Type.csv from local file system",
              "native_expressions": {
                "powerquery": "Source = Csv.Document(File.Contents(\"C:\\\\Users\\\\DELL\\\\Downloads\\\\Insurence Premium & Payout KPI Power Bi Dashboard\\\\Insurance Premium & Payout KPI Dashboard Dataset\\\\DM.Policy_Type.csv\"),[Delimiter=\",\", Columns=12, Encoding=1252, QuoteStyle=QuoteStyle.None])"
              }
            },
            {
              "order": 2,
              "step_type": "custom",
              "description": "Skip top 4 rows (remove initial metadata/extra header rows)",
              "native_expressions": {
                "powerquery": "#\"Removed Top Rows\" = Table.Skip(Source,4)"
              }
            },
            {
              "order": 3,
              "step_type": "custom",
              "description": "Promote the first row after skip to headers",
              "native_expressions": {
                "powerquery": "#\"Promoted Headers\" = Table.PromoteHeaders(#\"Removed Top Rows\", [PromoteAllScalars=true])"
              }
            },
            {
              "order": 4,
              "step_type": "remove_columns",
              "description": "Retain only specified policy type columns",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(#\"Promoted Headers\",{\"Policy Type Code\", \"Policy Type\", \"Number\"})"
              }
            }
          ]
        }
      },
      {
        "id": "DM_Regional_Manager",
        "name": "DM Regional_Manager",
        "table_type": "dimension",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Regional manager dimension",
        "columns": [
          {
            "name": "Regional Manager ID",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Regional manager identifier"
          },
          {
            "name": "Regional Manager Name",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Regional manager name"
          },
          {
            "name": "Mail",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Manager email"
          },
          {
            "name": "Region",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Region managed"
          },
          {
            "name": "States Covered",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "States under manager"
          },
          {
            "name": "Security",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Security / role metadata"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Read CSV file DM.Regional_Manager.csv from local file system",
              "native_expressions": {
                "powerquery": "Source = Csv.Document(File.Contents(\"C:\\\\Users\\\\DELL\\\\Downloads\\\\Insurence Premium & Payout KPI Power Bi Dashboard\\\\Insurance Premium & Payout KPI Dashboard Dataset\\\\DM.Regional_Manager.csv\"),[Delimiter=\",\", Columns=11, Encoding=1252, QuoteStyle=QuoteStyle.None])"
              }
            },
            {
              "order": 2,
              "step_type": "custom",
              "description": "Skip the first 4 rows (drop metadata/extra header rows)",
              "native_expressions": {
                "powerquery": "#\"Removed Top Rows\" = Table.Skip(Source,4)"
              }
            },
            {
              "order": 3,
              "step_type": "custom",
              "description": "Promote the next row to header names",
              "native_expressions": {
                "powerquery": "#\"Promoted Headers\" = Table.PromoteHeaders(#\"Removed Top Rows\", [PromoteAllScalars=true])"
              }
            },
            {
              "order": 4,
              "step_type": "remove_columns",
              "description": "Select only relevant regional manager columns",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(#\"Promoted Headers\",{\"Regional Manager ID\", \"Regional Manager Name\", \"Mail\", \"Region\", \"States Covered\", \"Security\"})"
              }
            }
          ]
        }
      },
      {
        "id": "DM_Zonal_Manager",
        "name": "DM Zonal_Manager",
        "table_type": "dimension",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Zonal manager dimension",
        "columns": [
          {
            "name": "Zonal Manager ID",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Zonal manager identifier"
          },
          {
            "name": "Zonal Manager Name",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Zonal manager name"
          },
          {
            "name": "Mail",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Manager email"
          },
          {
            "name": "Security",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Security / role metadata"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Read CSV file DM.Zonal_Manager.csv from local file system",
              "native_expressions": {
                "powerquery": "Source = Csv.Document(File.Contents(\"C:\\\\Users\\\\DELL\\\\Downloads\\\\Insurence Premium & Payout KPI Power Bi Dashboard\\\\Insurance Premium & Payout KPI Dashboard Dataset\\\\DM.Zonal_Manager.csv\"),[Delimiter=\",\", Columns=11, Encoding=1252, QuoteStyle=QuoteStyle.None])"
              }
            },
            {
              "order": 2,
              "step_type": "custom",
              "description": "Skip top 4 rows to remove non-data rows",
              "native_expressions": {
                "powerquery": "#\"Removed Top Rows\" = Table.Skip(Source,4)"
              }
            },
            {
              "order": 3,
              "step_type": "custom",
              "description": "Promote first data row to be headers",
              "native_expressions": {
                "powerquery": "#\"Promoted Headers\" = Table.PromoteHeaders(#\"Removed Top Rows\", [PromoteAllScalars=true])"
              }
            },
            {
              "order": 4,
              "step_type": "remove_columns",
              "description": "Keep only the zonal manager columns required",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(#\"Promoted Headers\",{\"Zonal Manager ID\", \"Zonal Manager Name\", \"Mail\", \"Security\"})"
              }
            }
          ]
        }
      },
      {
        "id": "FCT_Insurance_Policy_Table",
        "name": "FCT Insurance_Policy_Table",
        "table_type": "fact",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Fact table of insurance policies and related measures",
        "columns": [
          {
            "name": "Policy Number",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Policy identifier / PK"
          },
          {
            "name": "Start Date",
            "data_type": "datetime",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Policy start date"
          },
          {
            "name": "Last Paid Date",
            "data_type": "datetime",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Date of last premium payment"
          },
          {
            "name": "Tenure (Years)",
            "data_type": "integer",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Tenure in years"
          },
          {
            "name": "Date of Purchase",
            "data_type": "datetime",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Purchase date"
          },
          {
            "name": "Customer ID",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "foreign_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "FK to customer dimension"
          },
          {
            "name": "Sum Assured INR/Coverage Amount",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Coverage amount / sum assured"
          },
          {
            "name": "Premium Amount",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Premium amount for policy"
          },
          {
            "name": "Payment Frequency",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Premium payment frequency (e.g., monthly)"
          },
          {
            "name": "Loan Eligible",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Indicator if loan eligible"
          },
          {
            "name": "Loan Amount Allowed",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Allowed loan amount"
          },
          {
            "name": "Underwriting expenses",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Underwriting expenses"
          },
          {
            "name": "Sales Agent Code",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "foreign_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "FK to agent dimension"
          },
          {
            "name": "Purchase Month",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Month of purchase (text)"
          },
          {
            "name": "Purchase Quarter",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Quarter of purchase"
          },
          {
            "name": "Purchase Year",
            "data_type": "integer",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Year of purchase"
          },
          {
            "name": "Policy Anniversary Date",
            "data_type": "datetime",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Policy anniversary date"
          },
          {
            "name": "Claim ID",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "identifier",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Claim identifier (if present)"
          },
          {
            "name": "Policy Type Code",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "foreign_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "FK to policy type"
          },
          {
            "name": "Policy Code",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "foreign_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "FK to policy protection plan"
          },
          {
            "name": "Policy Status",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Current policy status"
          },
          {
            "name": "State",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "State of the policy/customer"
          },
          {
            "name": "RM ID",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "foreign_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Regional manager FK"
          },
          {
            "name": "Zonal Manager ID",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "foreign_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Zonal manager FK"
          },
          {
            "name": "Total Annual Premium",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Aggregated annual premium"
          },
          {
            "name": "Total Premium Amount",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Total premium amount"
          },
          {
            "name": "Premium Payment Duration",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Duration of premium payments"
          },
          {
            "name": "Total Premium Paid",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Premium paid to date"
          },
          {
            "name": "Total Premium Payable",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Total premium payable"
          },
          {
            "name": "Maturity Amount",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Projected maturity amount"
          },
          {
            "name": "Annualized ROI",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Annualized return on investment"
          },
          {
            "name": "Profit / Gain",
            "data_type": "decimal",
            "nullable": true,
            "hidden": false,
            "semantic_role": "measure",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": true,
            "distinct_count_high": false,
            "description": "Profit or gain amount"
          },
          {
            "name": "Tenure Date",
            "data_type": "datetime",
            "nullable": true,
            "hidden": false,
            "semantic_role": "date",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Tenure-related date"
          },
          {
            "name": "MaturedIn 5 Years",
            "data_type": "boolean",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Indicator matured in 5 years"
          },
          {
            "name": "MaturedIn 10 Years",
            "data_type": "boolean",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Indicator matured in 10 years"
          },
          {
            "name": "MaturedIn 15 Years",
            "data_type": "boolean",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Indicator matured in 15 years"
          },
          {
            "name": "MaturedIn 20 Years",
            "data_type": "boolean",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Indicator matured in 20 years"
          },
          {
            "name": "Payment Bucket",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Payment bucket / category"
          },
          {
            "name": "Region",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Geographical region"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Read CSV file FCT.Insurance_Policy_Table.csv from local file system",
              "native_expressions": {
                "powerquery": "Source = Csv.Document(File.Contents(\"C:\\\\Users\\\\DELL\\\\Downloads\\\\Insurence Premium & Payout KPI Power Bi Dashboard\\\\Insurance Premium & Payout KPI Dashboard Dataset\\\\FCT.Insurance_Policy_Table.csv\"),[Delimiter=\",\", Columns=24, Encoding=1252, QuoteStyle=QuoteStyle.None])"
              }
            },
            {
              "order": 2,
              "step_type": "custom",
              "description": "Skip top 4 rows (drop initial metadata/extra header rows)",
              "native_expressions": {
                "powerquery": "#\"Removed Top Rows\" = Table.Skip(Source,4)"
              }
            },
            {
              "order": 3,
              "step_type": "custom",
              "description": "Promote the first remaining row to column headers",
              "native_expressions": {
                "powerquery": "#\"Promoted Headers\" = Table.PromoteHeaders(#\"Removed Top Rows\", [PromoteAllScalars=true])"
              }
            },
            {
              "order": 4,
              "step_type": "remove_columns",
              "description": "Select only the set of policy-related columns required for analysis",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(#\"Promoted Headers\",{\"Policy Number\", \"Start Date\", \"Last Paid Date\", \"Tenure (Years)\", \"Date of Purchase\", \"Customer ID\", \"Sum Assured INR/Coverage Amount\", \"Premium Amount\", \"Payment Frequency\", \"Loan Eligible\", \"Loan Amount Allowed\", \"Underwriting expenses\", \"Sales Agent Code\", \"Purchase Month\", \"Purchase Quarter\", \"Purchase Year\", \"Policy Anniversary Date\", \"Claim ID\", \"Policy Type Code\", \"Policy Code\", \"Policy Status\", \"State\", \"RM ID\", \"Zonal Manager ID\"})"
              }
            },
            {
              "order": 5,
              "step_type": "change_type",
              "description": "Change the data types of selected columns (text, date, number, Int64 as specified)",
              "native_expressions": {
                "powerquery": "#\"Changed Type\" = Table.TransformColumnTypes(#\"Removed Other Columns\",{{\"Policy Number\", type text}, {\"Start Date\", type date}, {\"Last Paid Date\", type date}, {\"Tenure (Years)\", Int64.Type}, {\"Date of Purchase\", type date}, {\"Customer ID\", type text}, {\"Sum Assured INR/Coverage Amount\", type number}, {\"Premium Amount\", type number}, {\"Payment Frequency\", type text}, {\"Loan Eligible\", type text}, {\"Loan Amount Allowed\", type number}, {\"Underwriting expenses\", type number}, {\"Sales Agent Code\", type text}, {\"Purchase Month\", type text}, {\"Purchase Quarter\", type text}, {\"Purchase Year\", Int64.Type}, {\"Policy Anniversary Date\", type date}, {\"Claim ID\", type text}, {\"Policy Type Code\", type text}, {\"Policy Code\", type text}, {\"Policy Status\", type text}, {\"State\", type text}, {\"RM ID\", type text}, {\"Zonal Manager ID\", type text}})"
              }
            },
            {
              "order": 6,
              "step_type": "merge",
              "description": "Left join the changed policy table to the Hirarachy Table on State -> States Covered to bring in region information",
              "native_expressions": {
                "powerquery": "#\"Merged Queries\" = Table.NestedJoin(#\"Changed Type\", {\"State\"}, #\"Hirarachy Table\", {\"States Covered\"}, \"Hirarachy Table\", JoinKind.LeftOuter)"
              }
            },
            {
              "order": 7,
              "step_type": "custom",
              "description": "Expand the joined Hirarachy Table column to extract the Region column into the policy table",
              "native_expressions": {
                "powerquery": "#\"Expanded Hirarachy Table\" = Table.ExpandTableColumn(#\"Merged Queries\", \"Hirarachy Table\", {\"Region\"}, {\"Hirarachy Table.Region\"})"
              }
            },
            {
              "order": 8,
              "step_type": "rename",
              "description": "Rename the expanded Hirarachy Table.Region column to Region",
              "native_expressions": {
                "powerquery": "#\"Renamed Columns\" = Table.RenameColumns(#\"Expanded Hirarachy Table\",{{\"Hirarachy Table.Region\", \"Region\"}})"
              }
            }
          ]
        }
      },
      {
        "id": "Hirarachy_Table",
        "name": "Hirarachy Table",
        "table_type": "dimension",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Hierarchy table (regional/zonal manager info) - appears duplicate of regional manager",
        "columns": [
          {
            "name": "Regional Manager ID",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "primary_key",
            "used_in_relationships": true,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": true,
            "description": "Regional manager identifier"
          },
          {
            "name": "Regional Manager Name",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Regional manager name"
          },
          {
            "name": "Mail",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Manager email"
          },
          {
            "name": "Region",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Region"
          },
          {
            "name": "States Covered",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "States covered by manager"
          },
          {
            "name": "Security",
            "data_type": "string",
            "nullable": true,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": false,
            "used_in_filters": false,
            "used_in_groupby": false,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Security / role metadata"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Reference the DM Regional_Manager query as the source (uses the processed regional manager table)",
              "native_expressions": {
                "powerquery": "Source = #\"DM Regional_Manager\""
              }
            },
            {
              "order": 2,
              "step_type": "split_column",
              "description": "Split the 'States Covered' comma-delimited list into rows (split into list then expand the list column into separate rows), effectively normalizing many-states-per-manager into one row per state",
              "native_expressions": {
                "powerquery": "#\"Split Column by Delimiter\" = Table.ExpandListColumn(Table.TransformColumns(Source, {{\"States Covered\", Splitter.SplitTextByDelimiter(\",\", QuoteStyle.Csv), let itemType = (type nullable text) meta [Serialized.Text = true] in type {itemType}}}), \"States Covered\")"
              }
            }
          ]
        }
      },
      {
        "id": "Region",
        "name": "Region",
        "table_type": "lookup",
        "source_data_source_id": null,
        "is_materialized": true,
        "description": "Region lookup table",
        "columns": [
          {
            "name": "Region",
            "data_type": "string",
            "nullable": false,
            "hidden": false,
            "semantic_role": "dimension",
            "used_in_relationships": true,
            "used_in_filters": true,
            "used_in_groupby": true,
            "used_in_calculations": false,
            "distinct_count_high": false,
            "description": "Region name / key"
          }
        ],
        "ingestion": {
          "steps": [
            {
              "order": 1,
              "step_type": "read_source",
              "description": "Reference the Hirarachy Table query as source",
              "native_expressions": {
                "powerquery": "Source = #\"Hirarachy Table\""
              }
            },
            {
              "order": 2,
              "step_type": "remove_columns",
              "description": "Select only the Region column from the Hirarachy Table",
              "native_expressions": {
                "powerquery": "#\"Removed Other Columns\" = Table.SelectColumns(Source,{\"Region\"})"
              }
            },
            {
              "order": 3,
              "step_type": "group",
              "description": "Remove duplicate regions by returning distinct Region values",
              "native_expressions": {
                "powerquery": "#\"Removed Duplicates\" = Table.Distinct(#\"Removed Other Columns\")"
              }
            }
          ]
        }
      }
    ],
    "relationships": [
      {
        "id": "rel_fct_insurance_policy_table_dm_customer_detail_table",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Customer ID",
        "right_table_id": "tbl_dm_customer_detail_table",
        "right_column": "Customer ID",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "bidirectional",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      },
      {
        "id": "rel_fct_insurance_policy_table_dm_insurance_agent_table",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Sales Agent Code",
        "right_table_id": "tbl_dm_insurance_agent_table",
        "right_column": "Agent Code",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "bidirectional",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      },
      {
        "id": "rel_fct_insurance_policy_table_dm_zonal_manager",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Zonal Manager ID",
        "right_table_id": "tbl_dm_zonal_manager",
        "right_column": "Zonal Manager ID",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "bidirectional",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      },
      {
        "id": "rel_fct_insurance_policy_table_dm_policy_type",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Policy Type Code",
        "right_table_id": "tbl_dm_policy_type",
        "right_column": "Policy Type Code",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "bidirectional",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      },
      {
        "id": "rel_fct_insurance_policy_table_dm_regional_manager",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "RM ID",
        "right_table_id": "tbl_dm_regional_manager",
        "right_column": "Regional Manager ID",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "bidirectional",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      },
      {
        "id": "rel_fct_insurance_policy_table_dm_policy_protection_plan",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Policy Code",
        "right_table_id": "tbl_dm_policy_protection_plan",
        "right_column": "Policy Code",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "bidirectional",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      },
      {
        "id": "rel_fct_insurance_policy_table_start_date",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Start Date",
        "right_table_id": null,
        "right_column": null,
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "single",
        "enforced_integrity": false,
        "relationship_type": "date_relationship",
        "note": "Auto-generated Power BI local date table - no portable equivalent; use a shared date dimension when migrating"
      },
      {
        "id": "rel_fct_insurance_policy_table_last_paid_date",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Last Paid Date",
        "right_table_id": null,
        "right_column": null,
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "single",
        "enforced_integrity": false,
        "relationship_type": "date_relationship",
        "note": "Auto-generated Power BI local date table - no portable equivalent; use a shared date dimension when migrating"
      },
      {
        "id": "rel_fct_insurance_policy_table_date_of_purchase",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Date of Purchase",
        "right_table_id": null,
        "right_column": null,
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "single",
        "enforced_integrity": false,
        "relationship_type": "date_relationship",
        "note": "Auto-generated Power BI local date table - no portable equivalent; use a shared date dimension when migrating"
      },
      {
        "id": "rel_fct_insurance_policy_table_policy_anniversary_date",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Policy Anniversary Date",
        "right_table_id": null,
        "right_column": null,
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "single",
        "enforced_integrity": false,
        "relationship_type": "date_relationship",
        "note": "Auto-generated Power BI local date table - no portable equivalent; use a shared date dimension when migrating"
      },
      {
        "id": "rel_fct_insurance_policy_table_tenure_date",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Tenure Date",
        "right_table_id": null,
        "right_column": null,
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "single",
        "enforced_integrity": false,
        "relationship_type": "date_relationship",
        "note": "Auto-generated Power BI local date table - no portable equivalent; use a shared date dimension when migrating"
      },
      {
        "id": "rel_hirarachy_table_dm_regional_manager",
        "left_table_id": "tbl_hirarachy_table",
        "left_column": "Regional Manager ID",
        "right_table_id": "tbl_dm_regional_manager",
        "right_column": "Regional Manager ID",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "single",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      },
      {
        "id": "rel_fct_insurance_policy_table_region",
        "left_table_id": "tbl_fct_insurance_policy_table",
        "left_column": "Region",
        "right_table_id": "tbl_region",
        "right_column": "Region",
        "cardinality": "many_to_one",
        "join_type": "left",
        "active": true,
        "filter_direction": "bidirectional",
        "enforced_integrity": false,
        "relationship_type": "dimension_lookup",
        "note": null
      }
    ],
    "calculations": [
      {
        "id": "calc_cagr_percent",
        "name": "CAGR (%)",
        "description": null,
        "semantic_type": "growth_rate",
        "aggregation_behavior": "non_additive",
        "data_type": "decimal",
        "format_string": "0.00%",
        "is_base_measure": false,
        "reusable": false,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Total Premium Paid",
          "FCT Insurance_Policy_Table.Maturity Amount",
          "FCT Insurance_Policy_Table.Tenure (Years)"
        ],
        "depends_on_measures": [],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "growth",
            "cagr"
          ]
        },
        "expressions": {
          "dax": "\n VAR InitialValue = SUM('FCT Insurance_Policy_Table'[Total Premium Paid])\n VAR FinalValue = SUM('FCT Insurance_Policy_Table'[Maturity Amount])\n VAR Years = MAX('FCT Insurance_Policy_Table'[Tenure (Years)])\n\n RETURN\n IF(InitialValue>0 && Years>0,\n (POWER(DIVIDE(FinalValue,InitialValue,0), 1/Years)-1),BLANK())"
        }
      },
      {
        "id": "calc_underwritting_expense",
        "name": "Underwritting Expense",
        "description": null,
        "semantic_type": "sum",
        "aggregation_behavior": "additive",
        "data_type": "decimal",
        "format_string": "#,##0.00",
        "is_base_measure": true,
        "reusable": true,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Underwriting expenses"
        ],
        "depends_on_measures": [],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "expenses",
            "base"
          ]
        },
        "expressions": {
          "dax": "SUM('FCT Insurance_Policy_Table'[Underwriting expenses])"
        }
      },
      {
        "id": "calc_annual_amount_growth",
        "name": "Annual Amount Growth",
        "description": null,
        "semantic_type": "ratio",
        "aggregation_behavior": "non_additive",
        "data_type": "decimal",
        "format_string": null,
        "is_base_measure": true,
        "reusable": true,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Profit / Gain",
          "FCT Insurance_Policy_Table.Tenure (Years)"
        ],
        "depends_on_measures": [],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "growth",
            "base"
          ]
        },
        "expressions": {
          "dax": "DIVIDE(SUM('FCT Insurance_Policy_Table'[Profit / Gain]), SUM('FCT Insurance_Policy_Table'[Tenure (Years)]),0)"
        }
      },
      {
        "id": "calc_annual_roi",
        "name": "Annual ROI",
        "description": null,
        "semantic_type": "ratio",
        "aggregation_behavior": "non_additive",
        "data_type": "decimal",
        "format_string": "0.00%",
        "is_base_measure": false,
        "reusable": false,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Total Annual Premium"
        ],
        "depends_on_measures": [
          "Annual Amount Growth"
        ],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "roi",
            "growth"
          ]
        },
        "expressions": {
          "dax": "DIVIDE([Annual Amount Growth], SUM('FCT Insurance_Policy_Table'[Total Annual Premium]))"
        }
      },
      {
        "id": "calc_annual_growth_rate_fixed",
        "name": "Annual Growth Rate Fixed",
        "description": null,
        "semantic_type": "ratio",
        "aggregation_behavior": "non_additive",
        "data_type": "decimal",
        "format_string": "0.00%",
        "is_base_measure": false,
        "reusable": false,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Total Annual Premium"
        ],
        "depends_on_measures": [
          "Annual Amount Growth"
        ],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "growth",
            "fixed"
          ]
        },
        "expressions": {
          "dax": "DIVIDE([Annual Amount Growth],SUM('FCT Insurance_Policy_Table'[Total Annual Premium]),0)"
        }
      },
      {
        "id": "calc_total_annual_premium",
        "name": "Total Annual_Premium",
        "description": null,
        "semantic_type": "sum",
        "aggregation_behavior": "additive",
        "data_type": "decimal",
        "format_string": "#,##0.00",
        "is_base_measure": true,
        "reusable": true,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Total Annual Premium"
        ],
        "depends_on_measures": [],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "premium",
            "base"
          ]
        },
        "expressions": {
          "dax": "SUM('FCT Insurance_Policy_Table'[Total Annual Premium])"
        }
      },
      {
        "id": "calc_total_premium_amount",
        "name": "Total Premium_Amount",
        "description": null,
        "semantic_type": "sum",
        "aggregation_behavior": "additive",
        "data_type": "decimal",
        "format_string": "#,##0.00",
        "is_base_measure": true,
        "reusable": true,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Total Premium Amount"
        ],
        "depends_on_measures": [],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "premium",
            "base"
          ]
        },
        "expressions": {
          "dax": "SUM('FCT Insurance_Policy_Table'[Total Premium Amount])"
        }
      },
      {
        "id": "calc_total_premium_paid",
        "name": "Total Premium_Paid",
        "description": null,
        "semantic_type": "sum",
        "aggregation_behavior": "additive",
        "data_type": "decimal",
        "format_string": "#,##0.00",
        "is_base_measure": true,
        "reusable": true,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Total Premium Paid"
        ],
        "depends_on_measures": [],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "premium",
            "base"
          ]
        },
        "expressions": {
          "dax": "SUM('FCT Insurance_Policy_Table'[Total Premium Paid])"
        }
      },
      {
        "id": "calc_total_premium_payable",
        "name": "Total Premium_Payable",
        "description": null,
        "semantic_type": "sum",
        "aggregation_behavior": "additive",
        "data_type": "decimal",
        "format_string": "#,##0.00",
        "is_base_measure": true,
        "reusable": true,
        "depends_on_columns": [
          "FCT Insurance_Policy_Table.Total Premium Payable"
        ],
        "depends_on_measures": [],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "premium",
            "base"
          ]
        },
        "expressions": {
          "dax": "SUM('FCT Insurance_Policy_Table'[Total Premium Payable])"
        }
      },
      {
        "id": "calc_percent_premium_paid",
        "name": "% Premium Paid",
        "description": null,
        "semantic_type": "ratio",
        "aggregation_behavior": "non_additive",
        "data_type": "decimal",
        "format_string": "0.00%",
        "is_base_measure": false,
        "reusable": false,
        "depends_on_columns": [],
        "depends_on_measures": [
          "Total Premium_Paid",
          "Total Premium_Amount"
        ],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "premium",
            "ratio"
          ]
        },
        "expressions": {
          "dax": "DIVIDE([Total Premium_Paid],[Total Premium_Amount],0)"
        }
      },
      {
        "id": "calc_percent_premium_payable",
        "name": "% Premium Payable",
        "description": null,
        "semantic_type": "ratio",
        "aggregation_behavior": "non_additive",
        "data_type": "decimal",
        "format_string": "0.00%",
        "is_base_measure": false,
        "reusable": false,
        "depends_on_columns": [],
        "depends_on_measures": [
          "Total Premium_Payable",
          "Total Premium_Amount"
        ],
        "display": {
          "folder": null,
          "hidden": false,
          "tags": [
            "premium",
            "ratio"
          ]
        },
        "expressions": {
          "dax": "DIVIDE([Total Premium_Payable],[Total Premium_Amount],0)"
        }
      }
    ],
    "kpi_lineage": [
        {
          "kpi_name": "CAGR (%)",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Compound Annual Growth Rate computed from Total Premium Paid to Maturity Amount over Tenure (Years). Returns blank if initial value or years are not positive.",
          "formula": " \n VAR InitialValue = SUM('FCT Insurance_Policy_Table'[Total Premium Paid])\n VAR FinalValue = SUM('FCT Insurance_Policy_Table'[Maturity Amount])\n VAR Years = MAX('FCT Insurance_Policy_Table'[Tenure (Years)])\n\n RETURN\n IF(InitialValue>0 && Years>0,\n (POWER(DIVIDE(FinalValue,InitialValue,0), 1/Years)-1),BLANK())",
          "semantic_type": "growth_rate",
          "aggregation_behavior": "non_additive",
          "data_type": "decimal",
          "format_string": "0.00%",
          "is_base_measure": false,
          "reusable": true,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "growth",
              "cagr"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Total Premium Paid",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            },
            {
              "column_name": "Maturity Amount",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            },
            {
              "column_name": "Tenure (Years)",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": []
        },
        {
          "kpi_name": "Underwritting Expense",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Sum of underwriting expenses.",
          "formula": "SUM('FCT Insurance_Policy_Table'[Underwriting expenses])",
          "semantic_type": "sum",
          "aggregation_behavior": "additive",
          "data_type": "decimal",
          "format_string": "#,##0.00",
          "is_base_measure": true,
          "reusable": true,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "underwriting",
              "base"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Underwriting expenses",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": []
        },
        {
          "kpi_name": "Annual Amount Growth",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Annual amount growth computed as Profit / Gain divided by Tenure (Years).",
          "formula": "DIVIDE(SUM('FCT Insurance_Policy_Table'[Profit / Gain]), SUM('FCT Insurance_Policy_Table'[Tenure (Years)]),0)",
          "semantic_type": "ratio",
          "aggregation_behavior": "non_additive",
          "data_type": "decimal",
          "format_string": "#,##0.00",
          "is_base_measure": true,
          "reusable": true,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "growth",
              "base"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Profit / Gain",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            },
            {
              "column_name": "Tenure (Years)",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": []
        },
        {
          "kpi_name": "Annual ROI",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Annual return on investment: Annual Amount Growth divided by Total Annual Premium.",
          "formula": "DIVIDE([Annual Amount Growth], SUM('FCT Insurance_Policy_Table'[Total Annual Premium]))",
          "semantic_type": "ratio",
          "aggregation_behavior": "non_additive",
          "data_type": "decimal",
          "format_string": "0.00%",
          "is_base_measure": false,
          "reusable": false,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "roi",
              "ratio"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Total Annual Premium",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": [
            {
              "kpi_name": "Annual Amount Growth",
              "found": true,
              "semantic_type": "ratio",
              "aggregation_behavior": "non_additive",
              "data_type": "decimal"
            }
          ]
        },
        {
          "kpi_name": "Annual Growth Rate Fixed",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Annual growth rate (fixed) computed as Annual Amount Growth divided by Total Annual Premium with zero safe divide.",
          "formula": "DIVIDE([Annual Amount Growth],SUM('FCT Insurance_Policy_Table'[Total Annual Premium]),0)",
          "semantic_type": "ratio",
          "aggregation_behavior": "non_additive",
          "data_type": "decimal",
          "format_string": "0.00%",
          "is_base_measure": false,
          "reusable": false,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "growth",
              "ratio"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Total Annual Premium",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": [
            {
              "kpi_name": "Annual Amount Growth",
              "found": true,
              "semantic_type": "ratio",
              "aggregation_behavior": "non_additive",
              "data_type": "decimal"
            }
          ]
        },
        {
          "kpi_name": "Total Annual_Premium",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Sum of Total Annual Premium.",
          "formula": "SUM('FCT Insurance_Policy_Table'[Total Annual Premium])",
          "semantic_type": "sum",
          "aggregation_behavior": "additive",
          "data_type": "decimal",
          "format_string": "#,##0.00",
          "is_base_measure": true,
          "reusable": true,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "premium",
              "base"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Total Annual Premium",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": []
        },
        {
          "kpi_name": "Total Premium_Amount",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Sum of Total Premium Amount.",
          "formula": "SUM('FCT Insurance_Policy_Table'[Total Premium Amount])",
          "semantic_type": "sum",
          "aggregation_behavior": "additive",
          "data_type": "decimal",
          "format_string": "#,##0.00",
          "is_base_measure": true,
          "reusable": true,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "premium",
              "base"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Total Premium Amount",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": []
        },
        {
          "kpi_name": "Total Premium_Paid",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Sum of Total Premium Paid.",
          "formula": "SUM('FCT Insurance_Policy_Table'[Total Premium Paid])",
          "semantic_type": "sum",
          "aggregation_behavior": "additive",
          "data_type": "decimal",
          "format_string": "#,##0.00",
          "is_base_measure": true,
          "reusable": true,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "premium",
              "base"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Total Premium Paid",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": []
        },
        {
          "kpi_name": "Total Premium_Payable",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Sum of Total Premium Payable.",
          "formula": "SUM('FCT Insurance_Policy_Table'[Total Premium Payable])",
          "semantic_type": "sum",
          "aggregation_behavior": "additive",
          "data_type": "decimal",
          "format_string": "#,##0.00",
          "is_base_measure": true,
          "reusable": true,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "premium",
              "base"
            ]
          },
          "depends_on_columns": [
            {
              "column_name": "Total Premium Payable",
              "table_name": "FCT Insurance_Policy_Table",
              "table_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)$FCT.Insurance_Policy_Table.csv(datasource)",
              "table_type": "fact",
              "data_source": {
                "name": "FCT.Insurance_Policy_Table.csv",
                "source_type": "CSV",
                "connection_mode": "import",
                "path": "C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\Insurance Premium & Payout KPI Dashboard Dataset\\FCT.Insurance_Policy_Table.csv"
              },
              "report": {
                "tool": "Power BI",
                "report_name": "Tru Secure CreDebit Dashboard",
                "model_id": "23ae2cb4-ed9b-4dc0-a835-822f59b2a56c"
              }
            }
          ],
          "depends_on_measures": []
        },
        {
          "kpi_name": "% Premium Paid",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Percentage of premium paid = Total Premium_Paid / Total Premium_Amount (safe divide).",
          "formula": "DIVIDE([Total Premium_Paid],[Total Premium_Amount],0)",
          "semantic_type": "ratio",
          "aggregation_behavior": "non_additive",
          "data_type": "decimal",
          "format_string": "0.00%",
          "is_base_measure": false,
          "reusable": false,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "premium",
              "ratio"
            ]
          },
          "depends_on_columns": [],
          "depends_on_measures": [
            {
              "kpi_name": "Total Premium_Paid",
              "found": true,
              "semantic_type": "sum",
              "aggregation_behavior": "additive",
              "data_type": "decimal"
            },
            {
              "kpi_name": "Total Premium_Amount",
              "found": true,
              "semantic_type": "sum",
              "aggregation_behavior": "additive",
              "data_type": "decimal"
            }
          ]
        },
        {
          "kpi_name": "% Premium Payable",
          "kpi_id": "powerbi(toolname)$Tru Secure CreDebit Dashboard(filename)",
          "description": "Percentage of premium payable = Total Premium_Payable / Total Premium_Amount (safe divide).",
          "formula": "DIVIDE([Total Premium_Payable],[Total Premium_Amount],0)",
          "semantic_type": "ratio",
          "aggregation_behavior": "non_additive",
          "data_type": "decimal",
          "format_string": "0.00%",
          "is_base_measure": false,
          "reusable": false,
          "display": {
            "folder": "FCT Insurance_Policy_Table",
            "hidden": false,
            "tags": [
              "premium",
              "ratio"
            ]
          },
          "depends_on_columns": [],
          "depends_on_measures": [
            {
              "kpi_name": "Total Premium_Payable",
              "found": true,
              "semantic_type": "sum",
              "aggregation_behavior": "additive",
              "data_type": "decimal"
            },
            {
              "kpi_name": "Total Premium_Amount",
              "found": true,
              "semantic_type": "sum",
              "aggregation_behavior": "additive",
              "data_type": "decimal"
            }
          ]
        }
      ],
     "executivesummary": "Executive Summary\n\nPurpose and scope\n- The workbook titled \"Secure Debit PBI\" is a comprehensive Power BI data model designed for insurance performance analytics, focusing on premium and payout KPIs. It is built on a collection of imported CSV files and follows a star-schema architecture to support analysis across customer demographics, agent performance, and product profitability. The model incorporates advanced DAX calculations for growth metrics like CAGR and ROI, and utilizes Power Query transformations to normalize complex geographical hierarchies.\n\nSource systems and topology\n- Source: Local CSV files on a developer workstation:\n  - Base Path: C:\\Users\\DELL\\Downloads\\Insurence Premium & Payout KPI Power Bi Dashboard\\...\n  - Key Files: FCT.Insurance_Policy_Table.csv, DM.Customer_Detail_Table.csv, DM.Insurance_Agent_Table.csv, DM.Policy_Protection_Plan.csv, DM.Policy_Type.csv, DM.Regional_Manager.csv, DM.Zonal_Manager.csv\n  - Data access mode: Import mode (materialized VertiPaq model).\n  - Topology: Star-schema centered on a policy fact table with lookup relationships to customer, agent, product, and manager dimensions.\n\nHigh-level structure and key components\n- Primary table (fact): FCT Insurance_Policy_Table — Materialized at the policy grain. It contains financial measures (Premium Amount, Sum Assured, Expenses), transaction dates (Start Date, Last Paid Date), and foreign keys for dimensional joins.\n- Primary Dimensions:\n  - Customer Detail: Master data for policy holders including demographics (Gender, Age, Occupation) and risk markers (Smoker Status).\n  - Insurance Agent: Sales agent identifiers and contact information.\n  - Product Tables: DM Policy_Protection_Plan (plan-level) and DM Policy_Type (category-level).\n  - Manager Tables: Regional and Zonal manager mapping for organizational reporting.\n- Derived Tables & Logic:\n  - Hirarachy Table: A bridge table created by splitting comma-delimited 'States Covered' from the Regional Manager source into separate rows.\n  - Region Table: A distinct lookup table for geographical regions derived from the hierarchy.\n- Calculations: Advanced DAX measures for performance tracking, including Compound Annual Growth Rate (CAGR), Annualized ROI, and collection ratios.\n\nSource and ingestion details\n\nIngestion steps (sequenced)\n1. Fact Table Ingestion (FCT Insurance_Policy_Table)\n   - Action: Read CSV, skip 4 metadata rows, promote headers, and coerce types for 24 columns.\n   - Native Expression: Table.Skip(Source,4) followed by Table.TransformColumnTypes.\n   - Note: Includes a nested join to the Hirarachy Table to resolve Region names at the row level.\n\n2. Regional Manager Normalization (Hirarachy Table)\n   - Action: References the Regional Manager query and expands the 'States Covered' column.\n   - Power Query logic: Table.ExpandListColumn(Table.TransformColumns(Source, {{\"States Covered\", Splitter.SplitTextByDelimiter(\",\", ...)}})).\n   - Note: This transforms a denormalized string list into a relational format suitable for joins.\n\n3. Dimension Cleanup (Customer, Agent, Plan, Type)\n   - Action: Standard patterns of skipping metadata headers (usually 4 to 6 rows), promoting headers, and selecting required columns.\n\n4. Region Lookup Extraction\n   - Action: Derived from the Hirarachy Table by selecting the Region column and removing duplicates to create a clean filter dimension.\n\nLogical data model and grain\n\nPrimary fact: FCT Insurance_Policy_Table\n- Grain: One record per individual insurance policy.\n- Measures:\n  - Premium Amount, Total Annual Premium, Total Premium Paid: Decimal/Currency tracking.\n  - Sum Assured INR/Coverage Amount: Policy value.\n  - Underwriting expenses: Cost tracking.\n  - Tenure (Years): Duration of the policy.\n- Primary Keys and Foreign Keys:\n  - Policy Number: Primary key for the fact.\n  - Customer ID, Sales Agent Code, RM ID, Zonal Manager ID, Policy Code, Policy Type Code: Foreign keys for dimension lookups.\n- Date Dimensions: Start Date, Date of Purchase, Last Paid Date, and Policy Anniversary Date.\n\nCalculated Measures (DAX specifics)\n- CAGR (%): Calculates compound growth using: (POWER(DIVIDE(MaturityValue, InitialValue, 0), 1/Years)-1).\n- Annual ROI: Calculated as DIVIDE([Annual Amount Growth], SUM('Total Annual Premium')).\n- % Premium Paid: DIVIDE([Total Premium_Paid], [Total Premium_Amount], 0) to monitor collection health.\n\nRelationships and Schema\n- Schema Type: Star Schema.\n- Join Type: Most relationships are Many-to-One from the fact table to dimensions using Left Joins.\n- Filter Direction: Primarily 'Bidirectional' for the core dimension lookups, which may impact performance in large datasets.\n- Date Logic: Uses Power BI local auto-date tables for time intelligence, which are not shared across tables.\n\nData quality, integrity and risk analysis\n\nKey data quality risks identified\n1. Source Locality: The model uses hardcoded local file paths (C:\\Users\\DELL\\...). This prevents successful refresh in Power BI Service without a Data Gateway and networked file path conversion.\n2. String-Based Normalization: The Hirarachy Table relies on the presence of a comma delimiter in 'States Covered'. If the source data format changes, the Regional reporting will break.\n3. Bidirectional Filters: Multiple bidirectional filters are active. This can lead to ambiguous filter paths and performance bottlenecks during high-volume query processing.\n4. Lack of Central Date Table: Reliance on auto-generated local date tables makes cross-table date filtering and advanced time-intelligence (YTD, YoY) less efficient and harder to maintain.\n5. Null Handling: While DAX uses DIVIDE for safe division, raw premium sums do not have explicit COALESCE handling to manage nulls from the source CSVs.\n\nMigration and optimization recommendations\n\n1. Centralize Data Storage: Move local CSV files to a cloud-based folder (SharePoint/OneDrive) or ingest into a relational database (SQL Server/Snowflake) to enable automated refresh.\n2. Push Normalization Upstream: Move the 'States Covered' split logic and 'Region' extraction into an SQL view or ETL job. This simplifies the Power BI model and improves refresh speed.\n3. Implement a Calendar Dimension: Replace auto-date tables with a single, central Date/Calendar dimension to enable consistent time-intelligence across all date fields (Start Date, Paid Date, etc.).\n4. Optimize Relationships: Convert 'Bidirectional' filters to 'Single' direction wherever business logic permits to optimize the VertiPaq engine.\n5. Surrogate Keys: If moving to a data warehouse, replace string-based IDs (Policy Code, Customer ID) with integer surrogate keys to improve join performance.\n\nImplementation plan\n\nPhase 1 — Ingestion Stability\n- Relocate CSVs to a networked drive or cloud storage.\n- Update Power Query source paths and verify the Data Gateway connection.\n\nPhase 2 — Model Cleanup\n- Create a proper Date table and link it to the fact table's primary dates.\n- Consolidate the Manager and Hierarchy logic into a single flattened dimension if possible.\n- Set relationship directions to 'Single'.\n\nPhase 3 — Operational Monitoring\n- Implement row counts and null-rate checks in the ETL pipeline.\n- Monitor refresh times on the fact table as policy volume grows, considering incremental refresh if needed."
  };
  export default sampleModel;