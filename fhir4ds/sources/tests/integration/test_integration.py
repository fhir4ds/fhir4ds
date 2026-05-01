"""
Integration tests for fhir4ds.sources — Phase 5: API Ergonomics.

Tests that verify:
- All adapters are importable directly from fhir4ds.sources
- create_connection(source=...) mounts the adapter automatically
- create_connection() with no source behaves identically to existing behavior
- End-to-end DQM-style queries work against mounted sources
"""

from __future__ import annotations

import json
import os
import tempfile

import duckdb
import pytest

import fhir4ds
from fhir4ds import sources
from fhir4ds.sources import (
    CSVSource,
    CloudCredentials,
    ExistingTableSource,
    FileSystemSource,
    PostgresSource,
    PostgresTableMapping,
    SchemaValidationError,
    SourceAdapter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_parquet(path: str, rows: list[dict]) -> None:
    con = duckdb.connect(":memory:")
    import json as _json
    values = ", ".join(
        f"('{r['id']}', '{r['resourceType']}', '{_json.dumps(r['resource'])}'::JSON, '{r['patient_ref']}')"
        for r in rows
    )
    con.execute(f"""
        COPY (
            SELECT * FROM (VALUES {values}) t(id, resourceType, resource, patient_ref)
        ) TO '{path}' (FORMAT PARQUET)
    """)


_SAMPLE_ROWS = [
    {
        "id": "pat-1",
        "resourceType": "Patient",
        "resource": {"resourceType": "Patient", "id": "pat-1"},
        "patient_ref": "pat-1",
    },
    {
        "id": "obs-1",
        "resourceType": "Observation",
        "resource": {"resourceType": "Observation", "id": "obs-1", "subject": {"reference": "Patient/pat-1"}},
        "patient_ref": "pat-1",
    },
]


# ---------------------------------------------------------------------------
# Tests: all adapters importable from fhir4ds.sources
# ---------------------------------------------------------------------------

class TestImports:
    def test_source_adapter_importable(self):
        assert SourceAdapter is not None

    def test_schema_validation_error_importable(self):
        assert SchemaValidationError is not None

    def test_filesystem_source_importable(self):
        assert FileSystemSource is not None

    def test_cloud_credentials_importable(self):
        assert CloudCredentials is not None

    def test_postgres_source_importable(self):
        assert PostgresSource is not None

    def test_postgres_table_mapping_importable(self):
        assert PostgresTableMapping is not None

    def test_existing_table_source_importable(self):
        assert ExistingTableSource is not None

    def test_csv_source_importable(self):
        assert CSVSource is not None

    def test_sources_module_has_all_attribute(self):
        all_names = sources.__all__
        for name in [
            "SourceAdapter", "SchemaValidationError", "FileSystemSource",
            "CloudCredentials", "PostgresSource", "PostgresTableMapping",
            "ExistingTableSource", "CSVSource",
        ]:
            assert name in all_names, f"'{name}' missing from fhir4ds.sources.__all__"

    def test_fhir4ds_namespace_has_attach(self):
        assert hasattr(fhir4ds, "attach")
        assert callable(fhir4ds.attach)

    def test_fhir4ds_namespace_has_detach(self):
        assert hasattr(fhir4ds, "detach")
        assert callable(fhir4ds.detach)

    def test_fhir4ds_namespace_has_sources(self):
        assert hasattr(fhir4ds, "sources")

    def test_fhir4ds_namespace_has_schema_validation_error(self):
        assert hasattr(fhir4ds, "SchemaValidationError")


# ---------------------------------------------------------------------------
# Tests: create_connection(source=...) — Zero-ETL convenience
# ---------------------------------------------------------------------------

class TestCreateConnectionWithSource:
    def test_create_connection_with_parquet_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            _write_parquet(path, _SAMPLE_ROWS)

            source = FileSystemSource(path)
            con = fhir4ds.create_connection(register_udfs=False, source=source)

            rows = con.execute("SELECT COUNT(*) FROM resources").fetchone()
            assert rows[0] == 2

    def test_create_connection_with_existing_source(self):
        # Pre-create a resources table in a separate connection, then
        # use ExistingTableSource to validate it
        inner_con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
        inner_con.execute("""
            CREATE TABLE resources (
                id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR
            )
        """)
        inner_con.execute("""
            INSERT INTO resources VALUES ('pat-1', 'Patient', '{}', 'pat-1')
        """)
        source = ExistingTableSource()
        source.register(inner_con)  # validates schema
        row = inner_con.execute("SELECT COUNT(*) FROM resources").fetchone()
        assert row[0] == 1

    def test_create_connection_with_csv_source(self):
        import csv
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "patients.csv")
            with open(path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["pid", "gender"])
                writer.writeheader()
                writer.writerow({"pid": "p1", "gender": "male"})

            projection = """
                SELECT
                    pid::VARCHAR AS id,
                    'Patient'::VARCHAR AS resourceType,
                    json_object('resourceType','Patient','id',pid)::JSON AS resource,
                    pid::VARCHAR AS patient_ref
                FROM {source}
            """
            source = CSVSource(path, projection)
            con = fhir4ds.create_connection(register_udfs=False, source=source)
            row = con.execute("SELECT id FROM resources").fetchone()
            assert row[0] == "p1"

    def test_create_connection_without_source_unchanged_behavior(self):
        """create_connection() with no source behaves identically to before."""
        con = fhir4ds.create_connection(register_udfs=False)
        assert con is not None
        # No 'resources' view exists yet — that's expected
        with pytest.raises(Exception):
            con.execute("SELECT * FROM resources").fetchall()

    def test_create_connection_raises_type_error_for_non_adapter(self):
        with pytest.raises(TypeError, match="SourceAdapter"):
            fhir4ds.create_connection(register_udfs=False, source=object())


# ---------------------------------------------------------------------------
# Tests: end-to-end query against mounted sources
# ---------------------------------------------------------------------------

class TestEndToEndQueries:
    def test_query_resources_view_from_parquet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            _write_parquet(path, _SAMPLE_ROWS)

            con = fhir4ds.create_connection(register_udfs=False, source=FileSystemSource(path))

            patients = con.execute("""
                SELECT id FROM resources WHERE resourceType = 'Patient'
            """).fetchall()
            assert patients == [("pat-1",)]

            observations = con.execute("""
                SELECT id FROM resources WHERE resourceType = 'Observation'
            """).fetchall()
            assert observations == [("obs-1",)]

    def test_filter_by_patient_ref(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "resources.parquet")
            _write_parquet(path, _SAMPLE_ROWS)

            con = fhir4ds.create_connection(register_udfs=False, source=FileSystemSource(path))

            rows = con.execute("""
                SELECT id FROM resources WHERE patient_ref = 'pat-1' ORDER BY id
            """).fetchall()
            assert len(rows) == 2  # both resources belong to pat-1

    def test_existing_table_source_query(self):
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
        con.execute("""
            CREATE TABLE resources (
                id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR
            )
        """)
        con.execute("""
            INSERT INTO resources VALUES
                ('pat-1', 'Patient', '{"resourceType":"Patient"}', 'pat-1'),
                ('cond-1', 'Condition', '{"resourceType":"Condition"}', 'pat-1')
        """)

        source = ExistingTableSource()
        fhir4ds.attach(con, source)

        count = con.execute("SELECT COUNT(*) FROM resources").fetchone()[0]
        assert count == 2


# ---------------------------------------------------------------------------
# Tests: no regressions on existing FHIRDataLoader workflow
# ---------------------------------------------------------------------------

class TestNoRegressions:
    def test_fhirdataloader_import_still_works(self):
        from fhir4ds.cql.loader import FHIRDataLoader
        assert FHIRDataLoader is not None

    def test_create_connection_default_behavior_unchanged(self):
        con = fhir4ds.create_connection(register_udfs=False)
        assert con is not None
        # Connection is functional
        result = con.execute("SELECT 42").fetchone()
        assert result[0] == 42

    def test_fhir4ds_version_accessible(self):
        assert fhir4ds.__version__ is not None
