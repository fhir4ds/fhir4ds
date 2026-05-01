"""
Unit tests for fhir4ds.sources.base — Phase 0: Core Contracts.

Covers:
- validate_schema() happy/error paths
- quote_identifier() escaping
- SourceAdapter Protocol isinstance checks
- attach() / detach() in fhir4ds top-level API
"""

from __future__ import annotations

import pytest
import duckdb

from fhir4ds.sources.base import (
    SchemaValidationError,
    SourceAdapter,
    quote_identifier,
    validate_schema,
)
import fhir4ds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})


def _create_good_view(con) -> None:
    """Creates a resources view that fully satisfies the schema contract."""
    con.execute("""
        CREATE OR REPLACE VIEW resources AS
        SELECT
            'res-1'::VARCHAR       AS id,
            'Patient'::VARCHAR     AS resourceType,
            '{}'::JSON             AS resource,
            'pat-1'::VARCHAR       AS patient_ref
    """)


# ---------------------------------------------------------------------------
# validate_schema()
# ---------------------------------------------------------------------------

class TestValidateSchema:
    def test_passes_for_correct_view(self):
        con = _make_con()
        _create_good_view(con)
        validate_schema(con, "TestAdapter")  # must not raise

    def test_raises_for_missing_id(self):
        con = _make_con()
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                'Patient'::VARCHAR AS resourceType,
                '{}'::JSON         AS resource,
                'pat-1'::VARCHAR   AS patient_ref
        """)
        with pytest.raises(SchemaValidationError, match="'id'"):
            validate_schema(con, "TestAdapter")

    def test_raises_for_missing_resource_type(self):
        con = _make_con()
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                'r1'::VARCHAR    AS id,
                '{}'::JSON       AS resource,
                'pat-1'::VARCHAR AS patient_ref
        """)
        with pytest.raises(SchemaValidationError, match="'resourceType'"):
            validate_schema(con, "TestAdapter")

    def test_raises_for_missing_resource(self):
        con = _make_con()
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                'r1'::VARCHAR      AS id,
                'Patient'::VARCHAR AS resourceType,
                'pat-1'::VARCHAR   AS patient_ref
        """)
        with pytest.raises(SchemaValidationError, match="'resource'"):
            validate_schema(con, "TestAdapter")

    def test_raises_for_missing_patient_ref(self):
        con = _make_con()
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                'r1'::VARCHAR      AS id,
                'Patient'::VARCHAR AS resourceType,
                '{}'::JSON         AS resource
        """)
        with pytest.raises(SchemaValidationError, match="'patient_ref'"):
            validate_schema(con, "TestAdapter")

    def test_raises_for_wrong_type(self):
        con = _make_con()
        # id as INTEGER instead of VARCHAR
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                1::INTEGER         AS id,
                'Patient'::VARCHAR AS resourceType,
                '{}'::JSON         AS resource,
                'pat-1'::VARCHAR   AS patient_ref
        """)
        with pytest.raises(SchemaValidationError, match="'id'"):
            validate_schema(con, "TestAdapter")

    def test_error_message_contains_adapter_name(self):
        con = _make_con()
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT 'x'::VARCHAR AS id, 'Patient'::VARCHAR AS resourceType, '{}'::JSON AS resource
        """)
        with pytest.raises(SchemaValidationError, match="MyCustomAdapter"):
            validate_schema(con, "MyCustomAdapter")

    def test_raises_when_view_does_not_exist(self):
        con = _make_con()
        with pytest.raises(SchemaValidationError):
            validate_schema(con, "TestAdapter")


# ---------------------------------------------------------------------------
# quote_identifier()
# ---------------------------------------------------------------------------

class TestQuoteIdentifier:
    def test_simple_name(self):
        assert quote_identifier("my_table") == '"my_table"'

    def test_name_with_spaces(self):
        assert quote_identifier("my table") == '"my table"'

    def test_name_with_double_quotes(self):
        assert quote_identifier('say "hello"') == '"say ""hello"""'

    def test_name_with_hyphen(self):
        assert quote_identifier("my-table") == '"my-table"'

    def test_empty_string(self):
        assert quote_identifier("") == '""'

    def test_name_already_would_be_quoted(self):
        # Should double internal quotes
        result = quote_identifier('"already"')
        assert result == '"""already"""'

    def test_sql_injection_attempt(self):
        malicious = "t; DROP TABLE resources; --"
        quoted = quote_identifier(malicious)
        assert quoted == '"t; DROP TABLE resources; --"'
        # Verify it round-trips safely in DuckDB
        con = _make_con()
        # Creating a table with a safe name, then using quoted identifier
        con.execute(f"CREATE TABLE {quoted} (x INT)")
        result = con.execute("SHOW TABLES").fetchall()
        table_names = [r[0] for r in result]
        assert "t; DROP TABLE resources; --" in table_names


# ---------------------------------------------------------------------------
# SourceAdapter Protocol isinstance checks
# ---------------------------------------------------------------------------

class TestSourceAdapterProtocol:
    def test_object_without_methods_is_not_adapter(self):
        assert not isinstance(object(), SourceAdapter)

    def test_object_with_only_register_is_not_adapter(self):
        class OnlyRegister:
            def register(self, con): pass

        assert not isinstance(OnlyRegister(), SourceAdapter)

    def test_object_with_register_and_unregister_is_adapter(self):
        class MinimalAdapter:
            def register(self, con): pass
            def unregister(self, con): pass

        # The SourceAdapter Protocol requires register() and unregister()
        assert isinstance(MinimalAdapter(), SourceAdapter)

    def test_full_adapter_is_adapter(self):
        from datetime import datetime

        class FullAdapter:
            def register(self, con): pass
            def unregister(self, con): pass
            def get_changed_patients(self, since: datetime): return []
            def supports_incremental(self): return False

        assert isinstance(FullAdapter(), FullAdapter)


# ---------------------------------------------------------------------------
# fhir4ds.attach() / fhir4ds.detach()
# ---------------------------------------------------------------------------

class TestAttachDetach:
    def _make_adapter(self, register_calls: list, unregister_calls: list):
        class SpyAdapter:
            def register(self, con):
                register_calls.append(con)

            def unregister(self, con):
                unregister_calls.append(con)

        return SpyAdapter()
    def test_attach_calls_register_once(self):
        reg = []
        unreg = []
        con = _make_con()
        adapter = self._make_adapter(reg, unreg)
        fhir4ds.attach(con, adapter)
        assert len(reg) == 1
        assert reg[0] is con

    def test_attach_raises_type_error_for_non_adapter(self):
        con = _make_con()
        with pytest.raises(TypeError, match="SourceAdapter"):
            fhir4ds.attach(con, object())

    def test_detach_calls_unregister(self):
        reg = []
        unreg = []
        con = _make_con()
        adapter = self._make_adapter(reg, unreg)
        fhir4ds.detach(con, adapter)
        assert len(unreg) == 1
        assert unreg[0] is con

    def test_detach_calls_unregister_even_without_prior_register(self):
        unreg = []

        class SafeAdapter:
            def register(self, con): pass
            def unregister(self, con):
                unreg.append(con)

        con = _make_con()
        fhir4ds.detach(con, SafeAdapter())
        assert len(unreg) == 1
