"""
Integration tests for SQL + FHIRPath functionality.

Tests the full DuckDB integration including:
- UDF registration
- SQL queries with FHIRPath expressions
- Performance characteristics
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from ...import register_fhirpath


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


class TestUDFRegistration:
    """Tests for UDF registration."""

    def test_fhirpath_function_registered(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that fhirpath function is available."""
        result = con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE function_name = 'fhirpath'"
        ).fetchone()
        assert result is not None
        assert result[0] == "fhirpath"

    def test_fhirpath_is_valid_registered(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that fhirpath_is_valid function is available."""
        result = con.execute(
            "SELECT function_name FROM duckdb_functions() WHERE function_name = 'fhirpath_is_valid'"
        ).fetchone()
        assert result is not None


class TestBasicQueries:
    """Tests for basic FHIRPath queries in SQL."""

    def test_simple_path_query(self, con: duckdb.DuckDBPyConnection, patient_json: str) -> None:
        """Test a simple path query."""
        result = con.execute(
            "SELECT fhirpath(?, 'id') AS result",
            [patient_json]
        ).fetchone()
        assert result is not None
        assert result[0] == ["example-patient-1"]

    def test_nested_path_query(self, con: duckdb.DuckDBPyConnection, patient_json: str) -> None:
        """Test a nested path query."""
        result = con.execute(
            "SELECT fhirpath(?, 'meta.versionId') AS result",
            [patient_json]
        ).fetchone()
        assert result is not None
        assert result[0] == ["1"]

    def test_array_field_query(self, con: duckdb.DuckDBPyConnection, patient_json: str) -> None:
        """Test querying array fields."""
        result = con.execute(
            "SELECT fhirpath(?, 'name.given') AS result",
            [patient_json]
        ).fetchone()
        assert result is not None
        given_names = result[0]
        assert "John" in given_names
        assert "Adam" in given_names

    def test_object_field_query_returns_valid_json_strings(
        self, con: duckdb.DuckDBPyConnection, patient_json: str
    ) -> None:
        """Test querying object fields returns JSON-encoded elements."""
        result = con.execute(
            "SELECT fhirpath(?, 'name') AS result",
            [patient_json]
        ).fetchone()
        assert result is not None
        parsed = [json.loads(item) for item in result[0]]
        assert parsed[0]["family"] == "Smith"
        assert parsed[0]["given"] == ["John", "Adam"]
        assert parsed[1]["given"] == ["Johnny"]

    def test_missing_field_returns_empty(self, con: duckdb.DuckDBPyConnection, patient_json: str) -> None:
        """Test that missing fields return empty collection."""
        result = con.execute(
            "SELECT fhirpath(?, 'nonExistentField') AS result",
            [patient_json]
        ).fetchone()
        assert result is not None
        assert result[0] == []


class TestExpressionValidation:
    """Tests for expression validation."""

    def test_valid_expression(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that valid expressions return true."""
        result = con.execute(
            "SELECT fhirpath_is_valid('Patient.name.given') AS is_valid"
        ).fetchone()
        assert result[0] is True

    def test_empty_expression_invalid(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that empty expressions are invalid."""
        result = con.execute(
            "SELECT fhirpath_is_valid('') AS is_valid"
        ).fetchone()
        assert result[0] is False

    def test_null_expression_invalid(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that null expressions return NULL (SQL NULL semantics)."""
        result = con.execute(
            "SELECT fhirpath_is_valid(NULL) AS is_valid"
        ).fetchone()
        # NULL input returns NULL (not False) - SQL NULL semantics
        assert result[0] is None


class TestMultiRowQueries:
    """Tests for queries over multiple rows."""

    def test_multiple_resources(self, con: duckdb.DuckDBPyConnection, patient_json: str, observation_json: str) -> None:
        """Test querying multiple resources."""
        # Create a table with resources
        con.execute("CREATE TABLE resources (resource JSON)")
        con.execute("INSERT INTO resources VALUES (?)", [patient_json])
        con.execute("INSERT INTO resources VALUES (?)", [observation_json])

        # Query resourceType for all
        results = con.execute(
            "SELECT fhirpath(resource, 'resourceType') AS resource_type FROM resources"
        ).fetchall()

        assert len(results) == 2
        resource_types = [r[0][0] for r in results]
        assert "Patient" in resource_types
        assert "Observation" in resource_types

    def test_filtered_query(self, con: duckdb.DuckDBPyConnection, patient_json: str, observation_json: str) -> None:
        """Test filtering by resource type."""
        # Create a table with resources
        con.execute("CREATE TABLE resources (resource JSON)")
        con.execute("INSERT INTO resources VALUES (?)", [patient_json])
        con.execute("INSERT INTO resources VALUES (?)", [observation_json])

        # Query only Patients
        results = con.execute(
            """
            SELECT fhirpath(resource, 'id') AS id
            FROM resources
            WHERE fhirpath(resource, 'resourceType') = ['Patient']
            """
        ).fetchall()

        assert len(results) == 1
        assert results[0][0] == ["example-patient-1"]


class TestObservationQueries:
    """Tests for Observation-specific queries."""

    def test_observation_code(self, con: duckdb.DuckDBPyConnection, observation_json: str) -> None:
        """Test querying Observation code."""
        result = con.execute(
            "SELECT fhirpath(?, 'code.coding.code') AS codes",
            [observation_json]
        ).fetchone()
        assert result is not None
        codes = result[0]
        assert "8867-4" in codes  # Heart rate LOINC code

    def test_observation_value(self, con: duckdb.DuckDBPyConnection, observation_json: str) -> None:
        """Test querying Observation value."""
        result = con.execute(
            "SELECT fhirpath(?, 'valueQuantity.value') AS value",
            [observation_json]
        ).fetchone()
        assert result is not None
        # Values are returned as strings (VARCHAR[] return type)
        assert result[0] == ["72"]

    def test_observation_status(self, con: duckdb.DuckDBPyConnection, observation_json: str) -> None:
        """Test querying Observation status."""
        result = con.execute(
            "SELECT fhirpath(?, 'status') AS status",
            [observation_json]
        ).fetchone()
        assert result is not None
        assert result[0] == ["final"]


class TestNullHandling:
    """Tests for NULL handling."""

    def test_null_resource(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that NULL resource returns NULL."""
        result = con.execute(
            "SELECT fhirpath(NULL, 'id') AS result"
        ).fetchone()
        assert result[0] is None

    def test_null_expression(self, con: duckdb.DuckDBPyConnection, patient_json: str) -> None:
        """Test that NULL expression returns NULL."""
        result = con.execute(
            "SELECT fhirpath(?, NULL) AS result",
            [patient_json]
        ).fetchone()
        assert result[0] is None

    def test_invalid_json(self, con: duckdb.DuckDBPyConnection) -> None:
        """Test that invalid JSON returns empty collection."""
        result = con.execute(
            "SELECT fhirpath('not valid json', 'id') AS result"
        ).fetchone()
        assert result == ([],)


class TestPerformance:
    """Performance-related tests."""

    def test_expression_caching(self, con: duckdb.DuckDBPyConnection, patient_json: str) -> None:
        """Test that repeated expressions benefit from caching."""
        # Run the same query multiple times
        for _ in range(10):
            result = con.execute(
                "SELECT fhirpath(?, 'name.given') AS result",
                [patient_json]
            ).fetchone()
            assert result is not None
            assert "John" in result[0]

    def test_bulk_query(self, con: duckdb.DuckDBPyConnection, patient_json: str) -> None:
        """Test querying many resources efficiently."""
        # Create table with many resources
        con.execute("CREATE TABLE patients (resource JSON)")
        for _ in range(100):
            con.execute("INSERT INTO patients VALUES (?)", [patient_json])

        # Query all
        results = con.execute(
            "SELECT fhirpath(resource, 'id') AS id FROM patients"
        ).fetchall()

        assert len(results) == 100
        for r in results:
            assert r[0] == ["example-patient-1"]
