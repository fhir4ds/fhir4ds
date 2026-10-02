"""CLI tests for the WASM-aligned commands (cql translate/evaluate,
fhirpath, validate-resource). Adapter contract: exit codes, stdout JSON."""

from __future__ import annotations

import json

from fhir4ds.cli.main import main

_PATIENT = {
    "resourceType": "Patient",
    "id": "p1",
    "gender": "male",
    "name": [{"family": "Chalmers", "given": ["John", "Kim"]}],
}

_CQL = """library AlignTest version '1.0.0'
using FHIR version '4.0.1'
context Patient
define "Is Male": Patient.gender = 'male'
"""


def _write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_fhirpath_exit_0(tmp_path, capsys):
    res = _write(tmp_path, "p.json", json.dumps(_PATIENT))
    assert main(["fhirpath", "name.given.first()", "--resource", res]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["results"] == ["John"]


def test_fhirpath_missing_resource_exit_2(tmp_path, capsys):
    assert main(
        ["fhirpath", "id", "--resource", str(tmp_path / "nope.json")]
    ) == 2
    assert "ERROR" in capsys.readouterr().err


def test_fhirpath_non_object_resource_exit_2(tmp_path, capsys):
    res = _write(tmp_path, "arr.json", "[1, 2]")
    assert main(["fhirpath", "id", "--resource", res]) == 2


def test_validate_resource_exit_0(tmp_path, capsys):
    res = _write(tmp_path, "p.json", json.dumps(_PATIENT))
    assert main(["validate-resource", res]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["passed"] is True
    assert out["source"] == res


def test_validate_resource_bad_json_exit_2(tmp_path, capsys):
    res = _write(tmp_path, "bad.json", "{not json")
    assert main(["validate-resource", res]) == 2


def test_cql_translate_exit_0(tmp_path, capsys):
    lib = _write(tmp_path, "lib.cql", _CQL)
    assert main(["cql", "translate", lib]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert "Is Male" in out["sql"]
    assert out["column_types"]["Is Male"] == "Boolean"


def test_cql_translate_missing_library_exit_2(tmp_path, capsys):
    assert main(["cql", "translate", str(tmp_path / "nope.cql")]) == 2


def test_cql_translate_sql_out(tmp_path, capsys):
    lib = _write(tmp_path, "lib.cql", _CQL)
    dest = tmp_path / "out.sql"
    assert main(["cql", "translate", lib, "--sql-out", str(dest)]) == 0
    assert "Is Male" in dest.read_text(encoding="utf-8")
    out = json.loads(capsys.readouterr().out)
    assert out["sql_path"] == str(dest)


def test_cql_evaluate_exit_0(tmp_path, capsys):
    lib = _write(tmp_path, "lib.cql", _CQL)
    data = _write(
        tmp_path,
        "data.ndjson",
        '{"resourceType":"Patient","id":"p1","gender":"male"}\n'
        '{"resourceType":"Patient","id":"p2","gender":"female"}\n',
    )
    assert main(["cql", "evaluate", lib, "--data", data]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    assert out["patient_count"] == 2
    rows = {row["patient_id"]: row["Is Male"] for row in out["rows"]}
    assert rows == {"p1": True, "p2": False}


def test_cql_requires_subcommand(capsys):
    assert main(["cql"]) == 2
