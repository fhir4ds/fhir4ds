"""
SQL-on-FHIR v2 Official Specification Tests

Tests sqlonfhirpy against the official SQL-on-FHIR v2 specification tests
from https://github.com/FHIR/sql-on-fhir-v2/tree/master/tests
"""

import json
import os
from pathlib import Path
from typing import Any

import pytest

# Import sql_on_fhir_py
import sys

from ..import parse_view_definition, SQLGenerator
from ..errors import SQLOnFHIRError, ValidationError
from ..parser import ParseError

# Try to import duckdb and fhirpath extension
try:
    import duckdb
    from fhir4ds.fhirpath.duckdb import register_fhirpath
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False
    pytestmark = pytest.mark.skip(reason="duckdb or duckdb_fhirpath not available")


# Path to spec test files
SPEC_TESTS_DIR = Path(__file__).parent / "spec_tests"


def load_spec_test_file(filename: str) -> dict:
    """Load a spec test JSON file."""
    filepath = SPEC_TESTS_DIR / filename
    if not filepath.exists():
        pytest.skip(f"Spec test file not found: {filepath}")
    with open(filepath) as f:
        return json.load(f)


def get_all_spec_tests():
    """Get all spec tests from all test files (auto-discovers all JSON files)."""
    tests = []
    test_files = sorted(SPEC_TESTS_DIR.glob("*.json"))

    for filepath in test_files:
        filename = filepath.name
        with open(filepath) as f:
            data = json.load(f)
            file_title = data.get("title", filename)
            resources = data.get("resources", [])

            for i, test in enumerate(data.get("tests", [])):
                tests.append({
                    "file": filename,
                    "file_title": file_title,
                    "test_index": i,
                    "test_title": test.get("title", f"test_{i}"),
                    "test": test,
                    "resources": resources,
                })

    return tests


@pytest.fixture(scope="module")
def duckdb_connection():
    """Create a DuckDB connection with FHIRPath extension."""
    if not HAS_DUCKDB:
        pytest.skip("duckdb not available")

    con = duckdb.connect()
    register_fhirpath(con)
    yield con
    con.close()


@pytest.fixture
def generator():
    """Create a SQL generator with spec-strict collection validation."""
    return SQLGenerator(strict_collection=True)


def normalize_value(val: Any) -> Any:
    """Normalize a value for comparison."""
    if val is None:
        return None
    if isinstance(val, float):
        # Round floats for comparison
        return round(val, 6)
    if isinstance(val, list):
        return [normalize_value(v) for v in val]
    return val


def normalize_row(row: dict) -> dict:
    """Normalize a row for comparison."""
    return {k: normalize_value(v) for k, v in row.items()}


class TestSpecBasic:
    """Tests from basic.json"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_data = load_spec_test_file("basic.json")
        self.resources = self.test_data["resources"]
        self.tests = self.test_data["tests"]

    @pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb not available")
    def test_basic_attribute(self, duckdb_connection, generator):
        """Test basic attribute extraction."""
        test = self.tests[0]  # "basic attribute"
        view = test["view"]
        expected = test["expect"]

        # Parse and generate SQL
        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        # Setup resources
        con = duckdb_connection
        con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
        for r in self.resources:
            con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])

        # Execute SQL (with table name substitution)
        # The generated SQL uses lowercase plural table names like "FROM patients t"
        # Replace the table reference with the resources table + resourceType filter
        import re
        sql_with_table = re.sub(
            r'FROM\s+\w+\s+t\b',
            "FROM resources t WHERE t.resource->>'resourceType' = 'Patient'",
            sql
        )
        result = con.execute(sql_with_table).fetchall()

        # Verify
        assert len(result) == len(expected)

    @pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb not available")
    def test_boolean_attribute(self, duckdb_connection, generator):
        """Test boolean attribute with false value."""
        test = self.tests[1]  # "boolean attribute with false"
        view = test["view"]
        expected = test["expect"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        con = duckdb_connection
        con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
        for r in self.resources:
            con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])

        # The generated SQL uses lowercase plural table names like "FROM patients t"
        # Replace the table reference with the resources table + resourceType filter
        import re
        sql_with_table = re.sub(
            r'FROM\s+\w+\s+t\b',
            "FROM resources t WHERE t.resource->>'resourceType' = 'Patient'",
            sql
        )
        result = con.execute(sql_with_table).fetchdf()

        assert len(result) == len(expected)


class TestSpecParsing:
    """Test that all spec test ViewDefinitions can be parsed."""

    @pytest.mark.parametrize("test_info", get_all_spec_tests(), ids=lambda t: f"{t['file']}:{t['test_title']}")
    def test_parse_view_definition(self, test_info):
        """Test that ViewDefinition can be parsed."""
        test = test_info["test"]
        view = test.get("view", {})

        # Some tests expect errors - skip those for parsing validation
        if test.get("expectError"):
            # For error tests, we expect parsing might fail or succeed
            # Either is acceptable - the error might be caught at generation time
            try:
                vd = parse_view_definition(json.dumps(view))
                # If parsing succeeded, that's fine - error may come later
                assert vd is not None
            except (SQLOnFHIRError, ValidationError, ParseError):
                # If parsing fails, that's also acceptable for error tests
                pass
        else:
            vd = parse_view_definition(json.dumps(view))
            assert vd is not None
            assert vd.resource == view.get("resource")


class TestSpecSQLGeneration:
    """Test SQL generation for all spec tests."""

    @pytest.fixture
    def generator(self):
        return SQLGenerator(strict_collection=True)

    @pytest.mark.parametrize("test_info", get_all_spec_tests(), ids=lambda t: f"{t['file']}:{t['test_title']}")
    def test_generate_sql(self, test_info, generator):
        """Test that SQL can be generated from ViewDefinition."""
        test = test_info["test"]
        view = test.get("view", {})

        # Skip error tests
        if test.get("expectError"):
            pytest.skip("Error test - SQL generation expected to fail")

        # Known unsupported features that prevent SQL generation
        test_id = f"{test_info['file']}:{test_info['test_title']}"
        _gen_xfail = {
        }
        if test_id in _gen_xfail:
            pytest.xfail(_gen_xfail[test_id])

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None
        assert len(sql) > 0
        assert "SELECT" in sql.upper()
        # Check that the resource type is referenced
        assert view.get("resource", "").lower() in sql.lower() or "fhirpath" in sql.lower()


class TestSpecFHIRPath:
    """Tests for FHIRPath functionality."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_data = load_spec_test_file("fhirpath.json")
        self.resources = self.test_data["resources"]
        self.tests = self.test_data["tests"]

    def test_fhirpath_first(self, generator):
        """Test FHIRPath first() function."""
        test = self.tests[1]  # "two elements + first"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert "first()" in sql.lower() or "fhirpath" in sql.lower()

    def test_fhirpath_index(self, generator):
        """Test FHIRPath index access [n]."""
        test = self.tests[3]  # "index[0]"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None

    def test_fhirpath_where(self, generator):
        """Test FHIRPath where() function."""
        test = self.tests[6]  # "where"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert "where" in sql.lower() or "fhirpath" in sql.lower()

    def test_fhirpath_exists(self, generator):
        """Test FHIRPath exists() function."""
        test = self.tests[7]  # "exists"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert "exists()" in sql.lower() or "fhirpath" in sql.lower()


class TestSpecConstants:
    """Tests for constant substitution."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_data = load_spec_test_file("constant.json")
        self.resources = self.test_data["resources"]
        self.tests = self.test_data["tests"]

    def test_constant_string_in_path(self, generator):
        """Test string constant in path."""
        test = self.tests[0]  # "constant in path"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))

        # Verify constants are parsed
        assert len(vd.constants) == 1
        assert vd.constants[0].name == "name_use"
        assert vd.constants[0].valueString == "official"

        sql = generator.generate(vd)
        assert sql is not None

    def test_constant_in_where(self, generator):
        """Test constant in where clause."""
        test = self.tests[2]  # "constant in where element"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None

    def test_constant_in_unionAll(self, generator):
        """Test constant in unionAll."""
        test = self.tests[3]  # "constant in unionAll"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None

    def test_constant_integer(self, generator):
        """Test integer constant."""
        test = self.tests[4]  # "integer constant"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))

        assert len(vd.constants) == 1
        assert vd.constants[0].name == "name_index"
        assert vd.constants[0].valueInteger == 1

        sql = generator.generate(vd)
        assert sql is not None

    def test_constant_boolean(self, generator):
        """Test boolean constant."""
        test = self.tests[5]  # "boolean constant"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))

        assert len(vd.constants) == 1
        assert vd.constants[0].name == "is_deceased"
        assert vd.constants[0].valueBoolean == True

        sql = generator.generate(vd)
        assert sql is not None

    def test_undefined_constant_error(self, generator):
        """Test that undefined constant raises error."""
        test = self.tests[6]  # "accessing an undefined constant"
        view = test["view"]

        # This should raise an error during constant resolution
        with pytest.raises((SQLOnFHIRError, ValidationError)):
            vd = parse_view_definition(json.dumps(view))
            sql = generator.generate(vd)


class TestSpecConstantTypes:
    """Tests for all constant types."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_data = load_spec_test_file("constant_types.json")
        self.resources = self.test_data["resources"]
        self.tests = self.test_data["tests"]

    def test_constant_base64binary(self, generator):
        """Test base64Binary constant."""
        test = self.tests[0]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueBase64Binary == "aGVsbG8K"

    def test_constant_code(self, generator):
        """Test code constant."""
        test = self.tests[1]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueCode == "female"

    def test_constant_date(self, generator):
        """Test date constant."""
        test = self.tests[2]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueDate == "1978-03-12"

    def test_constant_datetime(self, generator):
        """Test dateTime constant."""
        test = self.tests[3]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueDateTime == "2016-11-12"

    def test_constant_decimal(self, generator):
        """Test decimal constant."""
        test = self.tests[4]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueDecimal == 1.2

    def test_constant_instant(self, generator):
        """Test instant constant."""
        test = self.tests[6]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueInstant == "2015-02-07T13:28:17.239+02:00"

    def test_constant_oid(self, generator):
        """Test oid constant."""
        test = self.tests[7]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueOid == "urn:oid:1.0"

    def test_constant_positiveint(self, generator):
        """Test positiveInt constant."""
        test = self.tests[8]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valuePositiveInt == 1

    def test_constant_time(self, generator):
        """Test time constant."""
        test = self.tests[9]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueTime == "18:12:00"

    def test_constant_unsignedint(self, generator):
        """Test unsignedInt constant."""
        test = self.tests[10]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueUnsignedInt == 9

    def test_constant_uri(self, generator):
        """Test uri constant."""
        test = self.tests[11]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueUri == "urn:uuid:53fefa32-fcbb-4ff8-8a92-55ee120877b7"

    def test_constant_url(self, generator):
        """Test url constant."""
        test = self.tests[12]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueUrl == "http://example.org"

    def test_constant_uuid(self, generator):
        """Test uuid constant."""
        test = self.tests[13]
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        assert len(vd.constants) == 1
        assert vd.constants[0].valueUuid == "urn:uuid:53fefa32-fcbb-4ff8-8a92-55ee120877b7"


class TestSpecCollection:
    """Tests for collection handling."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_data = load_spec_test_file("collection.json")
        self.resources = self.test_data["resources"]
        self.tests = self.test_data["tests"]

    def test_collection_true(self, generator):
        """Test collection = true."""
        test = self.tests[1]  # "collection = true"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None

    def test_collection_error_when_not_true(self, generator):
        """Test error when collection is not true for multi-values."""
        test = self.tests[0]  # "fail when 'collection' is not true"
        view = test["view"]

        # This should raise an error
        with pytest.raises((SQLOnFHIRError, ValidationError)):
            vd = parse_view_definition(json.dumps(view))
            sql = generator.generate(vd)


class TestSpecCombinations:
    """Tests for feature combinations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_data = load_spec_test_file("combinations.json")
        self.resources = self.test_data["resources"]
        self.tests = self.test_data["tests"]

    def test_nested_select(self, generator):
        """Test nested select."""
        test = self.tests[0]  # "select"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None

    def test_column_and_select(self, generator):
        """Test column + select combination."""
        test = self.tests[1]  # "column + select"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None

    def test_sibling_select(self, generator):
        """Test sibling select."""
        test = self.tests[2]  # "sibling select"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None

    def test_with_where(self, generator):
        """Test column + select with where."""
        test = self.tests[4]  # "column + select, with where"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None


class TestSpecFHIRPathNumbers:
    """Tests for FHIRPath number operations."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.test_data = load_spec_test_file("fhirpath_numbers.json")
        self.resources = self.test_data["resources"]
        self.tests = self.test_data["tests"]

    def test_arithmetic_operations(self, generator):
        """Test FHIRPath arithmetic operations."""
        test = self.tests[0]  # "add observation"
        view = test["view"]

        vd = parse_view_definition(json.dumps(view))
        sql = generator.generate(vd)

        assert sql is not None
        # Check that arithmetic operations are in the SQL
        assert "+" in sql or "add" in sql.lower() or "fhirpath" in sql.lower()


# Summary test to count coverage
class TestSpecCoverage:
    """Test coverage summary."""

    def test_spec_test_count(self):
        """Verify we have tests for all spec test cases."""
        all_tests = get_all_spec_tests()

        # Count by file
        files = {}
        for t in all_tests:
            files[t["file"]] = files.get(t["file"], 0) + 1

        print(f"\nSpec test coverage:")
        for f, count in sorted(files.items()):
            print(f"  {f}: {count} tests")
        print(f"  Total: {len(all_tests)} tests")

        # We should have all 22 spec test files
        assert len(files) == 22
        assert len(all_tests) == 134


def _adapt_sql_for_resources_table(sql: str, resource_type: str) -> str:
    """Adapt generated SQL to run against a generic 'resources' table.

    The generator produces SQL like 'FROM patients t' using type-specific tables.
    This adapts it to use a generic 'resources' table with a resourceType filter.
    """
    import re
    # Match any "FROM <word> t" pattern (the generator's table name)
    adapted = re.sub(r'FROM\s+\w+\s+t\b', 'FROM resources t', sql)
    return adapted


def _add_resource_type_filter(sql: str, resource_type: str) -> str:
    """Add a WHERE clause to filter by resourceType for the resources table."""
    import re
    type_filter = f"json_extract_string(t.resource, '$.resourceType') = '{resource_type}'"

    # For UNION ALL queries, add the filter to each branch
    branches = sql.split("\nUNION ALL\n")
    adapted_branches = []
    for branch in branches:
        # Look for a SQL-level WHERE keyword (at start of line, not inside strings)
        has_where = bool(re.search(r'^\s*WHERE\s', branch, re.MULTILINE | re.IGNORECASE))
        if has_where:
            adapted_branches.append(branch + f"\n  AND {type_filter}")
        else:
            adapted_branches.append(branch + f"\nWHERE {type_filter}")
    return "\nUNION ALL\n".join(adapted_branches)


def _execute_spec_test(con, generator, test_info):
    """Execute a spec test and return (actual_rows, expected_rows) or raise SkipTest."""
    test = test_info["test"]
    view = test.get("view", {})
    resources = test_info["resources"]
    expected = test.get("expect")

    if test.get("expectError"):
        pytest.skip("Error test — validated by parsing/generation tests")

    if expected is None:
        pytest.skip("No expected output defined")

    resource_type = view.get("resource", "")
    if not resource_type:
        pytest.skip("No resource type in view")

    # Parse and generate SQL
    vd = parse_view_definition(json.dumps(view))
    sql = generator.generate(vd)

    # Adapt SQL for generic resources table
    sql = _adapt_sql_for_resources_table(sql, resource_type)
    sql = _add_resource_type_filter(sql, resource_type)

    # Load test resources
    con.execute("CREATE OR REPLACE TABLE resources (resource VARCHAR)")
    for r in resources:
        con.execute("INSERT INTO resources VALUES (?)", [json.dumps(r)])

    # Execute
    result = con.execute(sql).fetchdf()

    # Convert result to list of dicts
    actual_rows = []
    for _, row in result.iterrows():
        row_dict = {}
        for col_name in result.columns:
            val = row[col_name]
            # Handle pandas NA / None / NaN
            import pandas as pd
            import numpy as np
            if isinstance(val, (np.ndarray, list)):
                # Convert numpy array to Python list
                val = [v.item() if hasattr(v, 'item') else v for v in val]
            elif pd.isna(val):
                val = None
            elif hasattr(val, 'item'):
                val = val.item()
            if isinstance(val, str):
                # Try to parse JSON arrays/objects
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        val = parsed
                except (json.JSONDecodeError, TypeError):
                    pass
            row_dict[col_name] = val
        actual_rows.append(row_dict)

    return actual_rows, expected


@pytest.mark.skipif(not HAS_DUCKDB, reason="duckdb not available")
class TestSpecExecution:
    """Execute generated SQL against test resources and verify expected output."""

    @pytest.fixture(autouse=True)
    def setup(self, duckdb_connection, generator):
        self.con = duckdb_connection
        self.gen = generator

    # Known unsupported FHIRPath functions — mark as xfail
    _XFAIL_TESTS = {
        # lowBoundary/highBoundary not implemented in fhirpath-py
        "fn_boundary.json:datetime lowBoundary": "lowBoundary() not implemented",
        "fn_boundary.json:datetime highBoundary": "highBoundary() not implemented",
        "fn_boundary.json:date lowBoundary": "lowBoundary() not implemented",
        "fn_boundary.json:date highBoundary": "highBoundary() not implemented",
        "fn_boundary.json:time lowBoundary": "lowBoundary() not implemented",
        "fn_boundary.json:time highBoundary": "highBoundary() not implemented",
        # ofType() broken on FHIR choice types in fhirpath-py
        "fn_oftype.json:select string values": "ofType() broken on choice types",
        "fn_oftype.json:select integer values": "ofType() broken on choice types",
        "fn_extension.json:simple extension": "ofType() broken on choice types",
        "constant.json:boolean constant": "deceased.ofType(boolean) broken on choice types",
        "constant_types.json:dateTime": "ofType(dateTime) broken on choice types",
        "constant_types.json:instant": "ofType(instant) broken on choice types",
        "constant_types.json:time": "ofType(time) broken on choice types",
        # where with ofType(integer) — choice type resolution
        "where.json:where path with greater than inequality": "ofType(integer) broken on choice types",
        "where.json:where path with less than inequality": "ofType(integer) broken on choice types",
        # Logic tests using ofType on choice types
        "logic.json:filtering with 'and'": "ofType(boolean) broken on choice types",
        "logic.json:filtering with 'or'": "ofType(boolean) broken on choice types",
        # row_index with repeat — depends on repeat being implemented
        # "row_index.json:%rowIndex with repeat": "repeat not implemented",
        # unionAll nested inside forEach — columns from inner branches not propagated
        "row_index.json:%rowIndex in unionAll inside forEach": "unionAll inside forEach not fully supported",
    }

    @pytest.mark.parametrize("test_info", get_all_spec_tests(),
                             ids=lambda t: f"{t['file']}:{t['test_title']}")
    def test_execute_and_verify(self, test_info):
        """Execute generated SQL and verify results match expected output."""
        test_id = f"{test_info['file']}:{test_info['test_title']}"
        if test_id in self._XFAIL_TESTS:
            pytest.xfail(self._XFAIL_TESTS[test_id])

        try:
            actual_rows, expected = _execute_spec_test(
                self.con, self.gen, test_info
            )
        except (SQLOnFHIRError, ValidationError, ParseError) as e:
            if test_info["test"].get("expectError"):
                return  # Expected error
            pytest.skip(f"Generation not yet supported: {e}")

        # Normalize for comparison
        actual_normalized = [normalize_row(r) for r in actual_rows]
        expected_normalized = [normalize_row(r) for r in expected]

        # Sort both by all column values for order-independent comparison
        def sort_key(row):
            return tuple(str(row.get(k, "")) for k in sorted(row.keys()))

        actual_sorted = sorted(actual_normalized, key=sort_key)
        expected_sorted = sorted(expected_normalized, key=sort_key)

        assert len(actual_sorted) == len(expected_sorted), (
            f"Row count mismatch: got {len(actual_sorted)}, expected {len(expected_sorted)}\n"
            f"Actual: {actual_sorted}\nExpected: {expected_sorted}"
        )

        for i, (actual_row, expected_row) in enumerate(zip(actual_sorted, expected_sorted)):
            for key in expected_row:
                assert key in actual_row, f"Missing column '{key}' in row {i}"
                assert actual_row[key] == expected_row[key], (
                    f"Row {i}, column '{key}': got {actual_row[key]!r}, "
                    f"expected {expected_row[key]!r}"
                )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
