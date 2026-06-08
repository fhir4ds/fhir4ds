"""Tests for Mongo DQM materialization helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhir4ds.cli.main import main
from fhir4ds.dqm.config import DQMConfigError
from fhir4ds.dqm.mongo_materialization import (
    FHIR4DS_MATERIALIZATION_TAG_SYSTEM,
    FHIR4DS_MEASURE_REPORT_TAG_CODE,
    MongoMaterializationConfig,
    MongoMaterializedMeasure,
    _prepare_measure_report_for_materialization,
    enqueue_patient_change_from_mongo_change,
    load_mongo_materialization_config,
    parse_mongo_materialization_config,
    publish_measure_report_to_mongo,
    split_patient_result_rows,
)
from fhir4ds.dqm.types import AuditMode
from fhir4ds.sources import MongoFhirServerSchema


def _write_measure_files(tmp_path: Path) -> tuple[Path, Path]:
    measure = tmp_path / "Measure-TestMeasure.json"
    cql = tmp_path / "TestMeasure.cql"
    measure.write_text(json.dumps({"resourceType": "Measure", "id": "TestMeasure"}))
    cql.write_text("library TestMeasure\n")
    return measure, cql


class FakeCollection:
    def __init__(self):
        self.update_calls = []

    def update_one(self, query, update, upsert=False):
        self.update_calls.append((query, update, upsert))


class FakeDB:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        self.collections.setdefault(name, FakeCollection())
        return self.collections[name]


class FakeClient:
    def __init__(self):
        self.dbs = {}
        self.closed = False

    def __getitem__(self, name):
        self.dbs.setdefault(name, FakeDB())
        return self.dbs[name]

    def close(self):
        self.closed = True


def test_parse_mongo_materialization_config_resolves_paths_and_defaults(tmp_path):
    measure, cql = _write_measure_files(tmp_path)
    raw = {
        "mongo": {
            "connection_string": "mongodb://localhost:27017",
            "database_name": "fhir",
            "materialization_database": "fhir4ds",
            "source_schema": {
                "collection_strategy": "shared",
                "shared_collection": "resources_current",
                "shared_resource_path": "$.resource",
                "shared_id_path": "$.resource.id",
                "shared_resource_type_path": "$.resource.resourceType",
                "resource_types": ["Patient", "Observation", "MeasureReport"],
            },
            "collections": {"queue": "queue", "reports": "reports"},
        },
        "period": {"start": "2026-01-01", "end": "2026-12-31"},
        "defaults": {"audit_mode": "population", "narratives": True},
        "results": {
            "persist_audit": True,
            "persist_measure_report": False,
            "publish_measure_report_to_mongo": True,
        },
        "worker": {
            "batch_size": 25,
            "include_delete_pre_images": True,
            "source_patient_pushdown": False,
        },
        "measures": [
            {
                "id": "CMS_TEST",
                "path": measure.name,
                "cql": cql.name,
                "version": "2026",
            }
        ],
    }

    config = parse_mongo_materialization_config(raw, base_dir=tmp_path)

    assert config.connection_string == "mongodb://localhost:27017"
    assert config.source_schema.collection_strategy == "shared"
    assert config.source_schema.shared_resource_path == "$.resource"
    assert config.materialization_database == "fhir4ds"
    assert config.collections.queue == "queue"
    assert config.collections.reports == "reports"
    assert config.batch_size == 25
    assert config.include_delete_pre_images is True
    assert config.source_patient_pushdown is False
    assert config.parameters["Measurement Period"] == ("2026-01-01", "2026-12-31")
    measure_config = config.measures[0]
    assert measure_config.measure_id == "CMS_TEST"
    assert measure_config.measure_path == measure
    assert measure_config.cql_path == cql
    assert measure_config.measure_version == "2026"
    assert measure_config.audit_mode == AuditMode.POPULATION
    assert measure_config.persist_audit is True
    assert measure_config.persist_measure_report is True
    assert measure_config.publish_measure_report_to_mongo is True
    assert measure_config.generate_narratives is True


def test_load_mongo_materialization_config_wraps_invalid_json(tmp_path):
    config_path = tmp_path / "mongo.json"
    config_path.write_text("{")

    with pytest.raises(DQMConfigError, match="Invalid JSON Mongo materialization config"):
        load_mongo_materialization_config(config_path)


def test_parse_mongo_materialization_config_rejects_non_object_libraries():
    raw = {
        "mongo": {
            "connection_string": "mongodb://localhost:27017",
            "database_name": "fhir",
        },
        "libraries": [],
    }

    with pytest.raises(DQMConfigError, match="'libraries' must be an object"):
        parse_mongo_materialization_config(raw)


def test_parse_mongo_materialization_config_rejects_non_object_terminology():
    raw = {
        "mongo": {
            "connection_string": "mongodb://localhost:27017",
            "database_name": "fhir",
        },
        "terminology": [],
    }

    with pytest.raises(DQMConfigError, match="'terminology' must be an object"):
        parse_mongo_materialization_config(raw)


def test_prepare_measure_report_tags_and_identifies():
    report = {"resourceType": "MeasureReport", "meta": {"profile": ["p"]}}
    measure = MongoMaterializedMeasure(measure_id="CMS TEST")

    prepared = _prepare_measure_report_for_materialization(
        report,
        measure=measure,
        patient_id="patient-1",
    )
    _prepare_measure_report_for_materialization(
        prepared,
        measure=measure,
        patient_id="patient-1",
    )

    assert prepared["id"].startswith("fhir4ds-CMS-TEST-")
    tags = prepared["meta"]["tag"]
    assert [
        tag
        for tag in tags
        if tag.get("system") == FHIR4DS_MATERIALIZATION_TAG_SYSTEM
        and tag.get("code") == FHIR4DS_MEASURE_REPORT_TAG_CODE
    ]
    assert len(tags) == 1
    assert prepared["identifier"][0]["value"] == "CMS TEST|patient-1"


def test_enqueue_patient_change_from_mongo_change_extracts_patient_ref():
    queue = FakeCollection()
    config = MongoMaterializationConfig(
        connection_string="mongodb://localhost:27017",
        source_schema=MongoFhirServerSchema(
            resource_types=("Patient", "Observation", "MeasureReport"),
        ),
    )
    change = {
        "operationType": "insert",
        "ns": {"coll": "Observation_4_0_0"},
        "fullDocument": {
            "resourceType": "Observation",
            "id": "obs-1",
            "subject": {"reference": "Patient/pat-1"},
        },
    }

    assert enqueue_patient_change_from_mongo_change(queue, config, change) is True

    query, update, upsert = queue.update_calls[0]
    assert query == {"_id": "pat-1"}
    assert update["$set"]["patient_id"] == "pat-1"
    assert update["$set"]["last_resource_type"] == "Observation"
    assert update["$set"]["last_resource_id"] == "obs-1"
    assert upsert is True


def test_enqueue_patient_change_ignores_generated_measure_report():
    queue = FakeCollection()
    config = MongoMaterializationConfig(
        connection_string="mongodb://localhost:27017",
        source_schema=MongoFhirServerSchema(resource_types=("MeasureReport",)),
    )
    change = {
        "operationType": "insert",
        "ns": {"coll": "MeasureReport_4_0_0"},
        "fullDocument": {
            "resourceType": "MeasureReport",
            "id": "fhir4ds-report",
            "meta": {
                "tag": [
                    {
                        "system": FHIR4DS_MATERIALIZATION_TAG_SYSTEM,
                        "code": FHIR4DS_MEASURE_REPORT_TAG_CODE,
                    }
                ]
            },
        },
    }

    assert enqueue_patient_change_from_mongo_change(queue, config, change) is False
    assert queue.update_calls == []


def test_publish_measure_report_to_mongo_uses_per_resource_collection():
    client = FakeClient()
    config = MongoMaterializationConfig(
        connection_string="mongodb://localhost:27017",
        source_schema=MongoFhirServerSchema(resource_types=("Patient", "Observation")),
    )
    report = {"resourceType": "MeasureReport", "id": "mr-1", "status": "complete"}

    publish_measure_report_to_mongo(config, report, client=client)

    collection = client.dbs["fhir"].collections["MeasureReport_4_0_0"]
    query, update, upsert = collection.update_calls[0]
    assert query == {"id": "mr-1"}
    assert update["$set"] == report
    assert upsert is True


def test_publish_measure_report_to_mongo_supports_wrapped_shared_collection():
    client = FakeClient()
    config = MongoMaterializationConfig(
        connection_string="mongodb://localhost:27017",
        source_schema=MongoFhirServerSchema(
            collection_strategy="shared",
            shared_collection="resources_current",
            shared_resource_path="$.payload.resource",
            shared_id_path="$.payload.resource.id",
            shared_resource_type_path="$.payload.resource.resourceType",
            resource_types=("Patient", "MeasureReport"),
        ),
    )
    report = {"resourceType": "MeasureReport", "id": "mr-1"}

    publish_measure_report_to_mongo(config, report, client=client)

    collection = client.dbs["fhir"].collections["resources_current"]
    query, update, _upsert = collection.update_calls[0]
    assert query == {"payload.resource.id": "mr-1"}
    assert update["$set"] == {"payload.resource": report}


def test_split_patient_result_rows_keeps_compact_and_full_audit():
    compact, audit = split_patient_result_rows(
        [
            {
                "patient_id": "patient-1",
                "initial_population": {
                    "result": True,
                    "evidence": [{"target": "Encounter/e1"}],
                },
                "evidence_Helper": [{"target": "Observation/o1"}],
            }
        ]
    )

    assert compact["rows"] == [
        {"patient_id": "patient-1", "initial_population": True}
    ]
    assert audit["rows"][0]["initial_population"]["evidence"][0]["target"] == "Encounter/e1"
    assert audit["rows"][0]["evidence_Helper"][0]["target"] == "Observation/o1"


def test_mongo_cli_requires_nested_subcommand(capsys):
    exit_code = main(["dqm", "mongo"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "requires a subcommand" in captured.err


def test_mongo_cli_status_prints_json(monkeypatch, tmp_path, capsys):
    import fhir4ds.cli.dqm as dqm_cli

    measure, _cql = _write_measure_files(tmp_path)
    config_path = tmp_path / "mongo.yaml"
    config_path.write_text(
        f"""
mongo:
  connection_string: mongodb://localhost:27017
measures:
  - path: {measure.name}
"""
    )

    monkeypatch.setattr(
        dqm_cli,
        "mongo_materialization_status",
        lambda config, limit=5: {"queue": {"pending": 1}, "limit": limit},
    )

    exit_code = main(["dqm", "mongo", "status", "--config", str(config_path), "--limit", "2"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {"queue": {"pending": 1}, "limit": 2}
