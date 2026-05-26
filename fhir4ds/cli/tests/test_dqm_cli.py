"""Tests for the DQM CLI."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import fhir4ds.cli.dqm as dqm_cli
from fhir4ds.cli.main import main
from fhir4ds.dqm.batch import inspect_config, validate_config
from fhir4ds.dqm.config import AuditSpec, DQMRunConfig, MeasureSpec, OutputSpec, SourceSpec
from fhir4ds.dqm.types import AuditMode


def _write_simple_measure(tmp_path: Path) -> tuple[Path, Path, Path]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "patient-1.json").write_text(
        json.dumps(
            {
                "resourceType": "Patient",
                "id": "p1",
                "gender": "male",
                "birthDate": "1990-01-01",
            }
        )
    )
    (data_dir / "patient-2.json").write_text(
        json.dumps(
            {
                "resourceType": "Patient",
                "id": "p2",
                "gender": "female",
                "birthDate": "1990-01-01",
            }
        )
    )

    measure_path = tmp_path / "Measure-TestMeasure.json"
    measure_path.write_text(
        json.dumps(
            {
                "resourceType": "Measure",
                "id": "TestMeasure",
                "library": ["http://example.org/Library/TestMeasure"],
                "group": [
                    {
                        "id": "primary",
                        "population": [
                            {
                                "code": {"coding": [{"code": "initial-population"}]},
                                "criteria": {"expression": "Initial Population"},
                            },
                            {
                                "code": {"coding": [{"code": "denominator"}]},
                                "extension": [
                                    {
                                        "url": "http://hl7.org/fhir/StructureDefinition/cqf-supportingEvidenceDefinition",
                                        "valueExpression": {
                                            "name": "HelperDefine",
                                            "description": "Patient has a birth date.",
                                            "language": "text/cql-identifier",
                                            "expression": "Helper Define",
                                        },
                                    }
                                ],
                                "criteria": {"expression": "Denominator"},
                            },
                            {
                                "code": {"coding": [{"code": "numerator"}]},
                                "criteria": {"expression": "Numerator"},
                            },
                        ]
                    }
                ],
            }
        )
    )

    cql_path = tmp_path / "TestMeasure.cql"
    cql_path.write_text(
        """library TestMeasure
using FHIR version '4.0.1'
context Patient
define "Initial Population":
    true
define "Denominator":
    true
define "Numerator":
    Patient.gender = 'male'
define "Helper Define":
    Patient.birthDate is not null
"""
    )
    return data_dir, measure_path, cql_path


def test_dqm_cli_run_config(tmp_path):
    data_dir, measure_path, cql_path = _write_simple_measure(tmp_path)
    output_dir = tmp_path / "out"
    config_path = tmp_path / "dqm.json"
    config_path.write_text(
        json.dumps(
            {
                "measures": [{"path": str(measure_path), "cql": str(cql_path)}],
                "source": {"type": "directory", "path": str(data_dir)},
                "period": {"start": "2026-01-01", "end": "2026-12-31"},
                "outputs": {
                    "directory": str(output_dir),
                    "formats": ["json"],
                    "measure_reports": "summary",
                    "definitions": {"mode": "all", "formats": ["json"]},
                },
            }
        )
    )

    exit_code = main(["dqm", "run", "--config", str(config_path)])

    assert exit_code == 0
    run_report = json.loads((output_dir / "run.json").read_text())
    assert run_report["failed"] == 0
    assert run_report["measures"][0]["result_rows"] == 2
    assert (output_dir / "TestMeasure" / "results.json").exists()
    assert (output_dir / "TestMeasure" / "MeasureReport-summary.json").exists()
    report = json.loads((output_dir / "TestMeasure" / "MeasureReport-summary.json").read_text())
    assert report["group"][0]["id"] == "primary"
    definitions = json.loads((output_dir / "TestMeasure" / "definitions.json").read_text())
    assert {row["patient_id"] for row in definitions} == {"p1", "p2"}
    assert "helper_define" in definitions[0]
    schema = json.loads((output_dir / "TestMeasure" / "definitions.schema.json").read_text())
    assert {
        item["definition"] for item in schema["definitions"]
    } == {"Initial Population", "Denominator", "Numerator", "Helper Define"}


def test_dqm_cli_validate_reports_errors(tmp_path, capsys):
    config = DQMRunConfig(
        measures=[],
        source=SourceSpec(type="directory", path=str(tmp_path / "missing")),
        outputs=OutputSpec(directory=tmp_path / "out", measure_reports="none"),
    )

    errors = validate_config(config)

    assert errors == [
        "At least one measure is required",
        f"Source path not found: {tmp_path / 'missing'}",
    ]


def test_dqm_cli_individual_report_supporting_evidence(tmp_path):
    data_dir, measure_path, cql_path = _write_simple_measure(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "dqm",
            "run",
            "--measure",
            str(measure_path),
            "--cql",
            str(cql_path),
            "--source",
            str(data_dir),
            "--period",
            "2026-01-01:2026-12-31",
            "--output",
            str(output_dir),
            "--measure-reports",
            "individual",
        ]
    )

    assert exit_code == 0
    report = json.loads(
        (output_dir / "TestMeasure" / "individual-reports" / "p1.json").read_text()
    )
    denominator = next(
        population
        for population in report["group"][0]["population"]
        if population["code"]["coding"][0]["code"] == "denominator"
    )
    support = next(
        ext
        for ext in denominator["extension"]
        if ext["url"] == "http://hl7.org/fhir/StructureDefinition/cqf-supportingEvidence"
    )
    assert {"url": "name", "valueCode": "HelperDefine"} in support["extension"]
    assert {"url": "value", "valueBoolean": True} in support["extension"]


def test_dqm_cli_individual_report_reuses_primary_supporting_evidence(tmp_path):
    data_dir, measure_path, cql_path = _write_simple_measure(tmp_path)
    output_dir = tmp_path / "out"
    config_path = tmp_path / "dqm.json"
    config_path.write_text(
        json.dumps(
            {
                "measures": [{"path": str(measure_path), "cql": str(cql_path)}],
                "source": {"type": "directory", "path": str(data_dir)},
                "period": {"start": "2026-01-01", "end": "2026-12-31"},
                "audit": {"mode": "population"},
                "outputs": {
                    "directory": str(output_dir),
                    "formats": ["json"],
                    "measure_reports": "individual",
                },
            }
        )
    )

    exit_code = main(["dqm", "run", "--config", str(config_path)])

    assert exit_code == 0
    results = json.loads((output_dir / "TestMeasure" / "results.json").read_text())
    assert "evidence_HelperDefine" in results[0]
    report = json.loads(
        (output_dir / "TestMeasure" / "individual-reports" / "p1.json").read_text()
    )
    support_json = json.dumps(report["group"][0]["population"])
    assert '"valueBoolean": true' in support_json
    assert "trace" not in support_json


def test_dqm_inspect_reports_measure_metadata(tmp_path):
    data_dir, measure_path, cql_path = _write_simple_measure(tmp_path)
    config = DQMRunConfig(
        measures=[MeasureSpec(path=measure_path, cql=cql_path)],
        source=SourceSpec(type="directory", path=str(data_dir)),
        outputs=OutputSpec(directory=tmp_path / "out", measure_reports="none"),
        audit=AuditSpec(mode=AuditMode.POPULATION),
    )

    payload = inspect_config(config)

    assert payload["measures"][0]["id"] == "TestMeasure"
    assert payload["measures"][0]["populations"] == 3
    assert payload["audit"]["mode"] == "population"


def test_dqm_hapi_explain_scope_prints_plan(monkeypatch, capsys):
    config = SimpleNamespace(name="hapi-config")
    calls = {}

    def fake_load_materialization_config(path):
        calls["config_path"] = path
        return config

    def fake_explain_patient_scope_plan(loaded_config, patient_ids, *, analyze=False):
        calls["config"] = loaded_config
        calls["patient_ids"] = patient_ids
        calls["analyze"] = analyze
        return ["Bitmap Heap Scan on fhir4ds_hapi_current_resources", "  Recheck Cond"]

    monkeypatch.setattr(
        dqm_cli,
        "load_materialization_config",
        fake_load_materialization_config,
    )
    monkeypatch.setattr(
        dqm_cli,
        "explain_patient_scope_plan",
        fake_explain_patient_scope_plan,
    )

    exit_code = main(
        [
            "dqm",
            "hapi",
            "explain-scope",
            "--config",
            "hapi.yaml",
            "--patient-id",
            "p2",
            "--patient-id",
            "p1",
            "--analyze",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls == {
        "config_path": "hapi.yaml",
        "config": config,
        "patient_ids": ["p2", "p1"],
        "analyze": True,
    }
    assert "Bitmap Heap Scan on fhir4ds_hapi_current_resources" in output
