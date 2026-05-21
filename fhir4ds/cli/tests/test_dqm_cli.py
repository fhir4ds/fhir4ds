"""Tests for the DQM CLI."""

from __future__ import annotations

import json
from pathlib import Path

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
                        "population": [
                            {
                                "code": {"coding": [{"code": "initial-population"}]},
                                "criteria": {"expression": "Initial Population"},
                            },
                            {
                                "code": {"coding": [{"code": "denominator"}]},
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
