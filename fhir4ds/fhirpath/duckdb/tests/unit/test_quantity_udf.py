#!/usr/bin/env python3
"""
Test script for the fhirpath_quantity UDF
"""

import duckdb
from fhir4ds.fhirpath import duckdb as duckdb_fhirpath

def test_fhirpath_quantity_udf():
    """Test the fhirpath_quantity UDF functionality"""

    # Create a DuckDB connection and register the extension
    con = duckdb.connect()
    duckdb_fhirpath.register_fhirpath(con)

    # Test cases
    test_cases = [
        # Test case 1: Basic quantity extraction
        {
            "resource": '{"valueQuantity": {"value": 120, "unit": "mmHg"}}',
            "expression": "valueQuantity",
            "expected": "{'value': 120, 'unit': 'mmHg'}"
        },
        # Test case 2: Nested quantity in Observation
        {
            "resource": '{"resourceType": "Observation", "valueQuantity": {"value": 95, "unit": "%"}}',
            "expression": "valueQuantity",
            "expected": "{'value': 95, 'unit': '%'}"
        },
        # Test case 3: Extract specific value
        {
            "resource": '{"valueQuantity": {"value": 120, "unit": "mmHg"}}',
            "expression": "valueQuantity.value",
            "expected": "120"
        },
        # Test case 4: Extract specific unit
        {
            "resource": '{"valueQuantity": {"value": 120, "unit": "mmHg"}}',
            "expression": "valueQuantity.unit",
            "expected": "mmHg"
        },
        # Test case 5: No match
        {
            "resource": '{"resourceType": "Patient", "name": ["John Doe"]}',
            "expression": "valueQuantity",
            "expected": None
        }
    ]

    # Run tests
    print("Testing fhirpath_quantity UDF:")
    print("=" * 50)

    all_passed = True
    for i, test_case in enumerate(test_cases, 1):
        resource = test_case["resource"]
        expression = test_case["expression"]
        expected = test_case["expected"]

        # Execute the query
        result = con.execute(
            f"SELECT fhirpath_quantity('{resource}', '{expression}')"
        ).fetchone()

        actual = result[0] if result else None

        # Check if test passed
        passed = actual == expected
        all_passed = all_passed and passed

        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"Test {i}: {status}")
        print(f"  Resource: {resource}")
        print(f"  Expression: {expression}")
        print(f"  Expected: {expected}")
        print(f"  Actual: {actual}")
        print()

    print("=" * 50)
    if all_passed:
        print("All tests passed! ✓")
    else:
        print("Some tests failed! ✗")

    return all_passed

if __name__ == "__main__":
    test_fhirpath_quantity_udf()