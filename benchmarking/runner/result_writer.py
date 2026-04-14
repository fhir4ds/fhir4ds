"""
Write results to files (CSV, SQL, JSON).
"""
import csv
import json
from pathlib import Path
from typing import Dict, List, Any, TYPE_CHECKING

import sqlparse

if TYPE_CHECKING:
    from .measure_runner import MeasureResult

def write_results(
    measure_result: "MeasureResult",
    output_dir: Path,
    sql_format: str = "mozilla",
) -> Dict[str, Path]:
    """
    Write all outputs for a measure.

    Creates:
    - output/sql/{measure_id}.sql - Formatted SQL
    - output/results/{measure_id}.csv - Per-patient results
    - output/stats/{measure_id}.json - Performance stats

    Returns dict of output file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {}

    # Write SQL
    sql_dir = output_dir / "sql"
    sql_dir.mkdir(exist_ok=True)
    sql_path = sql_dir / f"{measure_result.measure_id}.sql"
    write_sql(measure_result.sql, sql_path, format=sql_format)
    paths["sql"] = sql_path

    # Write CSV
    results_dir = output_dir / "results"
    results_dir.mkdir(exist_ok=True)
    csv_path = results_dir / f"{measure_result.measure_id}.csv"
    write_csv(measure_result, csv_path)
    paths["csv"] = csv_path

    # Write stats
    stats_dir = output_dir / "stats"
    stats_dir.mkdir(exist_ok=True)
    stats_path = stats_dir / f"{measure_result.measure_id}.json"
    write_stats(measure_result, stats_path)
    paths["stats"] = stats_path

    return paths

def write_sql(sql: str, path: Path, format: str = "mozilla") -> None:
    """
    Write formatted SQL to file.

    Formats:
    - mozilla: 4-space indent, uppercase keywords, wrap after 80 chars
    - default: 2-space indent
    """
    try:
        formatted = sqlparse.format(
            sql,
            reindent=True,
            keyword_case="upper",
            wrap_mode=80 if format == "mozilla" else None,
            indent_width=4 if format == "mozilla" else 2,
        )
    except Exception:
        # Fall back to raw SQL if formatter fails (e.g., token limit exceeded)
        formatted = sql

    path.write_text(f"-- Generated SQL for measure\n\n{formatted}\n")

def write_csv(measure_result: "MeasureResult", path: Path) -> None:
    """
    Write per-patient results as CSV.

    Columns:
    - patient_id
    - {definition_1}, {definition_2}, ... (one per define)
    - expected_{definition_1}, expected_{definition_2}, ...
    - match (all definitions match expected)
    """
    # Get all definition names from first result
    if not measure_result.results:
        # Write empty file with headers
        path.write_text("patient_id,match\n")
        return

    sample = measure_result.results[0]
    def_names = [k for k in sample.keys() if k != "patient_id"]

    # Build expected lookup
    expected_lookup = {}
    if measure_result.comparison:
        # Access test_cases from comparison if available
        pass  # Will be populated when we have TestSuite access

    # Build rows
    rows = []
    for result in measure_result.results:
        patient_id = result.get("patient_id", "unknown")
        expected = expected_lookup.get(patient_id, {})

        row = {"patient_id": patient_id}
        all_match = True

        for def_name in def_names:
            actual_raw = result.get(def_name, False)
            # Handle list/array values (resource refs, multi-value) - truthy if non-empty
            # Check hasattr for __len__ instead of isinstance to catch DuckDB arrays
            if hasattr(actual_raw, '__len__') and not isinstance(actual_raw, (str, bytes)):
                actual_bool = len(actual_raw) > 0
            else:
                actual_bool = bool(actual_raw)
            expected_val = expected.get(def_name)

            # Write the actual value (not just boolean) for proper output
            row[def_name] = actual_raw
            row[f"expected_{def_name}"] = expected_val if expected_val is not None else ""

            if expected_val is not None and actual_bool != expected_val:
                all_match = False

        row["match"] = all_match
        rows.append(row)

    # Write CSV
    fieldnames = ["patient_id"] + def_names + [f"expected_{d}" for d in def_names] + ["match"]

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def write_stats(measure_result: "MeasureResult", path: Path) -> None:
    """Write performance stats as JSON."""
    stats = {
        "measure_id": measure_result.measure_id,
        "patient_count": measure_result.patient_count,
        "timings_ms": measure_result.timings,
        "patients_per_second": (
            measure_result.patient_count /
            (measure_result.timings.get("total_ms", 1) / 1000)
        ),
    }

    if measure_result.comparison:
        stats["comparison"] = {
            "total_patients": measure_result.comparison.total_patients,
            "matching_patients": measure_result.comparison.matching_patients,
            "accuracy_pct": measure_result.comparison.accuracy_pct,
        }

    path.write_text(json.dumps(stats, indent=2))
