"""
Unit tests for convenience UDFs.

Tests the convenience UDFs:
- fhirpath_text: Returns first value as text
- fhirpath_bool: Returns boolean value
- fhirpath_number: Returns numeric value as double
- fhirpath_json: Returns JSON representation
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from ...import register_fhirpath
from ...udf import (
    fhirpath_bool_udf,
    fhirpath_json_udf,
    fhirpath_number_udf,
    fhirpath_text_udf,
)


# Load test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def patient_json() -> str:
    """Load the sample Patient resource as JSON string."""
    with open(FIXTURES_DIR / "patient.json") as f:
        return f.read()


@pytest.fixture
def observation_json() -> str:
    """Load the sample Observation resource as JSON string."""
    with open(FIXTURES_DIR / "observation.json") as f:
        return f.read()


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    """Create a DuckDB connection with FHIRPath registered."""
    con = duckdb.connect(":memory:")
    register_fhirpath(con)
    return con


class TestFhirpathTextDirect:
    """Direct tests for fhirpath_text_udf function."""

    def test_returns_first_value_as_text(self, patient_json: str) -> None:
        """Test that fhirpath_text returns the first value as a string."""
        result = fhirpath_text_udf(patient_json, "id")
        assert result == "example-patient-1"

    def test_returns_nested_value(self, patient_json: str) -> None:
        """Test extracting nested values."""
        result = fhirpath_text_udf(patient_json, "meta.versionId")
        assert result == "1"

    def test_returns_none_for_missing_field(self, patient_json: str) -> None:
        """Test that missing fields return None."""
        result = fhirpath_text_udf(patient_json, "nonExistentField")
        assert result is None

    def test_returns_none_for_null_resource(self) -> None:
        """Test that null resource returns None."""
        result = fhirpath_text_udf(None, "id")
        assert result is None

    def test_returns_none_for_null_expression(self, patient_json: str) -> None:
        """Test that null expression returns None."""
        result = fhirpath_text_udf(patient_json, None)
        assert result is None

    def test_returns_none_for_invalid_json(self) -> None:
        """Test that invalid JSON returns None."""
        result = fhirpath_text_udf("not valid json", "id")
        assert result is None

    def test_returns_none_for_invalid_expression(self, patient_json: str) -> None:
        """Test that invalid expression returns None."""
        result = fhirpath_text_udf(patient_json, "invalid..expression")
        assert result is None


class TestFhirpathBoolDirect:
    """Direct tests for fhirpath_bool_udf function."""

    def test_returns_boolean_true(self, patient_json: str) -> None:
        """Test that fhirpath_bool returns True for true values."""
        result = fhirpath_bool_udf(patient_json, "active")
        assert result is True

    def test_returns_boolean_false(self, patient_json: str) -> None:
        """Test that fhirpath_bool returns False for false values."""
        result = fhirpath_bool_udf(patient_json, "deceasedBoolean")
        assert result is False

    def test_returns_none_for_missing_field(self, patient_json: str) -> None:
        """Test that missing fields return None."""
        result = fhirpath_bool_udf(patient_json, "nonExistentField")
        assert result is None

    def test_returns_none_for_null_resource(self) -> None:
        """Test that null resource returns None."""
        result = fhirpath_bool_udf(None, "active")
        assert result is None

    def test_returns_none_for_null_expression(self, patient_json: str) -> None:
        """Test that null expression returns None."""
        result = fhirpath_bool_udf(patient_json, None)
        assert result is None

    def test_converts_string_true(self) -> None:
        """Test that string 'true' converts to True."""
        resource = '{"status": "true"}'
        result = fhirpath_bool_udf(resource, "status")
        assert result is True

    def test_converts_string_false(self) -> None:
        """Test that string 'false' converts to False."""
        resource = '{"status": "false"}'
        result = fhirpath_bool_udf(resource, "status")
        assert result is False

    def test_converts_string_true_case_insensitive(self) -> None:
        """Test that string 'TRUE' converts to True (case insensitive)."""
        resource = '{"status": "TRUE"}'
        result = fhirpath_bool_udf(resource, "status")
        assert result is True


class TestFhirpathNumberDirect:
    """Direct tests for fhirpath_number_udf function."""

    def test_returns_numeric_value(self, observation_json: str) -> None:
        """Test that fhirpath_number returns numeric values."""
        result = fhirpath_number_udf(observation_json, "valueQuantity.value")
        assert result == 72.0
        assert isinstance(result, float)

    def test_returns_none_for_missing_field(self, patient_json: str) -> None:
        """Test that missing fields return None."""
        result = fhirpath_number_udf(patient_json, "nonExistentField")
        assert result is None

    def test_returns_none_for_null_resource(self) -> None:
        """Test that null resource returns None."""
        result = fhirpath_number_udf(None, "value")
        assert result is None

    def test_returns_none_for_null_expression(self, observation_json: str) -> None:
        """Test that null expression returns None."""
        result = fhirpath_number_udf(observation_json, None)
        assert result is None

    def test_returns_none_for_non_numeric(self, patient_json: str) -> None:
        """Test that non-numeric values return None."""
        result = fhirpath_number_udf(patient_json, "id")
        assert result is None

    def test_converts_integer_to_float(self) -> None:
        """Test that integer values are converted to float."""
        resource = '{"count": 42}'
        result = fhirpath_number_udf(resource, "count")
        assert result == 42.0
        assert isinstance(result, float)

    def test_handles_float_values(self) -> None:
        """Test that float values are handled correctly."""
        resource = '{"value": 3.14159}'
        result = fhirpath_number_udf(resource, "value")
        assert abs(result - 3.14159) < 0.0001


class TestFhirpathJsonDirect:
    """Direct tests for fhirpath_json_udf function."""

    def test_returns_json_representation(self, patient_json: str) -> None:
        """Test that fhirpath_json returns JSON string."""
        result = fhirpath_json_udf(patient_json, "id")
        assert result is not None
        parsed = json.loads(result)
        assert parsed == ["example-patient-1"]

    def test_returns_empty_list_for_missing_field(self, patient_json: str) -> None:
        """Test that missing fields return None (SQL NULL)."""
        result = fhirpath_json_udf(patient_json, "nonExistentField")
        assert result is None

    def test_returns_none_for_null_resource(self) -> None:
        """Test that null resource returns None."""
        result = fhirpath_json_udf(None, "id")
        assert result is None

    def test_returns_none_for_null_expression(self, patient_json: str) -> None:
        """Test that null expression returns None."""
        result = fhirpath_json_udf(patient_json, None)
        assert result is None

    def test_returns_multiple_values_as_array(self, patient_json: str) -> None:
        """Test that multiple values are returned as JSON array."""
        result = fhirpath_json_udf(patient_json, "name.given")
        assert result is not None
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert "John" in parsed
        assert "Adam" in parsed


class TestFhirpathTextSQL:
    """SQL integration tests for fhirpath_text UDF."""

    def test_registered_and_callable(
        self, con: duckdb.DuckDBPyConnection, patient_json: str
    ) -> None:
        """Test that fhirpath_text is registered and callable from SQL."""
        result = con.execute("SELECT fhirpath_text(?, 'id')", [patient_json]).fetchone()
        assert result is not None
        assert result[0] == "example-patient-1"

    def test_null_resource_returns_null(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that NULL resource returns NULL from SQL."""
        result = con.execute("SELECT fhirpath_text(NULL, 'id')").fetchone()
        assert result[0] is None

    def test_null_expression_returns_null(
        self, con: duckdb.DuckDBPyConnection, patient_json: str
    ) -> None:
        """Test that NULL expression returns NULL from SQL."""
        result = con.execute("SELECT fhirpath_text(?, NULL)", [patient_json]).fetchone()
        assert result[0] is None


class TestFhirpathBoolSQL:
    """SQL integration tests for fhirpath_bool UDF."""

    def test_registered_and_callable(
        self, con: duckdb.DuckDBPyConnection, patient_json: str
    ) -> None:
        """Test that fhirpath_bool is registered and callable from SQL."""
        result = con.execute(
            "SELECT fhirpath_bool(?, 'active')", [patient_json]
        ).fetchone()
        assert result is not None
        assert result[0] is True

    def test_returns_false_value(
        self, con: duckdb.DuckDBPyConnection, patient_json: str
    ) -> None:
        """Test that fhirpath_bool returns False correctly from SQL."""
        result = con.execute(
            "SELECT fhirpath_bool(?, 'deceasedBoolean')", [patient_json]
        ).fetchone()
        assert result is not None
        assert result[0] is False

    def test_null_resource_returns_null(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that NULL resource returns NULL from SQL."""
        result = con.execute("SELECT fhirpath_bool(NULL, 'active')").fetchone()
        assert result[0] is None


class TestFhirpathNumberSQL:
    """SQL integration tests for fhirpath_number UDF."""

    def test_registered_and_callable(
        self, con: duckdb.DuckDBPyConnection, observation_json: str
    ) -> None:
        """Test that fhirpath_number is registered and callable from SQL."""
        result = con.execute(
            "SELECT fhirpath_number(?, 'valueQuantity.value')", [observation_json]
        ).fetchone()
        assert result is not None
        assert result[0] == 72.0

    def test_null_resource_returns_null(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that NULL resource returns NULL from SQL."""
        result = con.execute("SELECT fhirpath_number(NULL, 'value')").fetchone()
        assert result[0] is None

    def test_can_use_in_calculations(
        self, con: duckdb.DuckDBPyConnection, observation_json: str
    ) -> None:
        """Test that numeric result can be used in SQL calculations."""
        result = con.execute(
            "SELECT fhirpath_number(?, 'valueQuantity.value') * 2", [observation_json]
        ).fetchone()
        assert result is not None
        assert result[0] == 144.0


class TestFhirpathJsonSQL:
    """SQL integration tests for fhirpath_json UDF."""

    def test_registered_and_callable(
        self, con: duckdb.DuckDBPyConnection, patient_json: str
    ) -> None:
        """Test that fhirpath_json is registered and callable from SQL."""
        result = con.execute(
            "SELECT fhirpath_json(?, 'id')", [patient_json]
        ).fetchone()
        assert result is not None
        parsed = json.loads(result[0])
        assert parsed == ["example-patient-1"]

    def test_null_resource_returns_null(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that NULL resource returns NULL from SQL."""
        result = con.execute("SELECT fhirpath_json(NULL, 'id')").fetchone()
        assert result[0] is None

    def test_returns_valid_json_string(
        self, con: duckdb.DuckDBPyConnection, patient_json: str
    ) -> None:
        """Test that result is a valid JSON string."""
        result = con.execute(
            "SELECT fhirpath_json(?, 'name.given')", [patient_json]
        ).fetchone()
        assert result is not None
        # Should be parseable as JSON
        parsed = json.loads(result[0])
        assert isinstance(parsed, list)


class TestConvenienceUdfRegistration:
    """Tests for UDF registration."""

    def test_fhirpath_text_registered(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that fhirpath_text function is registered."""
        result = con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE function_name = 'fhirpath_text'"
        ).fetchone()
        assert result is not None
        assert result[0] == "fhirpath_text"

    def test_fhirpath_bool_registered(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that fhirpath_bool function is registered."""
        result = con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE function_name = 'fhirpath_bool'"
        ).fetchone()
        assert result is not None
        assert result[0] == "fhirpath_bool"

    def test_fhirpath_number_registered(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that fhirpath_number function is registered."""
        result = con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE function_name = 'fhirpath_number'"
        ).fetchone()
        assert result is not None
        assert result[0] == "fhirpath_number"

    def test_fhirpath_json_registered(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that fhirpath_json function is registered."""
        result = con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE function_name = 'fhirpath_json'"
        ).fetchone()
        assert result is not None
        assert result[0] == "fhirpath_json"

    def test_fhirpath_date_registered(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that fhirpath_date function is registered."""
        result = con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE function_name = 'fhirpath_date'"
        ).fetchone()
        assert result is not None
        assert result[0] == "fhirpath_date"


class TestMultiRowQueries:
    """Tests for queries over multiple rows."""

    def test_multiple_resources_text(
        self,
        con: duckdb.DuckDBPyConnection,
        patient_json: str,
        observation_json: str,
    ) -> None:
        """Test fhirpath_text over multiple resources."""
        con.execute("CREATE TABLE resources (resource JSON)")
        con.execute("INSERT INTO resources VALUES (?)", [patient_json])
        con.execute("INSERT INTO resources VALUES (?)", [observation_json])

        results = con.execute(
            "SELECT fhirpath_text(resource, 'id') AS id FROM resources"
        ).fetchall()

        assert len(results) == 2
        ids = [r[0] for r in results]
        assert "example-patient-1" in ids
        assert "example-observation-1" in ids

    def test_multiple_resources_number(
        self, con: duckdb.DuckDBPyConnection, observation_json: str
    ) -> None:
        """Test fhirpath_number over multiple resources."""
        con.execute("CREATE TABLE observations (resource JSON)")
        for _ in range(5):
            con.execute("INSERT INTO observations VALUES (?)", [observation_json])

        results = con.execute(
            "SELECT fhirpath_number(resource, 'valueQuantity.value') AS value FROM observations"
        ).fetchall()

        assert len(results) == 5
        for r in results:
            assert r[0] == 72.0

    def test_fhirpath_date_full_date(
        self, con: duckdb.DuckDBPyConnection, observation_json: str
    ) -> None:
        """Test fhirpath_date with full date format."""
        result = con.execute(
            "SELECT fhirpath_date(?, 'effectiveDateTime')", [observation_json]
        ).fetchone()
        assert result is not None
        assert result[0] == "2024-01-15"

    def test_fhirpath_date_month_precision(
        self, con: duckdb.DuckDBPyConnection
    ) -> None:
        """Test fhirpath_date with month precision date."""
        resource = '{"resourceType":"Observation","id":"123","effectiveDateTime":"2023-01"}'
        result = con.execute(
            "SELECT fhirpath_date(?, 'effectiveDateTime')", [resource]
        ).fetchone()
        assert result is not None
        assert result[0] == "2023-01-01"

    def test_fhirpath_date_year_precision(
        self, con: duckdb.DuckDBPyConnection
    ) -> None:
        """Test fhirpath_date with year precision date."""
        resource = '{"resourceType":"Observation","id":"123","effectiveDateTime":"2023"}'
        result = con.execute(
            "SELECT fhirpath_date(?, 'effectiveDateTime')", [resource]
        ).fetchone()
        assert result is not None
        assert result[0] == "2023-01-01"

    def test_fhirpath_date_missing_field(
        self, con: duckdb.DuckDBPyConnection
    ) -> None:
        """Test fhirpath_date with missing field."""
        resource = '{"resourceType":"Observation","id":"123"}'
        result = con.execute(
            "SELECT fhirpath_date(?, 'nonexistent')", [resource]
        ).fetchone()
        assert result is not None
        assert result[0] is None
