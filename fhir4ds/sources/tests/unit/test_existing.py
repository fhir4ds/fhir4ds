"""
Unit tests for fhir4ds.sources.existing — Phase 1: ExistingTableSource.

Acceptance criteria:
- ExistingTableSource("resources") passes schema validation against a correctly loaded table
- ExistingTableSource("resources") raises SchemaValidationError if any required column is missing
- ExistingTableSource("my_table") creates a resources view over my_table
- unregister() drops the view when _created_view is True
- unregister() is safe to call before register() — no exception
- register() is idempotent — calling twice does not error (CREATE OR REPLACE)
- Existing FHIRDataLoader workflows are unaffected — no breaking changes
"""

from __future__ import annotations

import pytest
import duckdb

from fhir4ds.sources.base import SchemaValidationError
from fhir4ds.sources.existing import ExistingTableSource
import fhir4ds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})


def _create_good_resources_table(con) -> None:
    """Directly creates a physical 'resources' table with the correct schema."""
    con.execute("""
        CREATE TABLE resources (
            id           VARCHAR,
            resourceType VARCHAR,
            resource     JSON,
            patient_ref  VARCHAR
        )
    """)
    con.execute("""
        INSERT INTO resources VALUES
            ('pat-1', 'Patient', '{"resourceType":"Patient","id":"pat-1"}', 'pat-1'),
            ('obs-1', 'Observation', '{"resourceType":"Observation","id":"obs-1"}', 'pat-1')
    """)


def _create_custom_table(con, table_name: str = "my_table") -> None:
    """Creates a table with the correct schema under a custom name."""
    con.execute(f"""
        CREATE TABLE {table_name} (
            id           VARCHAR,
            resourceType VARCHAR,
            resource     JSON,
            patient_ref  VARCHAR
        )
    """)
    con.execute(f"""
        INSERT INTO {table_name} VALUES
            ('pat-2', 'Patient', '{{"resourceType":"Patient","id":"pat-2"}}', 'pat-2')
    """)


# ---------------------------------------------------------------------------
# Tests: ExistingTableSource("resources")
# ---------------------------------------------------------------------------

class TestExistingTableSourceDefaultName:
    def test_passes_schema_validation_for_correct_table(self):
        con = _make_con()
        _create_good_resources_table(con)
        source = ExistingTableSource()
        source.register(con)  # must not raise

    def test_raises_schema_error_for_missing_id(self):
        con = _make_con()
        con.execute("""
            CREATE TABLE resources (
                resourceType VARCHAR,
                resource     JSON,
                patient_ref  VARCHAR
            )
        """)
        source = ExistingTableSource()
        with pytest.raises(SchemaValidationError, match="'id'"):
            source.register(con)

    def test_raises_schema_error_for_missing_resource(self):
        con = _make_con()
        con.execute("""
            CREATE TABLE resources (
                id           VARCHAR,
                resourceType VARCHAR,
                patient_ref  VARCHAR
            )
        """)
        source = ExistingTableSource()
        with pytest.raises(SchemaValidationError, match="'resource'"):
            source.register(con)

    def test_raises_schema_error_for_missing_patient_ref(self):
        con = _make_con()
        con.execute("""
            CREATE TABLE resources (
                id           VARCHAR,
                resourceType VARCHAR,
                resource     JSON
            )
        """)
        source = ExistingTableSource()
        with pytest.raises(SchemaValidationError, match="'patient_ref'"):
            source.register(con)

    def test_raises_schema_error_for_missing_resource_type(self):
        con = _make_con()
        con.execute("""
            CREATE TABLE resources (
                id          VARCHAR,
                resource    JSON,
                patient_ref VARCHAR
            )
        """)
        source = ExistingTableSource()
        with pytest.raises(SchemaValidationError, match="'resourceType'"):
            source.register(con)

    def test_does_not_create_view_for_default_table_name(self):
        con = _make_con()
        _create_good_resources_table(con)
        source = ExistingTableSource()
        source.register(con)
        assert source._created_view is False

    def test_register_is_idempotent(self):
        con = _make_con()
        _create_good_resources_table(con)
        source = ExistingTableSource()
        source.register(con)
        source.register(con)  # second call must not raise


# ---------------------------------------------------------------------------
# Tests: ExistingTableSource("my_table") — custom table name
# ---------------------------------------------------------------------------

class TestExistingTableSourceCustomName:
    def test_creates_resources_view_over_custom_table(self):
        con = _make_con()
        _create_custom_table(con, "my_table")
        source = ExistingTableSource("my_table")
        source.register(con)

        # The view should be queryable and return correct rows
        rows = con.execute("SELECT id FROM resources ORDER BY id").fetchall()
        assert rows == [("pat-2",)]

    def test_created_view_flag_set(self):
        con = _make_con()
        _create_custom_table(con)
        source = ExistingTableSource("my_table")
        source.register(con)
        assert source._created_view is True

    def test_unregister_drops_view(self):
        con = _make_con()
        _create_custom_table(con)
        source = ExistingTableSource("my_table")
        source.register(con)
        source.unregister(con)

        with pytest.raises(Exception):
            con.execute("SELECT * FROM resources").fetchall()

    def test_unregister_resets_created_view_flag(self):
        con = _make_con()
        _create_custom_table(con)
        source = ExistingTableSource("my_table")
        source.register(con)
        source.unregister(con)
        assert source._created_view is False

    def test_register_idempotent_for_custom_table(self):
        con = _make_con()
        _create_custom_table(con)
        source = ExistingTableSource("my_table")
        source.register(con)
        source.register(con)  # second call: CREATE OR REPLACE — must not error


# ---------------------------------------------------------------------------
# Tests: unregister() before register()
# ---------------------------------------------------------------------------

class TestUnregisterBeforeRegister:
    def test_unregister_before_register_no_exception(self):
        con = _make_con()
        source = ExistingTableSource()
        source.unregister(con)  # must not raise

    def test_unregister_before_register_custom_name_no_exception(self):
        con = _make_con()
        source = ExistingTableSource("my_table")
        source.unregister(con)  # must not raise


# ---------------------------------------------------------------------------
# Tests: supports_incremental()
# ---------------------------------------------------------------------------

class TestSupportsIncremental:
    def test_returns_false(self):
        source = ExistingTableSource()
        assert source.supports_incremental() is False


# ---------------------------------------------------------------------------
# Tests: API uniformity — attach/detach
# ---------------------------------------------------------------------------

class TestApiUniformity:
    def test_attach_with_existing_source(self):
        con = _make_con()
        _create_good_resources_table(con)
        source = ExistingTableSource()
        fhir4ds.attach(con, source)
        rows = con.execute("SELECT COUNT(*) FROM resources").fetchone()
        assert rows[0] == 2

    def test_detach_after_attach(self):
        con = _make_con()
        _create_custom_table(con)
        source = ExistingTableSource("my_table")
        fhir4ds.attach(con, source)
        fhir4ds.detach(con, source)
        # After detach, the view should be gone
        with pytest.raises(Exception):
            con.execute("SELECT * FROM resources").fetchall()

    def test_fhirdataloader_workflow_unaffected(self):
        """Verify that FHIRDataLoader usage still works normally."""
        from fhir4ds.cql.loader import FHIRDataLoader
        con = fhir4ds.create_connection(register_udfs=False)
        loader = FHIRDataLoader(con)
        # FHIRDataLoader creates a 'resources' table internally
        # We just verify the import and instantiation don't break
        assert loader is not None
