"""
Convert SINAN occurrence Excel data to JSON for the metrics dashboard.

Run this script to generate `public/data/occurrence_metrics.json`.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = PROJECT_ROOT / "Occurence_sinannet_cnv_animaisbr181817177_37_144_5.csv.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "public" / "data" / "occurrence_metrics.json"
YEARS = list(range(2015, 2025))


def normalize_label(value: Any) -> str:
    """Normalize labels for resilient column matching."""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.strip().lower()
    return re.sub(r"\s+", " ", text)


def find_column(columns: list[str], predicate: Any, description: str) -> str:
    """Find a column by predicate, raising a clear error when missing."""
    for column in columns:
        if predicate(normalize_label(column)):
            return column
    raise KeyError(f"Could not find required column for: {description}")


def to_int(value: Any) -> int:
    """Convert any numeric-like value to a safe integer."""
    if pd.isna(value):
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if math.isnan(number) or math.isinf(number):
        return 0
    return int(round(number))


def to_float(value: Any, precision: int = 3) -> float:
    """Convert any numeric-like value to a rounded float."""
    if pd.isna(value):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if math.isnan(number) or math.isinf(number):
        return 0.0
    return round(number, precision)


def to_state_name(raw_value: Any) -> str:
    """Strip state code prefix from raw state name (example: '11 Rondonia')."""
    cleaned = str(raw_value).strip()
    return re.sub(r"^\d+\s*", "", cleaned)


def load_and_resolve_columns() -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load workbook and dynamically map required columns."""
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    dataframe = pd.read_excel(INPUT_PATH)
    columns = list(dataframe.columns)

    region_col = find_column(columns, lambda c: c == "region", "region")
    state_col = find_column(columns, lambda c: c.startswith("unidade da federacao"), "state name")
    uf_col = find_column(columns, lambda c: c == "uf", "UF")
    total_col = find_column(columns, lambda c: c == "y2015-2024", "total occurrences")
    coefficient_col = find_column(
        columns,
        lambda c: c.startswith("coef. incidencia") and "2015-2024" in c,
        "incidence coefficient (2015-2024)",
    )
    lethality_col = find_column(
        columns,
        lambda c: c.startswith("taxa de letalidade") and "2015-2024" in c,
        "lethality rate (2015-2024)",
    )
    time_to_care_columns = {
        "ignored_or_blank": find_column(columns, lambda c: c.startswith("tempo_ign/"), "time to care ignored/blank"),
        "up_to_1h": find_column(columns, lambda c: c == "0 a 1 horas", "time to care 0-1h"),
        "between_1h_3h": find_column(columns, lambda c: c == "1 a 3 horas", "time to care 1-3h"),
        "between_3h_6h": find_column(columns, lambda c: c == "3 a 6 horas", "time to care 3-6h"),
        "between_6h_12h": find_column(columns, lambda c: c == "6 a 12 horas", "time to care 6-12h"),
        "between_12h_24h": find_column(columns, lambda c: c == "12 a 24 horas", "time to care 12-24h"),
        "more_than_24h": find_column(columns, lambda c: c == "24 horas +", "time to care >24h"),
    }

    yearly_occurrence = {
        2015: find_column(columns, lambda c: c.startswith("ocorrencia_y2015"), "occurrences 2015"),
        **{
            year: find_column(columns, lambda c, expected=f"y{year}": c == expected, f"occurrences {year}")
            for year in range(2016, 2025)
        },
    }
    yearly_incidence = {
        year: find_column(columns, lambda c, expected=f"{year}_incidencia": c == expected, f"incidence {year}")
        for year in YEARS
    }
    yearly_lethality = {
        year: find_column(columns, lambda c, expected=f"{year}_letalidade": c == expected, f"lethality {year}")
        for year in YEARS
    }

    mapped_columns = {
        "region": region_col,
        "state": state_col,
        "uf": uf_col,
        "total": total_col,
        "coefficient": coefficient_col,
        "lethality": lethality_col,
        "time_to_care": time_to_care_columns,
        "yearly_occurrence": yearly_occurrence,
        "yearly_incidence": yearly_incidence,
        "yearly_lethality": yearly_lethality,
    }
    return dataframe, mapped_columns


def build_brazil_by_year(row: pd.Series, columns_map: dict[str, Any]) -> list[dict[str, Any]]:
    """Build national yearly series."""
    series = []
    for year in YEARS:
        series.append(
            {
                "year": year,
                "occurrences": to_int(row[columns_map["yearly_occurrence"][year]]),
                "incidence": to_float(row[columns_map["yearly_incidence"][year]], precision=2),
                "lethality": to_float(row[columns_map["yearly_lethality"][year]], precision=2),
            }
        )
    return series


def build_time_to_care(row: pd.Series, columns_map: dict[str, Any], total: int) -> list[dict[str, Any]]:
    """Build national time-to-care distribution."""
    labels = {
        "ignored_or_blank": "Ignorado/Branco",
        "up_to_1h": "0 a 1 hora",
        "between_1h_3h": "1 a 3 horas",
        "between_3h_6h": "3 a 6 horas",
        "between_6h_12h": "6 a 12 horas",
        "between_12h_24h": "12 a 24 horas",
        "more_than_24h": "24 horas+",
    }

    result = []
    for key, column_name in columns_map["time_to_care"].items():
        count = to_int(row[column_name])
        percentage = round((count / total) * 100, 2) if total > 0 else 0.0
        result.append(
            {
                "bucket": key,
                "label": labels[key],
                "count": count,
                "percentage": percentage,
            }
        )
    return result


def build_state_data(df: pd.DataFrame, columns_map: dict[str, Any], brazil_total: int) -> list[dict[str, Any]]:
    """Build state-level metrics with yearly detail."""
    state_rows = df[df[columns_map["uf"]].notna()].copy()

    records = []
    for _, row in state_rows.iterrows():
        total_occurrences = to_int(row[columns_map["total"]])
        yearly = []
        for year in YEARS:
            yearly.append(
                {
                    "year": year,
                    "occurrences": to_int(row[columns_map["yearly_occurrence"][year]]),
                    "incidence": to_float(row[columns_map["yearly_incidence"][year]], precision=2),
                    "lethality": to_float(row[columns_map["yearly_lethality"][year]], precision=2),
                }
            )

        records.append(
            {
                "uf": str(row[columns_map["uf"]]).strip(),
                "state": to_state_name(row[columns_map["state"]]),
                "region": str(row[columns_map["region"]]).strip(),
                "totalOccurrences": total_occurrences,
                "percentageOfBrazil": round((total_occurrences / brazil_total) * 100, 2) if brazil_total > 0 else 0.0,
                "incidenceCoefficient": to_float(row[columns_map["coefficient"]]),
                "lethalityRate": to_float(row[columns_map["lethality"]]),
                "yearly": yearly,
            }
        )

    records.sort(key=lambda item: item["totalOccurrences"], reverse=True)
    return records


def build_region_data(state_records: list[dict[str, Any]], brazil_total: int) -> list[dict[str, Any]]:
    """Aggregate state records by region."""
    grouped: dict[str, dict[str, Any]] = {}
    for record in state_records:
        region = record["region"]
        if region not in grouped:
            grouped[region] = {
                "region": region,
                "totalOccurrences": 0,
                "stateCount": 0,
            }
        grouped[region]["totalOccurrences"] += record["totalOccurrences"]
        grouped[region]["stateCount"] += 1

    regions = list(grouped.values())
    for region in regions:
        region["percentageOfBrazil"] = (
            round((region["totalOccurrences"] / brazil_total) * 100, 2) if brazil_total > 0 else 0.0
        )

    regions.sort(key=lambda item: item["totalOccurrences"], reverse=True)
    return regions


def main() -> None:
    """Convert occurrence workbook into frontend-friendly JSON."""
    dataframe, columns_map = load_and_resolve_columns()
    region_col = columns_map["region"]

    brazil_rows = dataframe[dataframe[region_col].astype(str).str.strip().str.lower() == "brazil"]
    if brazil_rows.empty:
        raise ValueError("Could not find Brazil aggregate row in workbook.")
    brazil_row = brazil_rows.iloc[0]

    brazil_total = to_int(brazil_row[columns_map["total"]])
    brazil_by_year = build_brazil_by_year(brazil_row, columns_map)
    time_to_care = build_time_to_care(brazil_row, columns_map, brazil_total)
    by_state = build_state_data(dataframe, columns_map, brazil_total)
    by_region = build_region_data(by_state, brazil_total)

    payload = {
        "metadata": {
            "sourceFile": INPUT_PATH.name,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "years": YEARS,
            "totalRows": int(len(dataframe)),
            "stateRows": int(len(by_state)),
        },
        "summary": {
            "totalOccurrences": brazil_total,
            "averageIncidence": to_float(brazil_row[columns_map["coefficient"]]),
            "lethalityRate": to_float(brazil_row[columns_map["lethality"]]),
        },
        "brazilByYear": brazil_by_year,
        "timeToCareBrazil": time_to_care,
        "byRegion": by_region,
        "byState": by_state,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)

    print(f"Generated occurrence metrics JSON at: {OUTPUT_PATH}")
    print(f"Brazil total occurrences (2015-2024): {brazil_total:,}")
    print(f"State records: {len(by_state)}")
    print(f"Region records: {len(by_region)}")


if __name__ == "__main__":
    main()
