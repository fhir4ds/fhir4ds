"""CLI tests for `fhir4ds verify` (adapter contract: exit codes, stdout)."""

from __future__ import annotations

import json

from fhir4ds.cli.main import main
from fhir4ds.operations.tests.fixtures import (
    MATRIX_OUTPUT_COLUMNS,
    write_matrix_fixture,
)


def _run(tmp_path, argv):
    return main(["verify", *argv])


def test_missing_library_exit_2(tmp_path, capsys):
    assert _run(tmp_path, ["--library", str(tmp_path / "nope.cql")]) == 2
    assert "not found" in capsys.readouterr().err


def test_bad_parameters_json_exit_2(tmp_path, capsys):
    fixture = write_matrix_fixture(tmp_path / "fx")
    assert _run(tmp_path, [
        "--library", fixture["library"],
        "--parameters", "{not json",
    ]) == 2


def test_verify_pass_exit_0(tmp_path, capsys):
    fixture = write_matrix_fixture(tmp_path / "fx")
    cases = {
        "schema": 1,
        "cases": [
            {"patient": "pt-1", "population": "IPP", "expect": True},
            {"patient": "pt-2", "population": "IPP", "expect": False},
        ],
    }
    cases_file = tmp_path / "pass_cases.json"
    cases_file.write_text(json.dumps(cases))
    rc = _run(tmp_path, [
        "--library", fixture["library"],
        "--data", fixture["ndjson"],
        "--tests", str(cases_file),
        "--output-columns", json.dumps(MATRIX_OUTPUT_COLUMNS),
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["passed"] is True


def test_verify_failing_case_exit_1(tmp_path, capsys):
    fixture = write_matrix_fixture(tmp_path / "fx")
    rc = _run(tmp_path, [
        "--library", fixture["library"],
        "--data", fixture["ndjson"],
        "--tests", fixture["cases"],
        "--output-columns", json.dumps(MATRIX_OUTPUT_COLUMNS),
    ])
    assert rc == 1  # unknown-patient case fails; run itself succeeded
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True and payload["passed"] is False
    assert payload["tests"]["failures"][0]["patient"] == "pt-9"


def test_evaluate_without_cases_exit_0(tmp_path, capsys):
    fixture = write_matrix_fixture(tmp_path / "fx")
    rc = _run(tmp_path, [
        "--library", fixture["library"],
        "--data", fixture["ndjson"],
        "--output-columns", json.dumps(MATRIX_OUTPUT_COLUMNS),
    ])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"IPP": 2, "NAME": 2}


def test_broken_cql_exit_1_with_parse_diagnostic(tmp_path, capsys):
    lib = tmp_path / "Broken.cql"
    lib.write_text("library Broken\ndefine :")
    rc = _run(tmp_path, ["--library", str(lib), "--data", _tiny_ndjson(tmp_path)])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["diagnostics"][0]["code"] == "parse_error"


def test_text_format_human_readable(tmp_path, capsys):
    fixture = write_matrix_fixture(tmp_path / "fx")
    rc = _run(tmp_path, [
        "--library", fixture["library"],
        "--data", fixture["ndjson"],
        "--output-columns", json.dumps(MATRIX_OUTPUT_COLUMNS),
        "--format", "text",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "[OK]" in out and "IPP: 2" in out


def _tiny_ndjson(tmp_path):
    p = tmp_path / "tiny.ndjson"
    p.write_text('{"resourceType": "Patient", "id": "pt-1"}\n')
    return str(p)
