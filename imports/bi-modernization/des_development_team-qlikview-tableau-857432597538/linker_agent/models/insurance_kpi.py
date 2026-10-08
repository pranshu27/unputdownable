import pandas as pd
from glob import glob
import re
from typing import List, Dict
from pydantic import BaseModel


class InsuranceKpi(BaseModel):
    title: str
    kpi: str
    business_definition: str
    technical_definition: str
    kpi_owner: str
    primary_source_systems: str
    attributes: List[str]
    regulatory_relevance: str
    reporting_frequency: str
    business_benefit: str
    benchmark_auto_PC: str
    benchmark_home_PC: str
    benchmark_commercial_PC: str
    industry_benchmark: str



def extract_text_in_parentheses(text: str) -> str:
    match = re.search(r"\((.*?)\)", text)
    return match.group(1) if match else "unknown"


def read_csv_safe(file_path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(file_path, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(file_path, encoding="latin1")


def safe_str(value) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def row_to_insurance_kpi(row: pd.Series) -> InsuranceKpi:
    return InsuranceKpi(
        title=safe_str(row.get("KPI")),
        kpi=safe_str(row.get("KPI")),
        business_definition=safe_str(row.get("Business Definition")),
        technical_definition=safe_str(row.get("Technical Definition / Formula")),
        kpi_owner=safe_str(row.get("KPI Owner")),
        primary_source_systems=safe_str(row.get("Primary Source Systems")),
        attributes=[
            a.strip()
            for a in safe_str(
                row.get("Key Tables / Attributes / Services")
            ).split(",")
            if a.strip()
        ],
        regulatory_relevance=safe_str(
            row.get(
                "Regulatory Relevance (NAIC / RBC / MCAS / ORSA / CMS / ERISA / SEC)"
            )
        ),
        reporting_frequency=safe_str(row.get("Reporting Frequency")),
        business_benefit=safe_str(row.get("Business Benefit")),
        benchmark_auto_PC=safe_str(row.get("Benchmark - Auto (P&C)")),
        benchmark_home_PC=safe_str(row.get("Benchmark - Home (P&C)")),
        benchmark_commercial_PC=safe_str(row.get("Benchmark - Commercial (P&C)")),
        industry_benchmark=safe_str(row.get("Industry Benchmark / Target")),
    )


def get_kpi_list() -> Dict[str, List[str]]:
    """
    Returns a dictionary with sheet names as keys and list of KPI names as values.
    """
    sheets: Dict[str, pd.DataFrame] = {}
    csv_files = glob("./asserts/Insurance/*.csv")
    
    if not csv_files:
        raise FileNotFoundError("No CSV files found in ./asserts/Insurance/")
    
    # Read all files
    for file in csv_files:
        sheet_name = extract_text_in_parentheses(file)
        df = read_csv_safe(file)
        sheets[sheet_name] = df
    
    # Extract KPIs
    kpi_dict = {}
    for sheet_name, df in sheets.items():
        kpis = []
        if 'KPI' in df.columns:
            for kpi in df['KPI']:
                kpi_str = safe_str(kpi).strip()
                if kpi_str:
                    kpis.append(kpi_str)
        kpi_dict[sheet_name] = kpis
    # print(kpi_dict["P&C"])
    return kpi_dict


def get_all_kpis() -> Dict[str, List[InsuranceKpi]]:
    """
    Returns a dictionary with sheet names as keys and list of InsuranceKpi objects as values.
    """
    sheets: Dict[str, pd.DataFrame] = {}
    all_columns = set()
    
    csv_files = glob("./asserts/Insurance/*.csv")
    
    if not csv_files:
        raise FileNotFoundError("No CSV files found in ./asserts/Insurance/")
    
    # First pass: read files & collect columns
    for file in csv_files:
        sheet_name = extract_text_in_parentheses(file)
        df = read_csv_safe(file)
        sheets[sheet_name] = df
        all_columns.update(df.columns)
    
    # Normalize column order
    all_columns = sorted(all_columns)
    
    # Second pass: align columns
    for sheet_name, df in sheets.items():
        sheets[sheet_name] = df.reindex(columns=all_columns)
    
    # Convert to InsuranceKpi objects
    insurance_kpis_by_sheet: Dict[str, List[InsuranceKpi]] = {}
    
    for sheet_name, df in sheets.items():
        records = []
        for _, row in df.iterrows():
            try:
                kpi_obj = row_to_insurance_kpi(row)
                # print(kpi_obj)
                if kpi_obj.kpi.strip():
                    records.append(kpi_obj)
            except Exception as e:
                print(f"❌ Failed to parse row in {sheet_name}: {e}")
        insurance_kpis_by_sheet[sheet_name] = records
    return insurance_kpis_by_sheet


def load_insurance_kpis() -> list:
    """
    Returns a flat list of all InsuranceKpi objects across all sheets.
    Convenience wrapper over get_all_kpis() for use by the linker.
    """
    all_kpis_by_sheet = get_all_kpis()
    flat: list = []
    for kpis in all_kpis_by_sheet.values():
        flat.extend(kpis)
    return flat