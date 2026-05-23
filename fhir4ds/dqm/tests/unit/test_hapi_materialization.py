"""Tests for HAPI PostgreSQL DQM materialization helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhir4ds.cli.main import main
from fhir4ds.dqm.config import DQMConfigError
from fhir4ds.dqm.hapi_materialization import (
    HapiMaterializedMeasure,
    _compiled_metrics_delta,
    materialization_sql,
    materialized_measure_hash,
    parse_materialization_config,
    split_patient_result_rows,
)
from fhir4ds.dqm.types import AuditMode


def _write_measure_files(tmp_path: Path) -> tuple[Path, Path]:
    measure = tmp_path / "Measure-TestMeasure.json"
    cql = tmp_path / "TestMeasure.cql"
    measure.write_text(json.dumps({"resourceType": "Measure", "id": "TestMeasure"}))
    cql.write_text("library TestMeasure\n")
    return measure, cql


def test_materialization_sql_contains_queue_result_and_triggers():
    sql = materialization_sql()

    assert "CREATE TABLE IF NOT EXISTS fhir4ds_patient_change_queue" in sql
    assert "CREATE TABLE IF NOT EXISTS fhir4ds_measure_result" in sql
    assert "CREATE TABLE IF NOT EXISTS fhir4ds_measure_audit" in sql
    assert "compile_cache_hits" in sql
    assert "fhir4ds_measure_result_run_idx" in sql
    assert "pg_notify(" in sql
    assert "fhir4ds_hfj_resource_change" in sql


def test_parse_materialization_config_resolves_paths_and_defaults(tmp_path):
    measure, cql = _write_measure_files(tmp_path)
    raw = {
        "postgres": {"connection_string": "postgresql://hapi:hapi@localhost/hapi"},
        "period": {"start": "2026-01-01", "end": "2026-12-31"},
        "defaults": {"audit_mode": "population", "narratives": True},
        "results": {"persist_audit": True},
        "worker": {"batch_size": 25, "poll_interval_seconds": 5},
        "hapi_schema": {
            "schema": "custom",
            "resource_table": "resources",
            "version_table": "versions",
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
    assert config.batch_size == 25
    assert config.hapi_schema.schema == "custom"
    assert config.hapi_schema.resource_table == "resources"
    assert config.hapi_schema.version_table == "versions"
    assert config.parameters["Measurement Period"] == ("2026-01-01", "2026-12-31")
    assert len(config.measures) == 1
    measure_config = config.measures[0]
    assert measure_config.measure_id == "CMS_TEST"
    assert measure_config.measure_path == measure
    assert measure_config.cql_path == cql
    assert measure_config.measure_version == "2026"
    assert measure_config.audit_mode == AuditMode.POPULATION
    assert measure_config.persist_audit is True
    assert measure_config.generate_narratives is True


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


def test_hapi_cli_requires_nested_subcommand(capsys):
    exit_code = main(["dqm", "hapi"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "requires a subcommand" in captured.err
