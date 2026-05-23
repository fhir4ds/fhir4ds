"""Tests for HAPI PostgreSQL DQM materialization helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhir4ds.cli.main import main
from fhir4ds.dqm.config import DQMConfigError
from fhir4ds.dqm.hapi_materialization import (
    DEFAULT_DECODED_VIEW,
    FHIR4DS_MATERIALIZATION_TAG_SYSTEM,
    FHIR4DS_MEASURE_REPORT_IDENTIFIER_SYSTEM,
    FHIR4DS_MEASURE_REPORT_TAG_CODE,
    HapiMaterializationConfig,
    HapiMaterializedMeasure,
    HapiRetentionPolicy,
    _compiled_metrics_delta,
    _prepare_measure_report_for_materialization,
    _publish_measure_report_to_hapi,
    claim_pending_patients,
    materialization_sql,
    materialized_measure_hash,
    parse_materialization_config,
    persist_patient_measure_result,
    prune_materialization_history,
    reset_stale_processing,
    split_patient_result_rows,
)
from fhir4ds.dqm.types import AuditMode
from fhir4ds.sources import HapiPostgresSchema


def _write_measure_files(tmp_path: Path) -> tuple[Path, Path]:
    measure = tmp_path / "Measure-TestMeasure.json"
    cql = tmp_path / "TestMeasure.cql"
    measure.write_text(json.dumps({"resourceType": "Measure", "id": "TestMeasure"}))
    cql.write_text("library TestMeasure\n")
    return measure, cql


def test_materialization_sql_contains_queue_result_and_triggers():
    sql = materialization_sql()

    assert "{{" not in sql
    assert "CREATE TABLE IF NOT EXISTS fhir4ds_patient_change_queue" in sql
    assert "CREATE TABLE IF NOT EXISTS fhir4ds_measure_result" in sql
    assert "CREATE TABLE IF NOT EXISTS fhir4ds_measure_report" in sql
    assert "CREATE TABLE IF NOT EXISTS fhir4ds_measure_audit" in sql
    assert f'CREATE OR REPLACE VIEW "public"."{DEFAULT_DECODED_VIEW}"' in sql
    assert "fhir4ds_hapi_resource_json" in sql
    assert "lo_get(p_text_oid)" in sql
    assert "compile_cache_hits" in sql
    assert "fhir4ds_measure_result_run_idx" in sql
    assert "measure_report_json JSONB" in sql
    assert "resource_json JSONB NOT NULL" in sql
    assert "fhir4ds_measure_report_active_idx" in sql
    assert "persist_measure_report BOOLEAN" in sql
    assert "artifact_source TEXT NOT NULL DEFAULT 'files'" in sql
    assert "artifact_ref TEXT" in sql
    assert "ALTER COLUMN measure_path DROP NOT NULL" in sql
    assert "fhir4ds_is_generated_measure_report" in sql
    assert "LIKE 'fhir4ds-%'" in sql
    assert "pg_notify(" in sql
    assert "fhir4ds_hfj_resource_change" in sql


def test_materialization_sql_renders_custom_hapi_schema_and_channel():
    schema = HapiPostgresSchema(
        schema='custom "schema"',
        resource_table="resource master",
        version_table="version-table",
        resource_pk_column="pid",
        version_resource_fk_column="resource_pid",
        decoded_view="decoded resources",
    )

    sql = materialization_sql(schema, notification_channel="custom_channel")

    assert '"custom ""schema"""."resource master"' in sql
    assert '"custom ""schema"""."version-table"' in sql
    assert '"custom ""schema"""."decoded resources"' in sql
    assert "pg_notify(\n        'custom_channel'" in sql
    assert 'WHERE "resource_pid" = NEW."pid"' in sql


def test_parse_materialization_config_resolves_paths_and_defaults(tmp_path):
    measure, cql = _write_measure_files(tmp_path)
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "hapi": {"base_url": "http://localhost:18080/fhir"},
        "period": {"start": "2026-01-01", "end": "2026-12-31"},
        "defaults": {"audit_mode": "population", "narratives": True},
        "results": {
            "persist_audit": True,
            "persist_measure_report": True,
            "publish_measure_report_to_hapi": True,
        },
        "worker": {
            "batch_size": 25,
            "poll_interval_seconds": 5,
            "max_attempts": 4,
            "retry_backoff_seconds": 2.5,
            "processing_timeout_seconds": 120,
        },
        "retention": {
            "inactive_result_days": 90,
            "audit_days": 30,
            "run_days": 180,
        },
        "hapi_schema": {
            "schema": "custom",
            "resource_table": "resources",
            "version_table": "versions",
            "decoded_view": "decoded_resources",
        },
        "measures": [
            {
                "id": "CMS_TEST",
                "path": measure.name,
                "cql": cql.name,
                "version": "2026",
                "tags": ["smoke"],
            }
        ],
    }

    config = parse_materialization_config(raw, base_dir=tmp_path)

    assert config.postgres_connection_string == "postgresql://hapi:hapi@localhost/hapi"
    assert config.hapi_base_url == "http://localhost:18080/fhir"
    assert config.hapi_headers == {}
    assert config.hapi_timeout_seconds == 30.0
    assert config.batch_size == 25
    assert config.max_attempts == 4
    assert config.retry_backoff_seconds == 2.5
    assert config.processing_timeout_seconds == 120
    assert config.hapi_schema.schema == "custom"
    assert config.hapi_schema.resource_table == "resources"
    assert config.hapi_schema.version_table == "versions"
    assert config.hapi_schema.decoded_view == "decoded_resources"
    assert config.retention.inactive_result_days == 90
    assert config.retention.audit_days == 30
    assert config.retention.run_days == 180
    assert config.parameters["Measurement Period"] == ("2026-01-01", "2026-12-31")
    assert len(config.measures) == 1
    measure_config = config.measures[0]
    assert measure_config.measure_id == "CMS_TEST"
    assert measure_config.measure_path == measure
    assert measure_config.cql_path == cql
    assert measure_config.artifact_source == "files"
    assert measure_config.artifact_ref is None
    assert measure_config.measure_version == "2026"
    assert measure_config.audit_mode == AuditMode.POPULATION
    assert measure_config.persist_audit is True
    assert measure_config.persist_measure_report is True
    assert measure_config.publish_measure_report_to_hapi is True
    assert measure_config.generate_narratives is True


def test_parse_materialization_config_allows_hapi_artifact_source():
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "hapi": {"base_url": "http://localhost:18080/fhir"},
        "artifacts": {"source": "hapi"},
        "measures": [
            {
                "id": "CMS_TEST",
                "artifact_ref": "CMS122FHIRDiabetesAssessGreaterThan9Percent",
                "version": "2025",
            }
        ],
    }

    config = parse_materialization_config(raw)

    measure_config = config.measures[0]
    assert measure_config.measure_id == "CMS_TEST"
    assert measure_config.measure_path is None
    assert measure_config.cql_path is None
    assert measure_config.artifact_source == "hapi"
    assert measure_config.artifact_ref == "CMS122FHIRDiabetesAssessGreaterThan9Percent"


def test_parse_materialization_config_accepts_hapi_headers_and_timeout():
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "hapi": {
            "base_url": "http://localhost:18080/fhir",
            "headers": {"X-Tenant": "quality"},
            "bearer_token": "secret-token",
            "timeout_seconds": 15,
        },
        "artifacts": {"source": "hapi"},
        "measures": [{"id": "CMS_TEST", "artifact_ref": "MeasureRef"}],
    }

    config = parse_materialization_config(raw)

    assert config.hapi_headers == {
        "X-Tenant": "quality",
        "Authorization": "Bearer secret-token",
    }
    assert config.hapi_timeout_seconds == 15.0


def test_parse_materialization_config_requires_hapi_base_url_for_hapi_artifacts():
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "artifacts": {"source": "hapi"},
        "measures": [{"id": "CMS_TEST", "artifact_ref": "MeasureRef"}],
    }

    with pytest.raises(DQMConfigError, match="hapi.base_url"):
        parse_materialization_config(raw)


def test_parse_materialization_config_requires_hapi_base_url_for_publish(tmp_path):
    measure, _cql = _write_measure_files(tmp_path)
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "results": {"publish_measure_report_to_hapi": True},
        "measures": [{"path": str(measure)}],
    }

    with pytest.raises(DQMConfigError, match="hapi.base_url"):
        parse_materialization_config(raw, base_dir=tmp_path)


def test_parse_materialization_config_rejects_unsafe_channel(tmp_path):
    measure, _cql = _write_measure_files(tmp_path)
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "worker": {"notification_channel": "bad;notify"},
        "measures": [{"path": str(measure)}],
    }

    with pytest.raises(DQMConfigError, match="notification_channel"):
        parse_materialization_config(raw, base_dir=tmp_path)


def test_parse_materialization_config_rejects_unknown_hapi_schema_field(tmp_path):
    measure, _cql = _write_measure_files(tmp_path)
    raw = {
        "postgres": {
            "connection_string": "postgresql://hapi:hapi@localhost/hapi",
            "hapi_schema": {"bad_column": "x"},
        },
        "measures": [{"path": str(measure)}],
    }

    with pytest.raises(DQMConfigError, match="unknown field"):
        parse_materialization_config(raw, base_dir=tmp_path)


def test_parse_materialization_config_rejects_invalid_retention(tmp_path):
    measure, _cql = _write_measure_files(tmp_path)
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "retention": {"audit_days": 0},
        "measures": [{"path": str(measure)}],
    }

    with pytest.raises(DQMConfigError, match="retention.audit_days"):
        parse_materialization_config(raw, base_dir=tmp_path)


def test_split_patient_result_rows_keeps_compact_and_full_audit():
    compact, audit = split_patient_result_rows(
        [
            {
                "patient_id": "p1",
                "initial_population": {
                    "result": True,
                    "evidence": [{"target": "Encounter/e1"}],
                },
                "evidence_Helper": [{"target": "Observation/o1"}],
                "numerator": False,
            }
        ]
    )

    assert compact == {
        "rows": [
            {
                "patient_id": "p1",
                "initial_population": True,
                "numerator": False,
            }
        ]
    }
    assert audit["rows"][0]["initial_population"]["evidence"][0]["target"] == "Encounter/e1"
    assert audit["rows"][0]["evidence_Helper"][0]["target"] == "Observation/o1"


def test_prepare_measure_report_for_materialization_tags_and_identifies(tmp_path):
    measure, cql = _write_measure_files(tmp_path)
    report = {
        "resourceType": "MeasureReport",
        "meta": {"profile": ["http://example.com/Profile"]},
    }
    measure_config = HapiMaterializedMeasure(
        measure_id="CMS TEST",
        measure_path=measure,
        cql_path=cql,
    )

    prepared = _prepare_measure_report_for_materialization(
        report,
        measure=measure_config,
        patient_id="patient-1",
    )
    _prepare_measure_report_for_materialization(
        prepared,
        measure=measure_config,
        patient_id="patient-1",
    )

    assert prepared["id"].startswith("fhir4ds-CMS-TEST-")
    assert len(prepared["id"]) <= 64
    assert prepared["meta"]["profile"] == ["http://example.com/Profile"]
    tags = prepared["meta"]["tag"]
    matching_tags = [
        tag
        for tag in tags
        if tag.get("system") == FHIR4DS_MATERIALIZATION_TAG_SYSTEM
        and tag.get("code") == FHIR4DS_MEASURE_REPORT_TAG_CODE
    ]
    assert len(matching_tags) == 1
    identifiers = prepared["identifier"]
    assert identifiers == [
        {
            "system": FHIR4DS_MEASURE_REPORT_IDENTIFIER_SYSTEM,
            "value": "CMS TEST|patient-1",
        }
    ]


def test_publish_measure_report_to_hapi_puts_resource(monkeypatch):
    import fhir4ds.dqm.hapi_materialization as hapi_materialization

    requests = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b""

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return FakeResponse()

    monkeypatch.setattr(hapi_materialization.urllib.request, "urlopen", fake_urlopen)

    _publish_measure_report_to_hapi(
        HapiMaterializationConfig(
            postgres_connection_string="postgresql://hapi:hapi@localhost/hapi",
            hapi_base_url="http://localhost:18080/fhir",
            hapi_headers={"Authorization": "Bearer token"},
            hapi_timeout_seconds=12.5,
        ),
        {"resourceType": "MeasureReport", "id": "report 1"},
    )

    request, timeout = requests[0]
    assert timeout == 12.5
    assert request.full_url == "http://localhost:18080/fhir/MeasureReport/report%201"
    assert request.get_method() == "PUT"
    assert request.headers["Authorization"] == "Bearer token"
    assert json.loads(request.data.decode("utf-8"))["resourceType"] == "MeasureReport"


def test_persist_patient_measure_result_includes_measure_report_json(tmp_path):
    measure, cql = _write_measure_files(tmp_path)
    executed: list[tuple[str, list[object]]] = []

    class FakeCursor:
        def fetchone(self):
            return (123,)

    class FakeConn:
        def execute(self, sql, params=None):
            executed.append((sql, list(params or [])))
            return FakeCursor()

        def commit(self):
            return None

    result_id = persist_patient_measure_result(
        FakeConn(),
        run_id=9,
        patient_id="patient-1",
        measure=HapiMaterializedMeasure(
            measure_id="CMS_TEST",
            measure_path=measure,
            cql_path=cql,
        ),
        status="ok",
        result_json={"rows": []},
        summary_json={"total_patients": 1},
        measure_report_json={"resourceType": "MeasureReport", "id": "mr-1"},
        input_watermark=None,
        config_hash="hash",
    )

    assert result_id == 123
    insert_sql, insert_params = next(
        (sql, params) for sql, params in executed if "INSERT INTO fhir4ds_measure_result" in sql
    )
    assert "measure_report_json" in insert_sql
    assert '{"resourceType": "MeasureReport", "id": "mr-1"}' in insert_params
    report_sql, report_params = next(
        (sql, params) for sql, params in executed if "INSERT INTO fhir4ds_measure_report" in sql
    )
    assert "resource_json" in report_sql
    assert report_params[5] == "mr-1"
    assert report_params[7] is False


def test_compiled_metrics_delta_preserves_cumulative_snapshot():
    before = {"cache_hits": 1, "compile_ms": 10.0, "execute_count": 2}
    after = {
        "cache_hits": 3,
        "cache_misses": 1,
        "compile_ms": 25.5,
        "execute_count": 5,
        "last_patient_count": 4,
    }

    metrics = _compiled_metrics_delta(before, after)

    assert metrics["cache_hits"] == 2
    assert metrics["cache_misses"] == 1
    assert metrics["compile_ms"] == 15.5
    assert metrics["execute_count"] == 3
    assert metrics["last_patient_count"] == 4
    assert metrics["cumulative"] == after


def test_materialized_measure_hash_changes_with_parameters(tmp_path):
    measure, cql = _write_measure_files(tmp_path)
    base = HapiMaterializedMeasure(
        measure_id="CMS_TEST",
        measure_path=measure,
        cql_path=cql,
        parameters={"Measurement Period": ("2026-01-01", "2026-12-31")},
    )
    changed = HapiMaterializedMeasure(
        measure_id="CMS_TEST",
        measure_path=measure,
        cql_path=cql,
        parameters={"Measurement Period": ("2027-01-01", "2027-12-31")},
    )

    assert materialized_measure_hash(base) != materialized_measure_hash(changed)


def test_materialized_measure_hash_changes_with_artifact_source(tmp_path):
    measure, cql = _write_measure_files(tmp_path)
    file_measure = HapiMaterializedMeasure(
        measure_id="CMS_TEST",
        measure_path=measure,
        cql_path=cql,
        artifact_source="files",
    )
    hapi_measure = HapiMaterializedMeasure(
        measure_id="CMS_TEST",
        artifact_source="hapi",
        artifact_ref="CMS_TEST",
    )

    assert materialized_measure_hash(file_measure) != materialized_measure_hash(
        hapi_measure
    )


def test_prune_materialization_history_uses_configured_retention(monkeypatch):
    import fhir4ds.dqm.hapi_materialization as hapi_materialization

    executed: list[tuple[str, list[int]]] = []

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def execute(self, sql, params=None):
            executed.append((sql, list(params or [])))
            return self

        def fetchall(self):
            return [(1,), (2,)]

        def commit(self):
            return None

    class FakePsycopg:
        @staticmethod
        def connect(connection_string):
            assert connection_string == "postgresql://hapi:hapi@localhost/hapi"
            return FakeConn()

    monkeypatch.setattr(hapi_materialization, "require_psycopg", lambda: FakePsycopg)

    deleted = prune_materialization_history(
        "postgresql://hapi:hapi@localhost/hapi",
        HapiRetentionPolicy(inactive_result_days=90, audit_days=30, run_days=180),
    )

    assert deleted == {"audits": 2, "inactive_results": 2, "runs": 2}
    assert [params for _sql, params in executed] == [[30], [90], [180]]
    assert any("DELETE FROM fhir4ds_measure_audit" in sql for sql, _params in executed)
    assert any("DELETE FROM fhir4ds_measure_result" in sql for sql, _params in executed)
    assert any("DELETE FROM fhir4ds_measure_run" in sql for sql, _params in executed)


def test_claim_pending_patients_retries_failed_rows_with_backoff():
    executed: list[tuple[str, list[float]]] = []

    class FakeCursor:
        def fetchall(self):
            return [("p1", "watermark")]

    class FakeConn:
        def execute(self, sql, params=None):
            executed.append((sql, list(params or [])))
            return FakeCursor()

        def commit(self):
            return None

    rows = claim_pending_patients(
        FakeConn(),
        10,
        max_attempts=5,
        retry_backoff_seconds=2.5,
    )

    assert rows[0].patient_id == "p1"
    sql, params = executed[0]
    assert "status = 'failed'" in sql
    assert "attempts < %s" in sql
    assert params == [5, 2.5, 10]


def test_reset_stale_processing_marks_exhausted_rows_failed():
    executed: list[tuple[str, list[float]]] = []

    class FakeCursor:
        def fetchall(self):
            return [("p1",), ("p2",)]

    class FakeConn:
        def execute(self, sql, params=None):
            executed.append((sql, list(params or [])))
            return FakeCursor()

        def commit(self):
            return None

    count = reset_stale_processing(
        FakeConn(),
        processing_timeout_seconds=120,
        max_attempts=3,
    )

    assert count == 2
    sql, params = executed[0]
    assert "WHEN attempts >= %s THEN 'failed'" in sql
    assert "Processing timeout; max attempts reached" in sql
    assert params == [3, 3, 3, 120]


def test_hapi_cli_requires_nested_subcommand(capsys):
    exit_code = main(["dqm", "hapi"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "requires a subcommand" in captured.err
