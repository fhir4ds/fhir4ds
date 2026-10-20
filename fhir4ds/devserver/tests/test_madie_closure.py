"""S22d-2 (§5): List-closure MADiE export/import + collision policy."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from fhir4ds.devserver import madie_import
from fhir4ds.devserver.madie_export_closure import export_measure_closure_zip


def _make_type_workspace(root: Path) -> None:
    (root / "Library").mkdir(parents=True)
    (root / "Library" / "Core.cql").write_text(
        "library Core version '1.0.0'\ncontext Patient\n\ndefine A: 1\n"
    )
    (root / "Library" / "Main.cql").write_text(
        "library Main version '1.0.0'\n"
        "include Core version '1.0.0' called Core\n"
        'valueset "VS": \'http://x/vs1\'\n'
        "context Patient\n\n"
        'define "IP": exists([Observation: \"VS\"])\n'
    )
    (root / "Library" / "Unused.cql").write_text(
        "library Unused version '1.0.0'\ncontext Patient\n\ndefine B: 2\n"
    )
    (root / "ValueSet").mkdir()
    (root / "ValueSet" / "vs1.json").write_text(
        json.dumps({"resourceType": "ValueSet", "id": "vs1", "url": "http://x/vs1"})
    )
    (root / "ValueSet" / "unref.json").write_text(
        json.dumps({"resourceType": "ValueSet", "id": "unref", "url": "http://x/unref"})
    )
    mdir = root / "Measure" / "MainM"
    (mdir / "Measure").mkdir(parents=True)
    (mdir / "Measure" / "MainM.json").write_text(
        json.dumps(
            {
                "resourceType": "Measure",
                "id": "MainM",
                "name": "MainM",
                "library": ["urn:cleanroom:lib:Main"],
                "group": [
                    {
                        "population": [
                            {
                                "code": {"coding": [{"code": "initial-population"}]},
                                "criteria": {"expression": "IP"},
                            }
                        ]
                    }
                ],
            }
        )
    )
    # Test-set membership BY REFERENCE: t1 in, t2 NOT in.
    (mdir / "List").mkdir()
    (mdir / "List" / "TestCases.json").write_text(
        json.dumps(
            {
                "resourceType": "List",
                "status": "current",
                "mode": "working",
                "entry": [{"item": {"reference": "Patient/t1"}}],
            }
        )
    )
    (mdir / "MeasureReport").mkdir()
    (mdir / "MeasureReport" / "t1.json").write_text(
        json.dumps({"resourceType": "MeasureReport", "subject": {"reference": "Patient/t1"}})
    )
    # Patients: t1 (in the List) + t2 (not).
    (root / "Patient" / "t1").mkdir(parents=True)
    (root / "Patient" / "t1" / "t1.json").write_text(
        json.dumps({"resourceType": "Patient", "id": "t1", "gender": "female"})
    )
    (root / "Patient" / "t1" / "Observation").mkdir()
    (root / "Patient" / "t1" / "Observation" / "o1.json").write_text(
        json.dumps(
            {
                "resourceType": "Observation",
                "id": "o1",
                "status": "final",
                "code": {"coding": [{"system": "http://x", "code": "1"}]},
                "subject": {"reference": "Patient/t1"},
            }
        )
    )
    (root / "Patient" / "t2").mkdir(parents=True)
    (root / "Patient" / "t2" / "t2.json").write_text(
        json.dumps({"resourceType": "Patient", "id": "t2", "gender": "male"})
    )


class _FakeWatcher:
    def __init__(self, cfg):
        self._cfg = cfg


class _FakeServer:
    def __init__(self, cfg):
        self.watcher = _FakeWatcher(cfg)


def _server_for(root: Path) -> _FakeServer:
    from types import SimpleNamespace

    return _FakeServer(SimpleNamespace(root=root))


class TestClosureExport:
    def test_closure_zip_contents(self, tmp_path):
        _make_type_workspace(tmp_path)
        blob = export_measure_closure_zip(tmp_path, "MainM")
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = set(zf.namelist())
        # Closure of Main = Main + Core; Unused is NOT in the closure.
        assert "cql/Main-1.0.0.cql" in names
        assert "cql/Core-1.0.0.cql" in names
        assert not any("Unused" in n for n in names)
        # Referenced valueset ships; the unreferenced one does not.
        assert "resources/valueset-vs1.json" in names
        assert not any("unref" in n for n in names)
        # LIST-REFERENCED patient t1 ships as one bundle (their resources
        # inside); t2 does NOT.
        assert "testcase/patient-t1/t1.json" in names
        assert "testcase/patient-t1/t1-expected.json" in names
        assert not any("patient-t2" in n for n in names)
        t1 = json.loads(zf.read("testcase/patient-t1/t1.json"))
        rts = sorted(
            e["resource"]["resourceType"] for e in t1["entry"]
        )
        assert rts == ["Observation", "Patient"]
        # The expected MeasureReport rides along (MADiE trailing-entry form).
        assert "resources/measure-MainM-1.0.0.json" in names
        assert any("expected" in n for n in names)

    def test_unknown_measure_rejected(self, tmp_path):
        _make_type_workspace(tmp_path)
        with pytest.raises(LookupError):
            export_measure_closure_zip(tmp_path, "NoSuchMeasure")


class TestImportCollisionPolicy:
    def _tests_zip(self, pid: str = "w01") -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            bundle = {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [
                    {"resource": {"resourceType": "Patient", "id": pid}},
                    {
                        "resource": {
                            "resourceType": "Observation",
                            "id": "o-9",
                            "subject": {"reference": f"Patient/{pid}"},
                        }
                    },
                    {
                        "resource": {
                            "resourceType": "MeasureReport",
                            "extension": [
                                {
                                    "url": "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-isTestCases",
                                    "valueBoolean": True,
                                }
                            ],
                            "subject": {"reference": f"Patient/{pid}"},
                        }
                    },
                ],
            }
            zf.writestr(f"{pid}/case-1.json", json.dumps(bundle))
        return buf.getvalue()

    def test_collision_rejected_by_default(self, tmp_path):
        # Existing patient w01 in the single store.
        (tmp_path / "Patient" / "w01").mkdir(parents=True)
        (tmp_path / "Patient" / "w01" / "w01.json").write_text(
            json.dumps({"resourceType": "Patient", "id": "w01"})
        )
        (tmp_path / "Library").mkdir()
        (tmp_path / "Library" / "x.cql").write_text("library X\n")
        server = _server_for(tmp_path)
        result = madie_import.import_tests_zip(
            server, self._tests_zip("w01"), measure_name="M"
        )
        assert result["ok"] is False
        assert result.get("collisions") == ["w01"]
        assert any(
            d.get("code") == "PATIENT_ID_COLLISION" for d in result["diagnostics"]
        )

    def test_namespace_optin_rewrites_ids(self, tmp_path):
        (tmp_path / "Patient" / "w01").mkdir(parents=True)
        (tmp_path / "Patient" / "w01" / "w01.json").write_text(
            json.dumps({"resourceType": "Patient", "id": "w01"})
        )
        (tmp_path / "Library").mkdir()
        (tmp_path / "Library" / "x.cql").write_text("library X\n")
        server = _server_for(tmp_path)
        result = madie_import.import_tests_zip(
            server, self._tests_zip("w01"), measure_name="M", namespace_collisions=True
        )
        assert result["ok"] is True
        case_file = next((tmp_path / "Patient" / "tc-w01").glob("*.json"))
        resource = json.loads(case_file.read_text())
        entries = [e["resource"] for e in resource["entry"]]
        patient = next(r for r in entries if r["resourceType"] == "Patient")
        assert patient["id"] == "tc-w01"
        obs = next(r for r in entries if r["resourceType"] == "Observation")
        assert obs["subject"]["reference"] == "Patient/tc-w01"
