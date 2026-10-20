"""S22d-1 (AM5–AM8): FHIR-type workspace — migration + discovery tests."""

from __future__ import annotations

import json
from pathlib import Path

from fhir4ds.devserver.config import load_config
from fhir4ds.devserver.discovery import scan_workspace
from fhir4ds.devserver.workspace_types import (
    FHIR_TYPE_FOLDERS,
    list_patient_ids,
    migrate_workspace,
)
from fhir4ds.devserver.workspace_types import test_cases_list as make_test_cases


def _legacy_workspace(root: Path) -> None:
    (root / "cql").mkdir()
    (root / "cql" / "Demo.cql").write_text(
        "library Demo version '1.0.0'\nusing FHIR version '4.0.1'\ncontext Patient\n\ndefine Ok: 1 = 1\n"
    )
    (root / "valuesets").mkdir()
    (root / "valuesets" / "vs1.json").write_text(
        json.dumps({"resourceType": "ValueSet", "id": "myvs", "url": "http://x/vs1"})
    )
    (root / "data").mkdir()
    resources = [
        {"resourceType": "Patient", "id": "w01", "gender": "female", "birthDate": "1970-01-01"},
        {"resourceType": "Encounter", "id": "e1", "status": "finished",
         "subject": {"reference": "Patient/w01"}},
        {"resourceType": "Organization", "id": "org1", "name": "Acme"},
        {"resourceType": "Patient", "id": "w02", "gender": "male"},
    ]
    (root / "data" / "patients.ndjson").write_text(
        "\n".join(json.dumps(r) for r in resources)
    )


class TestMigration:
    def test_legacy_markers_detected(self, tmp_path):
        assert migrate_workspace(tmp_path)["migrated"] is False

    def test_migration_layout(self, tmp_path):
        _legacy_workspace(tmp_path)
        report = migrate_workspace(tmp_path)
        assert report["migrated"] is True
        assert report["patients"] == 2
        assert (tmp_path / "Library" / "Demo.cql").is_file()
        assert (tmp_path / "ValueSet" / "myvs.json").is_file()
        # Single patient store: one folder per patient.
        assert (tmp_path / "Patient" / "w01" / "w01.json").is_file()
        assert (tmp_path / "Patient" / "w02" / "w02.json").is_file()
        # Attributed clinical resource: BY TYPE inside the patient folder.
        assert (tmp_path / "Patient" / "w01" / "Encounter" / "e1.json").is_file()
        # Unattributed: root type folder.
        assert (tmp_path / "Organization" / "org1.json").is_file()
        # Originals archived.
        assert (tmp_path / "_attic" / "migration-legacy" / "data" / "patients.ndjson").is_file()
        assert not (tmp_path / "data").exists()
        # Idempotent.
        assert migrate_workspace(tmp_path)["migrated"] is False

    def test_dry_run_touches_nothing(self, tmp_path):
        _legacy_workspace(tmp_path)
        report = migrate_workspace(tmp_path, dry_run=True)
        assert report["migrated"] is True
        assert (tmp_path / "data" / "patients.ndjson").is_file()
        assert not (tmp_path / "Patient").exists()

    def test_bundle_data_splits(self, tmp_path):
        (tmp_path / "cql").mkdir()
        bundle = {
            "resourceType": "Bundle",
            "type": "collection",
            "entry": [
                {"resource": {"resourceType": "Patient", "id": "b1"}},
                {"resource": {"resourceType": "Observation", "id": "o1",
                              "subject": {"reference": "Patient/b1"}}},
            ],
        }
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "bundle.json").write_text(json.dumps(bundle))
        migrate_workspace(tmp_path)
        assert (tmp_path / "Patient" / "b1" / "b1.json").is_file()
        assert (tmp_path / "Patient" / "b1" / "Observation" / "o1.json").is_file()


class TestTypeDiscovery:
    def test_type_layout_discovery(self, tmp_path):
        _legacy_workspace(tmp_path)
        migrate_workspace(tmp_path)
        cfg = load_config(tmp_path)
        snap = scan_workspace(cfg)
        assert [lib.name for lib in snap.libraries] == ["Demo"]
        dataset_names = {Path(d).name for d in snap.datasets}
        assert {"w01.json", "w02.json", "e1.json", "org1.json"} <= dataset_names
        assert {Path(d).name for d in snap.valuesets} == {"myvs.json"}

    def test_measure_dir_inner_types_excluded_from_measures(self, tmp_path):
        (tmp_path / "cql").mkdir()
        mdir = tmp_path / "Measure" / "DemoM" / "Measure"
        mdir.mkdir(parents=True)
        (mdir / "DemoM.json").write_text(
            json.dumps({"resourceType": "Measure", "id": "DemoM"})
        )
        inner = tmp_path / "Measure" / "DemoM"
        (inner / "List").mkdir()
        (inner / "List" / "TestCases.json").write_text(
            json.dumps(make_test_cases(["p1"]))
        )
        (inner / "MeasureReport").mkdir()
        (inner / "MeasureReport" / "p1.json").write_text(
            json.dumps({"resourceType": "MeasureReport", "id": "mr1"})
        )
        cfg = load_config(tmp_path)
        snap = scan_workspace(cfg)
        assert [Path(m).name for m in snap.measures] == ["DemoM.json"]

    def test_reserved_names_are_fhir_types(self):
        for name in ("Patient", "Library", "ValueSet", "Measure", "List", "Parameters"):
            assert name in FHIR_TYPE_FOLDERS


class TestCaseListResource:
    def test_roundtrip(self):
        lst = make_test_cases(["w02", "w01"])
        assert lst["resourceType"] == "List"
        assert lst["mode"] == "working"
        assert list_patient_ids(lst) == ["w01", "w02"]

    def test_non_list_input(self):
        assert list_patient_ids(None) == []
        assert list_patient_ids({"resourceType": "Patient"}) == []
