"""Unit tests for the HAPI PostgreSQL source adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pytest

from fhir4ds.sources import HapiPostgresSchema, HapiPostgresSource
from fhir4ds.sources.base import SchemaValidationError, quote_identifier, validate_schema
from fhir4ds.sources.hapi_postgres import _HAPI_POSTGRES_ATTACHMENT_NAME


def _mock_hapi_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
    att = quote_identifier(_HAPI_POSTGRES_ATTACHMENT_NAME)
    con.execute(f"ATTACH ':memory:' AS {att}")
    con.execute(f"CREATE SCHEMA {att}.public")
    con.execute(f"""
        CREATE TABLE {att}.public.hfj_resource (
            res_id BIGINT,
            res_type VARCHAR,
            fhir_id VARCHAR,
            res_ver BIGINT,
            res_updated TIMESTAMP,
            res_deleted_at TIMESTAMP
        )
    """)
    con.execute(f"""
        CREATE TABLE {att}.public.hfj_res_ver (
            pid BIGINT,
            res_id BIGINT,
            res_ver BIGINT,
            res_encoding VARCHAR,
            res_text_vc VARCHAR
        )
    """)
    return con


def _insert_mock_resource(
    con: duckdb.DuckDBPyConnection,
    *,
    res_id: int,
    res_type: str,
    fhir_id: str,
    resource_json: str,
    updated_at: str = "2026-05-23 00:00:00",
    encoding: str = "JSON",
    deleted: bool = False,
) -> None:
    att = quote_identifier(_HAPI_POSTGRES_ATTACHMENT_NAME)
    deleted_at = "2026-05-24 00:00:00" if deleted else None
    con.execute(
        f"INSERT INTO {att}.public.hfj_resource VALUES (?, ?, ?, 1, ?, ?)",
        [res_id, res_type, fhir_id, updated_at, deleted_at],
    )
    con.execute(
        f"INSERT INTO {att}.public.hfj_res_ver VALUES (?, ?, 1, ?, ?)",
        [res_id, res_id, encoding, resource_json],
    )


class TestHapiPostgresSourceSql:
    def test_default_select_matches_hapi_current_resource_tables(self):
        src = HapiPostgresSource("postgresql://hapi:hapi@localhost/hapi")
        sql = src._current_resources_select()

        assert '"fhir4ds_hapi_pg"."public"."hfj_resource"' in sql
        assert '"fhir4ds_hapi_pg"."public"."hfj_res_ver"' in sql
        assert 'v."res_id" = r."res_id"' in sql
        assert 'v."res_ver" = r."res_ver"' in sql
        assert 'v."res_encoding" = \'JSON\'' in sql
        assert 'v."res_text_vc" IS NOT NULL' in sql

    def test_custom_schema_identifiers_are_quoted(self):
        schema = HapiPostgresSchema(
            schema='clinical "schema"',
            resource_table="resource master",
            version_table="version-table",
            resource_pk_column="pid",
            version_resource_fk_column="resource_pid",
        )
        src = HapiPostgresSource(
            "postgresql://hapi:hapi@localhost/hapi",
            schema=schema,
            attachment_name='pg "hapi"',
        )
        sql = src._current_resources_select()

        assert '"pg ""hapi"""."clinical ""schema"""."resource master"' in sql
        assert '"pg ""hapi"""."clinical ""schema"""."version-table"' in sql
        assert 'v."resource_pid" = r."pid"' in sql

    def test_register_escapes_connection_string_literal(self, monkeypatch):
        import fhir4ds.sources.hapi_postgres as hapi_postgres

        executed: list[str] = []

        class FakeCon:
            def execute(self, sql, params=None):
                executed.append(sql)
                return self

            def fetchone(self):
                return [0]

        monkeypatch.setattr(hapi_postgres, "validate_schema", lambda con, name: None)
        src = HapiPostgresSource(
            "postgresql://user:pass@host/db'; DROP TABLE resources; --",
            fail_on_unsupported_storage=False,
        )
        src.register(FakeCon())

        attach_sql = next(sql for sql in executed if "ATTACH IF NOT EXISTS" in sql)
        assert "db''; DROP TABLE resources; --" in attach_sql
        assert "db'; DROP TABLE resources" not in attach_sql


class TestHapiPostgresSourceView:
    def test_register_projects_standard_resources_view(self):
        con = _mock_hapi_connection()
        _insert_mock_resource(
            con,
            res_id=1000,
            res_type="Patient",
            fhir_id="1000",
            resource_json='{"resourceType":"Patient","active":true}',
        )
        _insert_mock_resource(
            con,
            res_id=1001,
            res_type="Observation",
            fhir_id="obs-1",
            resource_json=(
                '{"resourceType":"Observation","subject":{"reference":"Patient/1000"}}'
            ),
        )

        src = HapiPostgresSource("postgresql://unused", fail_on_unsupported_storage=False)
        con.execute(f"""
            CREATE OR REPLACE VIEW resources AS {src._current_resources_select()}
        """)
        validate_schema(con, "HapiPostgresSource")

        rows = con.execute("""
            SELECT id, resourceType, patient_ref
            FROM resources
            ORDER BY id
        """).fetchall()
        assert rows == [
            ("1000", "Patient", "1000"),
            ("obs-1", "Observation", "1000"),
        ]

    def test_deleted_resources_are_excluded(self):
        con = _mock_hapi_connection()
        _insert_mock_resource(
            con,
            res_id=1000,
            res_type="Patient",
            fhir_id="1000",
            resource_json='{"resourceType":"Patient"}',
            deleted=True,
        )

        src = HapiPostgresSource("postgresql://unused", fail_on_unsupported_storage=False)
        con.execute(f"""
            CREATE OR REPLACE VIEW resources AS {src._current_resources_select()}
        """)
        assert con.execute("SELECT count(*) FROM resources").fetchone()[0] == 0

    def test_compressed_storage_detection_counts_unsupported_current_rows(self):
        con = _mock_hapi_connection()
        _insert_mock_resource(
            con,
            res_id=1000,
            res_type="Patient",
            fhir_id="1000",
            resource_json=None,
            encoding="JSONC",
        )

        src = HapiPostgresSource("postgresql://unused")
        assert src._unsupported_storage_count(con) == 1

    def test_schema_validation_catches_wrong_resource_type(self):
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": True})
        con.execute("""
            CREATE OR REPLACE VIEW resources AS
            SELECT
                '1000'::VARCHAR AS id,
                123::INTEGER AS resourceType,
                '{}'::JSON AS resource,
                '1000'::VARCHAR AS patient_ref
        """)
        with pytest.raises(SchemaValidationError, match="resourceType"):
            validate_schema(con, "HapiPostgresSource")


class TestHapiPostgresIncremental:
    def test_supports_incremental(self):
        src = HapiPostgresSource("postgresql://hapi:hapi@localhost/hapi")
        assert src.supports_incremental() is True

    def test_get_changed_patients_requires_register(self):
        src = HapiPostgresSource("postgresql://hapi:hapi@localhost/hapi")
        with pytest.raises(RuntimeError, match="before register"):
            src.get_changed_patients(datetime.now(timezone.utc))

    def test_get_changed_patients_uses_current_inline_resources(self):
        con = _mock_hapi_connection()
        _insert_mock_resource(
            con,
            res_id=1000,
            res_type="Patient",
            fhir_id="1000",
            resource_json='{"resourceType":"Patient"}',
            updated_at="2026-05-23 01:00:00",
        )
        _insert_mock_resource(
            con,
            res_id=1001,
            res_type="Observation",
            fhir_id="obs-1",
            resource_json=(
                '{"resourceType":"Observation","subject":{"reference":"Patient/1000"}}'
            ),
            updated_at="2026-05-23 02:00:00",
        )

        src = HapiPostgresSource("postgresql://unused", fail_on_unsupported_storage=False)
        src._con = con
        src._attached = True

        changed = src.get_changed_patients(
            datetime(2026, 5, 23, 1, 30, tzinfo=timezone.utc)
        )
        assert changed == ["1000"]
