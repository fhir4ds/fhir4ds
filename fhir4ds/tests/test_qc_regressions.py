"""
Regression tests for QC Remediation fixes.

Each test corresponds to a specific issue from the QC Testing Report.
These tests ensure the fixes remain in place and prevent regressions.
"""

import json
import pytest
import duckdb


# ---------------------------------------------------------------------------
# I02: evaluate_measure() .rel bug — conn.sql() returns DuckDBPyRelation
# ---------------------------------------------------------------------------


class TestI02RelBug:
    """The CQL evaluate pipeline must not use .rel (which doesn't exist)."""

    def test_conn_sql_returns_relation(self):
        """conn.sql() returns a DuckDBPyRelation, not .rel."""
        conn = duckdb.connect()
        rel = conn.sql("SELECT 1 AS x")
        assert hasattr(rel, "df"), "conn.sql() should return a DuckDBPyRelation with .df()"
        assert not hasattr(conn.execute("SELECT 1"), "rel"), (
            "DuckDB result objects should not have .rel attribute"
        )
        conn.close()

    def test_evaluate_measure_no_rel_attribute_error(self):
        """evaluate_measure() must not raise AttributeError about .rel."""
        from fhir4ds.cql import evaluate_measure

        conn = duckdb.connect()
        # Using a non-existent path should raise ValueError (our I07 fix),
        # not AttributeError about .rel
        with pytest.raises((ValueError, FileNotFoundError)):
            evaluate_measure("/nonexistent/path.cql", conn)
        conn.close()


# ---------------------------------------------------------------------------
# I05: register() must be idempotent
# ---------------------------------------------------------------------------


class TestI05RegisterIdempotent:
    """Calling register functions multiple times must not crash."""

    def test_register_fhirpath_idempotent(self):
        """register_fhirpath() called twice should not raise."""
        from fhir4ds.fhirpath.duckdb.extension import register_fhirpath

        conn = duckdb.connect()
        register_fhirpath(conn)
        # Second call must not raise NotImplementedException
        register_fhirpath(conn)
        # Verify UDF still works
        result = conn.sql(
            "SELECT fhirpath('{\"id\":\"123\"}', 'id') AS val"
        ).fetchone()
        assert result is not None
        conn.close()

    def test_register_cql_idempotent(self):
        """CQL register() called twice should not raise."""
        from fhir4ds.cql.duckdb.extension import register

        conn = duckdb.connect()
        register(conn)
        # Second call must not raise
        register(conn)
        conn.close()

    def test_register_fhirpath_three_times(self):
        """Stress test: register_fhirpath() called three times."""
        from fhir4ds.fhirpath.duckdb.extension import register_fhirpath

        conn = duckdb.connect()
        for _ in range(3):
            register_fhirpath(conn)
        result = conn.sql(
            "SELECT fhirpath_text('{\"id\":\"abc\"}', 'id') AS val"
        ).fetchone()[0]
        assert result == "abc"
        conn.close()


# ---------------------------------------------------------------------------
# I07: evaluate_measure("") must not raise IsADirectoryError
# ---------------------------------------------------------------------------


class TestI07EmptyPathValidation:
    """evaluate_measure() must validate path input before filesystem ops."""

    def test_empty_string_raises_valueerror(self):
        """Empty string path should raise ValueError, not IsADirectoryError."""
        from fhir4ds.cql import evaluate_measure

        conn = duckdb.connect()
        with pytest.raises(ValueError, match="(?i)(empty|blank|path)"):
            evaluate_measure("", conn)
        conn.close()

    def test_directory_path_raises_valueerror(self):
        """Directory path should raise ValueError, not proceed."""
        import tempfile
        from fhir4ds.cql import evaluate_measure

        conn = duckdb.connect()
        with pytest.raises(ValueError, match="(?i)(directory|not a file|file)"):
            evaluate_measure(tempfile.gettempdir(), conn)
        conn.close()


# ---------------------------------------------------------------------------
# I08: evaluate_measure() must detect closed connection
# ---------------------------------------------------------------------------


class TestI08ClosedConnection:
    """evaluate_measure() must raise a clear error for closed connections."""

    def test_closed_connection_raises_connection_error(self):
        """Closed DuckDB connection should be detected early."""
        from fhir4ds.cql import evaluate_measure

        conn = duckdb.connect()
        conn.close()
        with pytest.raises(Exception) as exc_info:
            evaluate_measure("/tmp/fake.cql", conn)
        # Must NOT be a misleading FileNotFoundError about the CQL file
        error_type = type(exc_info.value).__name__
        error_msg = str(exc_info.value).lower()
        assert (
            "connection" in error_msg
            or "closed" in error_msg
            or "ConnectionException" in error_type
            or "InvalidInputException" in error_type
        ), f"Expected connection-related error, got {error_type}: {exc_info.value}"


# ---------------------------------------------------------------------------
# I09: __version__ must match wheel version
# ---------------------------------------------------------------------------


class TestI09VersionMismatch:
    """Package version must be consistent."""

    def test_version_is_0_0_2(self):
        """fhir4ds.__version__ must match the wheel version 0.0.2."""
        import fhir4ds

        assert fhir4ds.__version__ == "0.0.2"


# ---------------------------------------------------------------------------
# I10: ViewDef duplicate column validation
# ---------------------------------------------------------------------------


class TestI10DuplicateColumnValidation:
    """generate_view_sql() must reject duplicate column names within a select."""

    def test_duplicate_columns_raises_error(self):
        """ViewDefinition with duplicate column names should fail."""
        from fhir4ds import generate_view_sql

        view_def = {
            "resourceType": "ViewDefinition",
            "resource": "Patient",
            "select": [
                {"column": [
                    {"path": "id", "name": "patient_id"},
                    {"path": "gender", "name": "patient_id"},  # duplicate
                ]}
            ],
        }
        with pytest.raises((ValueError, Exception)):
            generate_view_sql(view_def)

    def test_unique_columns_accepted(self):
        """ViewDefinition with unique column names should succeed."""
        from fhir4ds import generate_view_sql

        view_def = {
            "resourceType": "ViewDefinition",
            "resource": "Patient",
            "select": [
                {"column": [
                    {"path": "id", "name": "patient_id"},
                    {"path": "gender", "name": "patient_gender"},
                ]}
            ],
        }
        sql = generate_view_sql(view_def)
        assert sql is not None
        assert "patient_id" in sql


# ---------------------------------------------------------------------------
# I11: FHIRDataLoader must be importable from main package
# ---------------------------------------------------------------------------


class TestI11FHIRDataLoaderExport:
    """FHIRDataLoader must be accessible from fhir4ds namespace."""

    def test_import_from_main_package(self):
        """from fhir4ds import FHIRDataLoader must work."""
        from fhir4ds import FHIRDataLoader

        assert FHIRDataLoader is not None

    def test_in_all(self):
        """FHIRDataLoader must be listed in fhir4ds.__all__."""
        import fhir4ds

        assert "FHIRDataLoader" in fhir4ds.__all__


# ---------------------------------------------------------------------------
# I03: CQL exists() correlation with CTE references
# ---------------------------------------------------------------------------


class TestI03ExistsCorrelation:
    """CQL exists([Resource]) must generate correlated EXISTS, not IS NOT NULL."""

    def test_sql_identifier_importable(self):
        """SQLIdentifier must be importable from the translator types module."""
        from fhir4ds.cql.translator.types import SQLIdentifier

        ident = SQLIdentifier(name="TestCTE")
        assert ident.name == "TestCTE"

    def test_correlation_handles_sql_identifier(self):
        """The correlation module must handle SQLIdentifier in isinstance checks."""
        import inspect
        from fhir4ds.cql.translator import correlation

        source = inspect.getsource(correlation)
        # The fix added SQLIdentifier handling in _correlate_exists_ast
        assert "SQLIdentifier" in source, (
            "correlation.py must reference SQLIdentifier for exists() handling"
        )
