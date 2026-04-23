#!/usr/bin/env python3
"""
Execute official SQL-on-FHIR v2 spec tests and generate a conformance report.

This script runs the implementation against the official test suite and produces
a test_report.json file compatible with the SQL-on-FHIR v2 repository format.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, List, Dict, Tuple

import duckdb
import jsonschema
import pandas as pd
import numpy as np

# Ensure we can import fhir4ds
sys.path.insert(0, os.getcwd())

from conformance_log import log_run
from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.viewdef import parse_view_definition, SQLGenerator
from fhir4ds.viewdef.errors import SQLOnFHIRError, ValidationError
from fhir4ds.viewdef.parser import ParseError

# Path to spec test files
SPEC_TESTS_DIR = Path("fhir4ds/viewdef/tests/spec_tests")
OUTPUT_FILE = Path("conformance/reports/viewdef_report.json")

# SQL-on-FHIR v2 test report JSON schema (canonical copy from upstream)
_TEST_REPORT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "additionalProperties": False,
    "patternProperties": {
        ".*": {
            "type": "object",
            "required": ["tests"],
            "additionalProperties": False,
            "properties": {
                "tests": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "required": ["name", "result"],
                        "properties": {
                            "name": {"type": "string"},
                            "result": {
                                "type": "object",
                                "required": ["passed"],
                                "properties": {
                                    "passed": {"type": "boolean"},
                                    "error": {"type": "string"},
                                    "details": {"type": "object"},
                                },
                            },
                        },
                    },
                }
            },
        }
    },
}

def normalize_value(val: Any) -> Any:
    """Normalize a value for comparison."""
    if val is None:
        return None
    if isinstance(val, float):
        return round(val, 6)
    if isinstance(val, list):
        return [normalize_value(v) for v in val]
    return val

def normalize_row(row: dict) -> dict:
    """Normalize a row for comparison."""
    return {k: normalize_value(v) for k, v in row.items()}

def _adapt_sql_for_resources_table(sql: str) -> str:
    """Adapt generated SQL to run against a generic 'resources' table."""
    return re.sub(r'FROM\s+\w+\s+t\b', 'FROM resources t', sql)

def _add_resource_type_filter(sql: str, resource_type: str) -> str:
    """Add a WHERE clause to filter by resourceType for the resources table."""
    type_filter = f"json_extract_string(t.resource, '$.resourceType') = '{resource_type}'"
    branches = sql.split("\nUNION ALL\n")
    adapted_branches = []
    for branch in branches:
        has_where = bool(re.search(r'^\s*WHERE\s', branch, re.MULTILINE | re.IGNORECASE))
        if has_where:
            adapted_branches.append(branch + f"\n  AND {type_filter}")
        else:
            adapted_branches.append(branch + f"\nWHERE {type_filter}")
    return "\nUNION ALL\n".join(adapted_branches)

def run_test(con, generator, test, resources) -> Tuple[bool, str]:
    view = test.get("view", {})
    expected = test.get("expect")
    expect_error = test.get("expectError", False)

    if expected is None and not expect_error:
        return False, "No expected output or error defined"

    resource_type = view.get("resource", "")
    if not resource_type and not expect_error:
        # Some tests might have multiple resources or other structures
        # but the spec usually has a single root resource.
        pass

    try:
        # Parse and generate SQL
        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        # Adapt SQL
        sql = _adapt_sql_for_resources_table(sql)
        if isinstance(resource_type, str) and resource_type:
            sql = _add_resource_type_filter(sql, resource_type)
        elif isinstance(resource_type, list) and resource_type:
             # For multi-resource union, the filter is more complex, 
             # but the generator already handles the union logic.
             # We just need to replace the table name.
             pass

        # Load test resources
        con.execute("CREATE OR REPLACE TABLE resources (resource VARCHAR)")
        for r in resources:
            con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])

        # Execute
        result = con.execute(sql).fetchdf()

        if expect_error:
            return False, "Expected error but query succeeded"

        # Convert result to list of dicts
        actual_rows = []
        for _, row in result.iterrows():
            row_dict = {}
            for col_name in result.columns:
                val = row[col_name]
                if isinstance(val, (np.ndarray, list)):
                    val = [v.item() if hasattr(v, 'item') else v for v in val]
                elif pd.isna(val):
                    val = None
                elif hasattr(val, 'item'):
                    val = val.item()
                
                if isinstance(val, str):
                    try:
                        parsed = json.loads(val)
                        if isinstance(parsed, list):
                            val = parsed
                    except (json.JSONDecodeError, TypeError):
                        pass
                row_dict[col_name] = val
            actual_rows.append(row_dict)

        # Normalize and compare
        actual_normalized = [normalize_row(r) for r in actual_rows]
        expected_normalized = [normalize_row(r) for r in expected]

        def sort_key(row):
            return tuple(str(row.get(k, "")) for k in sorted(row.keys()))

        actual_sorted = sorted(actual_normalized, key=sort_key)
        expected_sorted = sorted(expected_normalized, key=sort_key)

        if len(actual_sorted) != len(expected_sorted):
             return False, f"Row count mismatch: got {len(actual_sorted)}, expected {len(expected_sorted)}"

        for i, (actual_row, expected_row) in enumerate(zip(actual_sorted, expected_sorted)):
            for key in expected_row:
                if key not in actual_row:
                    return False, f"Missing column '{key}' in row {i}"
                if actual_row[key] != expected_row[key]:
                    return False, f"Row {i}, column '{key}': got {actual_row[key]!r}, expected {expected_row[key]!r}"

        return True, ""

    except (SQLOnFHIRError, ValidationError, ParseError, duckdb.Error, Exception) as e:
        if expect_error:
            return True, ""
        return False, str(e)

def main():
    if not SPEC_TESTS_DIR.exists():
        print(f"Error: Spec tests directory not found at {SPEC_TESTS_DIR}")
        sys.exit(1)

    con = duckdb.connect()
    register_fhirpath(con)
    generator = SQLGenerator(strict_collection=True)

    report = {}
    test_files = sorted(SPEC_TESTS_DIR.glob("*.json"))

    total_tests = 0
    passed_tests = 0

    print(f"Running {len(test_files)} spec test files...")

    for filepath in test_files:
        filename = filepath.name
        with open(filepath) as f:
            data = json.load(f)
            resources = data.get("resources", [])
            
            file_results = []
            for i, test in enumerate(data.get("tests", [])):
                test_title = test.get("title", f"test_{i}")
                passed, reason = run_test(con, generator, test, resources)
                
                result_obj = {
                    "name": test_title,
                    "result": {"passed": passed},
                }
                if not passed:
                    result_obj["result"]["error"] = reason
                
                file_results.append(result_obj)
                total_tests += 1
                if passed:
                    passed_tests += 1
            
            report[filename] = { "tests": file_results }
            print(f"  {filename}: {sum(1 for t in file_results if t['result']['passed'])}/{len(file_results)} passed")

    # Ensure output directory exists
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    # Validate report against the SQL-on-FHIR v2 test report JSON schema
    try:
        jsonschema.validate(instance=report, schema=_TEST_REPORT_SCHEMA)
        print("Report schema validation: PASSED")
    except jsonschema.ValidationError as exc:
        print(f"Report schema validation: FAILED — {exc.message}", file=sys.stderr)

    print(f"\nConformance report generated at {OUTPUT_FILE}")
    print(f"Summary: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests:.1%})")

    log_run("ViewDefinition", OUTPUT_FILE)

if __name__ == "__main__":
    main()
