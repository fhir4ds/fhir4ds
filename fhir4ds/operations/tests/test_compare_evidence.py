"""C2-U1: compare_evidence capability tests (delta semantics, strict
input coercion, error taxonomy) + CLI --evidence/--baseline + MCP tool.
"""

from __future__ import annotations

import json

import pytest

from fhir4ds.operations import (
    CompareEvidenceResult,
    compare_evidence,
    evidence_payload_from_dict,
)


def _single(pid: str, pops: dict) -> dict:
    return {
        "schema": 1,
        "ok": True,
        "patient_id": pid,
        "populations": pops,
        "definitions": [],
    }


def _multi(entries: dict[str, dict]) -> dict:
    return {"schema": 1, "ok": True, "patients": entries}


class TestDeltaSemantics:
    def test_no_diff_is_changed_false(self):
        r = compare_evidence(_single("p1", {"IPP": True}), _single("p1", {"IPP": True}))
        d = r.to_dict()
        assert d["ok"] and d["changed"] is False and d["passed"] is True
        assert d["summary"] == {"moved": 0, "added": 0, "removed": 0, "flipped": 0}
        assert d["patients"] == []

    def test_moved(self):
        r = compare_evidence(
            _single("p1", {"IPP": True, "NUMER": False}),
            _single("p1", {"IPP": True, "NUMER": True}),
        )
        d = r.to_dict()
        assert d["changed"] and d["summary"]["moved"] == 1
        entry = d["patients"][0]
        assert entry["classification"] == "moved"
        assert entry["from"] is False and entry["to"] is True
        assert entry["column"] == "NUMER"

    def test_flipped_null_bool(self):
        r = compare_evidence(
            _single("p1", {"IPP": None}), _single("p1", {"IPP": True})
        )
        d = r.to_dict()
        assert d["summary"]["flipped"] == 1 and d["summary"]["moved"] == 0
        assert d["patients"][0]["from"] is None and d["patients"][0]["to"] is True

    def test_patient_added_and_removed(self):
        base = _multi({"p1": {"populations": {"IPP": True}}})
        curr = _multi({"p2": {"populations": {"IPP": True}}})
        r = compare_evidence(base, curr)
        d = r.to_dict()
        assert d["summary"]["added"] == 1 and d["summary"]["removed"] == 1
        kinds = {(p["patient_id"], p["classification"]) for p in d["patients"]}
        assert kinds == {("p1", "removed"), ("p2", "added")}

    def test_column_added_within_patient(self):
        base = _multi({"p1": {"populations": {"IPP": True}}})
        curr = _multi({"p1": {"populations": {"IPP": True, "NUMER": True}}})
        d = compare_evidence(base, curr).to_dict()
        assert d["summary"]["added"] == 1
        assert d["patients"][0]["column"] == "NUMER"

    def test_deterministic_ordering(self):
        base = _multi({"b": {"populations": {"Z": True, "A": True}}})
        curr = _multi({"a": {"populations": {"Z": True, "A": True}}})
        d = compare_evidence(base, curr).to_dict()
        keys = [(p["patient_id"], p["column"]) for p in d["patients"]]
        assert keys == sorted(keys)

    def test_output_columns_aliasing(self):
        r = compare_evidence(
            _single("p1", {"Initial Population": False}),
            _single("p1", {"Initial Population": True}),
            output_columns={"Initial Population": "IPP"},
        )
        assert r.patients[0]["column"] == "IPP"

    def test_rationale_strings(self):
        r = compare_evidence(_single("p1", {"IPP": True}), _single("p1", {"IPP": False}))
        assert "IPP" in r.patients[0]["rationale"]


class TestStrictInputCoercion:
    def test_single_envelope_accepted(self):
        view = evidence_payload_from_dict(
            _single("p1", {"IPP": True}), label="x"
        )
        assert view == {"p1": {"IPP": True}}

    def test_collection_envelope_accepted(self):
        view = evidence_payload_from_dict(
            _multi({"p1": {"populations": {"IPP": True}}}), label="x"
        )
        assert view == {"p1": {"IPP": True}}

    def test_bare_map_accepted(self):
        view = evidence_payload_from_dict(
            {"p1": {"populations": {"IPP": True}}}, label="x"
        )
        assert view == {"p1": {"IPP": True}}

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError):
            evidence_payload_from_dict([1, 2], label="x")

    def test_unknown_shape_rejected_with_keys(self):
        with pytest.raises(ValueError) as ei:
            evidence_payload_from_dict({"nope": 1}, label="baseline")
        assert "baseline" in str(ei.value) and "nope" in str(ei.value)

    def test_bad_population_value_rejected(self):
        with pytest.raises(ValueError):
            evidence_payload_from_dict(
                {"patient_id": "p1", "populations": {"IPP": "yes"}}, label="x"
            )

    def test_missing_patient_id_rejected(self):
        with pytest.raises(ValueError):
            evidence_payload_from_dict({"populations": {"IPP": True}}, label="x")

    def test_capability_wraps_input_error(self):
        r = compare_evidence({"garbage": True}, _single("p1", {}))
        assert r.ok is False
        assert r.diagnostics[0].code.value == "input_error"


class TestCliBaseline:
    def _run_verify(self, tmp_path, extra_args, dataset_rows=None):
        """Drive verify.run via argparse namespace (in-process, no shell)."""
        import argparse

        from fhir4ds.cli import verify as verify_mod

        lib = tmp_path / "Lib.cql"
        lib.write_text(
            "library Lib version '1.0.0'\n"
            "using FHIR version '4.0.1'\n"
            "include FHIRHelpers version '4.0.1' called FHIRHelpers\n"
            "define \"Initial Population\":\n"
            "  exists([Patient] P where P.gender = 'female')\n",
            encoding="utf-8",
        )
        data = tmp_path / "patients.ndjson"
        rows = dataset_rows or [
            {"resourceType": "Patient", "id": "p1", "gender": "female"},
            {"resourceType": "Patient", "id": "p2", "gender": "male"},
        ]
        data.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8"
        )
        parser = argparse.ArgumentParser("verify")
        verify_mod.configure_parser(parser)
        args = parser.parse_args(
            ["--library", str(lib), "--data", str(data), *extra_args]
        )
        return verify_mod.run(args)

    def test_evidence_artifact_then_baseline_diff(self, tmp_path, capsys):
        ev_path = tmp_path / "evidence.json"
        rc = self._run_verify(tmp_path, ["--evidence", str(ev_path)])
        capsys.readouterr()  # drain run-1 envelope output
        assert rc == 0
        artifact = json.loads(ev_path.read_text(encoding="utf-8"))
        assert artifact["schema"] == 1 and "patients" in artifact
        assert artifact["patients"]["p1"]["populations"]["Initial Population"] is True

        # Change the dataset so the delta is non-empty.
        rc2 = self._run_verify(
            tmp_path,
            ["--baseline", str(ev_path)],
            dataset_rows=[
                {"resourceType": "Patient", "id": "p1", "gender": "male"},
                {"resourceType": "Patient", "id": "p2", "gender": "male"},
            ],
        )
        out = capsys.readouterr().out
        assert rc2 == 0
        delta = json.loads(out)
        assert delta["ok"] and delta["changed"] is True
        assert any(
            p["classification"] == "moved" and p["patient_id"] == "p1"
            for p in delta["patients"]
        )

    def test_baseline_missing_file_exit_2(self, tmp_path, capsys):
        rc = self._run_verify(tmp_path, ["--baseline", str(tmp_path / "nope.json")])
        assert rc == 2


class TestMcpCompareTool:
    def test_tool_registered_and_correct(self):
        pytest.importorskip("mcp")
        from fhir4ds.mcp.server import build_server

        server = build_server()
        names = [t.name for t in server._tool_manager.list_tools()]
        assert "compare_evidence_tool" in names
