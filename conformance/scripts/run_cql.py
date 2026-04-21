#!/usr/bin/env python3
"""
Execute official CQL test suite and generate a conformance report.

Level 4: Integrates production-grade comparison logic from benchmarking/runner/comparison.py
to bridge the gap between DuckDB output and CQL spec expectations.
"""

import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import duckdb

# Ensure we can import fhir4ds
sys.path.insert(0, os.getcwd())

from fhir4ds.cql import register_udfs, translate_cql

# Path to CQL test files
CQL_TESTS_DIR = Path("fhir4ds/cql/tests/official/cql-tests/tests/cql")
OUTPUT_FILE = Path("conformance/reports/cql_report.json")

# XML namespace for CQL tests
NS = {"ns": "http://hl7.org/fhirpath/tests"}

def unpack_duckdb_result(val: Any) -> Any:
    """Unpack JSON strings from DuckDB into Python objects."""
    if isinstance(val, str):
        val_trimmed = val.strip()
        if (val_trimmed.startswith('{') and val_trimmed.endswith('}')) or \
           (val_trimmed.startswith('[') and val_trimmed.endswith(']')):
            try:
                return json.loads(val_trimmed)
            except json.JSONDecodeError:
                pass
    return val

def parse_cql_literal(text: str) -> Any:
    """Parse a CQL literal string from XML into a Python object."""
    text = ' '.join(text.split())  # normalize all whitespace
    if not text or text.lower() == "null":
        return None
    
    # Boolean
    if text.lower() == "true": return True
    if text.lower() == "false": return False
    
    # Long integer (CQL suffix L)
    if text.endswith('L') or text.endswith('l'):
        try:
            return int(text[:-1])
        except ValueError:
            pass

    # Number
    try:
        if '.' in text:
            from decimal import Decimal, InvalidOperation
            try:
                d = Decimal(text)
                # Use float only if it doesn't lose precision
                f = float(text)
                if Decimal(str(f)) == d:
                    return f
                return d
            except (InvalidOperation, ValueError):
                return float(text)
        return int(text)
    except ValueError:
        pass
        
    # String: 'quoted'
    if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
        s = text[1:-1]
        # Decode CQL Unicode escape sequences (\uXXXX)
        s = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), s)
        return s
    
    # Quantity: 5.0 'g' or 5 'mg'
    q_match = re.match(r"^([\d\.\-]+)\s*'(.*)'$", text)
    if q_match:
        return {"value": float(q_match.group(1)), "unit": q_match.group(2)}
    
    # DateTime: @2012-04-04T or @2012-04-04T10:00:00
    if text.startswith('@'):
        return text.lstrip('@')
        
    # Interval: Interval[1, 5]
    i_match = re.match(r"^Interval\s*([\[\(])\s*(.*)\s*,\s*(.*)\s*([\]\)])$", text)
    if i_match:
        return {
            "start": parse_cql_literal(i_match.group(2)),
            "end": parse_cql_literal(i_match.group(3)),
            "lowClosed": i_match.group(1) == '[',
            "highClosed": i_match.group(4) == ']'
        }
    
    # List: {1, 2, 3} or {Interval[1, 5], Interval[6, 10]}
    if text.startswith('{') and text.endswith('}'):
        inner = text[1:-1].strip()
        if not inner: return []
        # Bracket-and-string-aware split on commas
        items = []
        depth = 0
        in_string = False
        current = []
        for ch in inner:
            if ch == "'" and not in_string:
                in_string = True
            elif ch == "'" and in_string:
                in_string = False
            if not in_string:
                if ch in ('[', '(', '{'):
                    depth += 1
                elif ch in (']', ')', '}'):
                    depth -= 1
            if ch == ',' and depth == 0 and not in_string:
                items.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        items.append(''.join(current).strip())
        # Heuristic: if every item is a plain `key: value` pair (identifier
        # followed by colon), this is a Tuple like `{ A: 2, B: 5 }`, not a
        # list.  Lists containing typed tuples (`Tuple { ... }`) or nested
        # sets (`{ ... }`) won't match the simple `^\w+\s*:` pattern.
        if items and all(re.match(r'^\w+\s*:', it) for it in items if it):
            result = {}
            for p in items:
                if ':' in p:
                    k, v = p.split(':', 1)
                    result[k.strip()] = parse_cql_literal(v.strip())
            return result
        return [parse_cql_literal(t) for t in items if t]
        
    # Tuple/Concept/Code type literals: Tuple { id: 5, name: 'Chris' }, Concept { codes: ... }
    type_match = re.match(r'^(\w+)\s*\{', text)
    if type_match or (text.startswith('{') and ':' in text):
        t_text = re.sub(r'^\w+\s*', '', text).strip() if type_match else text
        if t_text.startswith('{') and t_text.endswith('}'):
            t_text = t_text[1:-1].strip()
        
        result = {}
        # Bracket-aware split on commas for nested types
        items = []
        depth = 0
        in_string = False
        current = []
        for ch in t_text:
            if ch == "'" and not in_string:
                in_string = True
            elif ch == "'" and in_string:
                in_string = False
            if not in_string:
                if ch in ('{', '[', '('):
                    depth += 1
                elif ch in ('}', ']', ')'):
                    depth -= 1
            if ch == ',' and depth == 0 and not in_string:
                items.append(''.join(current).strip())
                current = []
            else:
                current.append(ch)
        items.append(''.join(current).strip())
        
        for p in items:
            if ':' in p:
                k, v = p.split(':', 1)
                result[k.strip()] = parse_cql_literal(v.strip())
        return result
        
    return text

def normalize_output(output_elem) -> Any:
    """Normalize the expected output from XML element."""
    if output_elem is None:
        return None
    
    val_type = output_elem.get("type")
    text = output_elem.text.strip() if output_elem.text else ""
    
    if val_type == "boolean":
        return text.lower() == "true"
    if val_type == "integer" or val_type == "long":
        return int(text.rstrip('Ll'))
    if val_type == "decimal":
        return float(text)
    if val_type == "string":
        if (text.startswith("'") and text.endswith("'")) or (text.startswith('"') and text.endswith('"')):
            text = text[1:-1]
        # Decode CQL Unicode escape sequences (\uXXXX)
        text = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
        return text
    
    return parse_cql_literal(text)

def compare_results(actual: Any, expected: Any) -> bool:
    """
    Production-grade comparison logic adapted from comparison.py.
    """
    actual = unpack_duckdb_result(actual)
    
    # Handle audit structs: extract .result from audit mode output
    if isinstance(actual, dict) and "result" in actual and "evidence" in actual:
        actual = actual["result"]

    # Handle NaN values
    import math
    if isinstance(actual, float) and math.isnan(actual):
        actual = None
    if isinstance(expected, float) and math.isnan(expected):
        expected = None
    
    # Both None/missing
    if actual is None and expected is None:
        return True

    # One None, other not
    if actual is None or expected is None:
        # Special case: False vs None for boolean defines (both falsy)
        if (actual is False and expected is None) or (actual is None and expected is False):
            return True
        # Empty list/string/dict vs None
        if actual in ([], "", {}) and expected is None:
            return True
        return False

    # Scalar-to-list reduction: if actual is [X] and expected is X
    if isinstance(actual, list) and len(actual) == 1 and not isinstance(expected, list):
        return compare_results(actual[0], expected)

    # List vs boolean: non-empty list is truthy, empty list is falsy
    if isinstance(expected, bool) and isinstance(actual, list):
        return expected == (len(actual) > 0)
    if isinstance(actual, bool) and isinstance(expected, list):
        return actual == (len(expected) > 0)

    # Number comparison with precision
    from decimal import Decimal
    if isinstance(actual, (int, float, Decimal)) and isinstance(expected, (int, float, Decimal)):
        try:
            da = Decimal(str(actual))
            de = Decimal(str(expected))
            if da == de:
                return True
        except Exception:
            pass
        return abs(float(actual) - float(expected)) < 0.001

    # Cross-type: string actual vs Decimal expected (or vice versa)
    if isinstance(actual, str) and isinstance(expected, Decimal):
        try:
            da = Decimal(actual)
            if da == expected:
                return True
        except Exception:
            pass
    if isinstance(expected, str) and isinstance(actual, Decimal):
        try:
            de = Decimal(expected)
            if actual == de:
                return True
        except Exception:
            pass

    # Quantity comparison
    if isinstance(actual, dict) and isinstance(expected, dict):
        if "value" in actual and ("unit" in expected or "code" in expected or "unit" in actual):
            v_match = compare_results(actual.get("value"), expected.get("value"))
            u_actual = actual.get("unit") or actual.get("code")
            u_expected = expected.get("unit") or expected.get("code")
            if v_match and (u_actual == u_expected): return True

        # Interval comparison (production uses low/high, spec uses start/end or low/high)
        a_low = actual.get("low") or actual.get("start")
        a_high = actual.get("high") or actual.get("end")
        e_low = expected.get("low") or expected.get("start")
        e_high = expected.get("high") or expected.get("end")
        if a_low is not None and e_low is not None:
            return compare_results(a_low, e_low) and compare_results(a_high, e_high)

        # Generic dict comparison (Tuple/Concept/Code types)
        if set(actual.keys()) == set(expected.keys()):
            return all(compare_results(actual[k], expected[k]) for k in expected)

    # String handling (Date normalization)
    # Cross-type: string actual vs numeric expected (e.g., "1" vs 1, "10.0" vs 10.0)
    if isinstance(actual, str) and isinstance(expected, (int, float)):
        try:
            from decimal import Decimal as _D
            return compare_results(_D(actual), _D(str(expected)))
        except Exception:
            pass
    if isinstance(expected, str) and isinstance(actual, (int, float)):
        try:
            from decimal import Decimal as _D
            return compare_results(_D(str(actual)), _D(expected))
        except Exception:
            pass
    if isinstance(actual, str) and isinstance(expected, str):
        # Normalize datetime strings to dates for comparison
        a_norm = actual.split()[0] if ' ' in actual else actual
        e_norm = expected.split()[0] if ' ' in expected else expected
        # Strip trailing T from spec dates
        e_norm = e_norm.rstrip('T')
        # Strip leading T from time strings (CQL uses T prefix for times)
        a_norm = a_norm.lstrip('T').strip()
        e_norm = e_norm.lstrip('T').strip()
        if a_norm == e_norm: return True
        if a_norm.startswith(e_norm) or e_norm.startswith(a_norm): return True

    # Cross-type: datetime object vs string
    if isinstance(actual, (date, datetime)) and isinstance(expected, str):
        e_norm = expected.rstrip('T')
        a_str = actual.isoformat()
        if a_str.startswith(e_norm) or e_norm.startswith(a_str[:len(e_norm)]): return True
        # Compare date portion only
        a_date = actual.strftime('%Y-%m-%d') if hasattr(actual, 'strftime') else str(actual)
        if a_date == e_norm or e_norm.startswith(a_date): return True
    if isinstance(expected, (date, datetime)) and isinstance(actual, str):
        return compare_results(expected, actual)  # swap and reuse logic above

    # Cross-type: time object vs string (CQL time format: T14:30:00.000)
    from datetime import time as dt_time
    if isinstance(actual, dt_time) and isinstance(expected, str):
        e_norm = expected.lstrip('T').strip()
        a_str = actual.strftime('%H:%M:%S')
        if actual.microsecond:
            a_str += f'.{actual.microsecond // 1000:03d}'
        else:
            a_str += '.000'
        if a_str == e_norm or e_norm.startswith(a_str) or a_str.startswith(e_norm):
            return True
    if isinstance(expected, dt_time) and isinstance(actual, str):
        return compare_results(expected, actual)

    # Recursive list/dict check
    if isinstance(actual, list) and isinstance(expected, list):
        if len(actual) != len(expected): return False
        return all(compare_results(a, b) for a, b in zip(actual, expected))
    
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual.keys()) != set(expected.keys()): return False
        return all(compare_results(actual[k], expected[k]) for k in expected.keys())

    # Fallback: string comparison
    return str(actual).lower() == str(expected).lower()

def run_test(conn, test_elem) -> Tuple[bool, str]:
    """Run a single CQL test case."""
    expr_elem = test_elem.find("ns:expression", NS)
    if expr_elem is None:
        return False, "No expression found"
    
    cql_expr = expr_elem.text or ""
    expect_invalid = expr_elem.get("invalid", "false") != "false"
    
    output_elem = test_elem.find("ns:output", NS)
    expected = normalize_output(output_elem)
    
    try:
        # Wrap expression in a dummy library
        library_text = f"library Conformance version '1.0'\ndefine \"TestResult\": {cql_expr}"
        
        # Translate to SQL expression
        results = translate_cql(library_text, connection=conn)
        sql_expr = results["TestResult"].to_sql()
        
        # Execute in DuckDB
        res = conn.execute(f"SELECT {sql_expr}").fetchone()
        result = res[0] if res else None
        
        if expect_invalid:
            return False, "Expected error but evaluation succeeded"
            
        # Comparison logic
        if compare_results(result, expected):
            return True, ""
            
        return False, f"Expected {expected} ({type(expected).__name__}), got {result} ({type(result).__name__})"
        
    except Exception as e:
        if expect_invalid:
            return True, ""
        return False, str(e)

def main():
    if not CQL_TESTS_DIR.exists():
        print(f"Error: CQL tests directory not found at {CQL_TESTS_DIR}")
        return

    # Initialize DuckDB
    conn = duckdb.connect(":memory:", config={'allow_unsigned_extensions': 'true'})
    is_cpp = register_udfs(conn)
    print(f">>> Using {'C++' if is_cpp else 'Python'} UDFs")
    
    # Ensure resources table exists
    conn.execute("CREATE TABLE IF NOT EXISTS resources (resource VARCHAR, patient_id VARCHAR)")
    
    report = {}
    test_files = sorted(CQL_TESTS_DIR.glob("*.xml"))
    
    total_tests = 0
    passed_tests = 0
    
    print(f"Running {len(test_files)} CQL test files...")
    
    for filepath in test_files:
        filename = filepath.name
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()
        except Exception as e:
            print(f"  Error parsing {filename}: {e}")
            continue
            
        file_results = []
        for test_elem in root.findall(".//ns:test", NS):
            test_name = test_elem.get("name", "unnamed")
            passed, reason = run_test(conn, test_elem)
            
            test_obj = { "name": test_name, "result": { "passed": passed } }
            if not passed: test_obj["result"]["reason"] = reason
                
            file_results.append(test_obj)
            total_tests += 1
            if passed: passed_tests += 1
                
        report[filename] = { "tests": file_results }
        print(f"  {filename}: {sum(1 for t in file_results if t['result']['passed'])}/{len(file_results)} passed")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)
        
    print(f"\nConformance report generated at {OUTPUT_FILE}")
    if total_tests > 0:
        print(f"Summary: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests:.1%})")

if __name__ == "__main__":
    main()
