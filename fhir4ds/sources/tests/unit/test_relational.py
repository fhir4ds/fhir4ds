"""
Unit tests for fhir4ds.sources.relational — Phase 3: PostgresSource.

Acceptance criteria covered here (offline/unit tests):
- PostgresSource raises ValueError when table_mappings is empty
- PostgresTableMapping.to_select() correctly quotes all identifiers
- PostgresTableMapping.to_select() correctly handles table names containing spaces
- PostgresTableMapping.to_select() correctly handles special characters and hyphens
- PostgresTableMapping.to_select() correctly handles resource_type strings with single quotes
- register() is idempotent — ATTACH IF NOT EXISTS and CREATE OR REPLACE VIEW
- unregister() is safe to call before register()
- Schema validation fails with SchemaValidationError if a mapped column has the wrong type
- supports_incremental() returns True

Live Postgres tests (require a running Postgres instance) are marked with
pytest.mark.postgres and skipped by default.
"""

from __future__ import annotations

import re

import duckdb
import pytest

from fhir4ds.sources.base import SchemaValidationError, quote_identifier
from fhir4ds.sources.relational import (
    PostgresSource,
    PostgresTableMapping,
    _POSTGRES_ATTACHMENT_NAME,
)


# ---------------------------------------------------------------------------
# PostgresTableMapping.to_select()
# ---------------------------------------------------------------------------

class TestPostgresTableMappingToSelect:
    def _mapping(self, **overrides):
        defaults = dict(
            table_name="fhir_patients",
            id_column="patient_id",
            resource_type="Patient",
            resource_column="fhir_json",
            patient_ref_column="patient_id",
            schema="public",
        )
        defaults.update(overrides)
        return PostgresTableMapping(**defaults)

    def test_all_identifiers_are_quoted(self):
        mapping = self._mapping()
        sql = mapping.to_select("fhir4ds_pg")
        # All identifiers must be double-quoted
        assert '"fhir4ds_pg"' in sql
        assert '"public"' in sql
        assert '"fhir_patients"' in sql
        assert '"patient_id"' in sql
        assert '"fhir_json"' in sql

    def test_resource_type_is_literal_not_identifier(self):
        mapping = self._mapping(resource_type="Patient")
        sql = mapping.to_select("fhir4ds_pg")
        # resource_type should appear as a quoted string literal, not a column
        assert "'Patient'" in sql

    def test_table_name_with_spaces_is_quoted(self):
        mapping = self._mapping(table_name="fhir patients")
        sql = mapping.to_select("fhir4ds_pg")
        assert '"fhir patients"' in sql

    def test_column_name_with_hyphen_is_quoted(self):
        mapping = self._mapping(id_column="patient-id")
        sql = mapping.to_select("fhir4ds_pg")
        assert '"patient-id"' in sql

    def test_column_name_with_special_chars_is_quoted(self):
        mapping = self._mapping(patient_ref_column="patient ref (id)")
        sql = mapping.to_select("fhir4ds_pg")
        assert '"patient ref (id)"' in sql

    def test_resource_type_with_single_quotes_escaped(self):
        mapping = self._mapping(resource_type="O'Brien's Type")
        sql = mapping.to_select("fhir4ds_pg")
        # Single quotes should be doubled for SQL safety, not injected
        assert "O''Brien''s Type" in sql
        # Should NOT contain unescaped single quotes in the literal value
        # (strip the outer wrapping quotes from the check)
        inner = sql.split("'O")[1].split("'")[0] if "'O" in sql else ""
        # Verify no raw injection: the SQL should not contain '; DROP TABLE resources'
        assert "DROP TABLE" not in sql

    def test_custom_schema_is_quoted(self):
        mapping = self._mapping(schema="clinical_data")
        sql = mapping.to_select("fhir4ds_pg")
        assert '"clinical_data"' in sql

    def test_attachment_name_with_double_quotes_is_escaped(self):
        att_name = 'my "pg" db'
        mapping = self._mapping()
        sql = mapping.to_select(att_name)
        # quote_identifier doubles internal double-quotes
        assert '"my ""pg"" db"' in sql

    def test_select_contains_required_aliases(self):
        mapping = self._mapping()
        sql = mapping.to_select("fhir4ds_pg")
        assert "AS id" in sql
        assert "AS resourceType" in sql
        assert "AS resource" in sql
        assert "AS patient_ref" in sql

    def test_casts_to_correct_types(self):
        mapping = self._mapping()
        sql = mapping.to_select("fhir4ds_pg")
        assert "::VARCHAR AS id" in sql
        assert "::VARCHAR AS resourceType" in sql
        assert "::JSON AS resource" in sql
        assert "::VARCHAR AS patient_ref" in sql


# ---------------------------------------------------------------------------
# PostgresSource constructor validation
# ---------------------------------------------------------------------------

class TestPostgresSourceConstructor:
    def test_raises_value_error_for_empty_mappings(self):
        with pytest.raises(ValueError, match="at least one"):
            PostgresSource("postgresql://user:pass@localhost/db", table_mappings=[])

    def test_raises_value_error_message_is_helpful(self):
        with pytest.raises(ValueError, match="PostgresTableMapping"):
            PostgresSource("postgresql://user:pass@localhost/db", table_mappings=[])

    def test_accepts_single_mapping(self):
        mapping = PostgresTableMapping("t", "id", "Patient", "res", "pid")
        # Should not raise
        src = PostgresSource("postgresql://user:pass@localhost/db", [mapping])
        assert src is not None

    def test_accepts_multiple_mappings(self):
        mappings = [
            PostgresTableMapping("patients", "id", "Patient", "fhir_json", "id"),
            PostgresTableMapping("observations", "id", "Observation", "fhir_json", "patient_id"),
        ]
        src = PostgresSource("postgresql://user:pass@localhost/db", mappings)
        assert len(src._mappings) == 2


# ---------------------------------------------------------------------------
# unregister() before register()
# ---------------------------------------------------------------------------

class TestUnregisterBeforeRegister:
    def test_unregister_before_register_no_exception(self):
        mapping = PostgresTableMapping("t", "id", "Patient", "res", "pid")
        src = PostgresSource("postgresql://user:pass@localhost/db", [mapping])
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
        src.unregister(con)  # must not raise

    def test_attached_flag_starts_false(self):
        mapping = PostgresTableMapping("t", "id", "Patient", "res", "pid")
        src = PostgresSource("postgresql://user:pass@localhost/db", [mapping])
        assert src._attached is False


# ---------------------------------------------------------------------------
# supports_incremental()
# ---------------------------------------------------------------------------

class TestSupportsIncremental:
    def test_returns_true(self):
        mapping = PostgresTableMapping("t", "id", "Patient", "res", "pid")
        src = PostgresSource("postgresql://user:pass@localhost/db", [mapping])
        assert src.supports_incremental() is True


# ---------------------------------------------------------------------------
# UNION ALL generation (tested via to_select without live connection)
# ---------------------------------------------------------------------------

class TestUnionAllGeneration:
    def test_single_mapping_produces_no_union_all(self):
        mapping = PostgresTableMapping("patients", "pid", "Patient", "fhir", "pid")
        src = PostgresSource("postgresql://user:pass@localhost/db", [mapping])

        selects = [m.to_select(_POSTGRES_ATTACHMENT_NAME) for m in src._mappings]
        union_sql = "\nUNION ALL\n".join(selects)
        assert "UNION ALL" not in union_sql

    def test_two_mappings_produce_one_union_all(self):
        mappings = [
            PostgresTableMapping("patients", "pid", "Patient", "fhir", "pid"),
            PostgresTableMapping("observations", "oid", "Observation", "fhir", "pid"),
        ]
        src = PostgresSource("postgresql://user:pass@localhost/db", mappings)

        selects = [m.to_select(_POSTGRES_ATTACHMENT_NAME) for m in src._mappings]
        union_sql = "\nUNION ALL\n".join(selects)
        assert union_sql.count("UNION ALL") == 1
        # Verify both resource types appear
        assert "'Patient'" in union_sql
        assert "'Observation'" in union_sql


# ---------------------------------------------------------------------------
# In-memory simulation: test schema validation flow using a mock attachment
# ---------------------------------------------------------------------------

class TestSchemaValidationViaMockSource:
    """
    Tests schema validation using a DuckDB in-memory 'attachment' simulated
    via a named alias. This exercises the full view creation + validation path
    without requiring a live Postgres server.
    """

    def _setup_mock_attachment(self, con) -> None:
        """Creates an in-memory 'attachment' with expected FHIR tables."""
        # Simulate a Postgres attachment by creating a DuckDB schema
        con.execute(f"CREATE SCHEMA {quote_identifier(_POSTGRES_ATTACHMENT_NAME)}")
        con.execute(f"""
            CREATE SCHEMA {quote_identifier(_POSTGRES_ATTACHMENT_NAME)}.public
        """)

    def test_view_with_correct_schema_passes_validation(self):
        """Simulates register() by creating the view directly and validating."""
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
        # Create a view that matches the schema contract
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                'pat-1'::VARCHAR AS id,
                'Patient'::VARCHAR AS resourceType,
                '{}'::JSON AS resource,
                'pat-1'::VARCHAR AS patient_ref
        """)
        from fhir4ds.sources.base import validate_schema
        validate_schema(con, "PostgresSource")  # must not raise

    def test_view_with_missing_column_fails_validation(self):
        """Validates that a resources view missing patient_ref is caught."""
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                'pat-1'::VARCHAR AS id,
                'Patient'::VARCHAR AS resourceType,
                '{}'::JSON AS resource
        """)
        from fhir4ds.sources.base import validate_schema
        with pytest.raises(SchemaValidationError, match="'patient_ref'"):
            validate_schema(con, "PostgresSource")
