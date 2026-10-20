"""S22e (§3): normalize-on-ingest — ndjson is TRANSPORT only.

Any ``.ndjson`` file that appears under ``data/`` (runtime ingest, not
first-boot — that is the S22d-1 migration) is parsed once, split into
canonical per-patient folders (``Patient/<id>/`` + type subfolders via
the typed patient-ref doctrine), the monolith is archived to
``_attic/``, and a changed event fires. Unattributed resources land in
their root type folder. The browser never converts formats.
"""

from __future__ import annotations

import json
from pathlib import Path

from fhir4ds.devserver.workspace_types import normalize_ndjson_ingest


def _write_ndjson(path: Path, resources: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in resources) + "\n")


class TestNormalizeIngest:
    def test_monolith_normalized_and_archived(self, tmp_path):
        data = tmp_path / "data"
        _write_ndjson(
            data / "patients.ndjson",
            [
                {"resourceType": "Patient", "id": "n1", "gender": "female"},
                {
                    "resourceType": "Observation",
                    "id": "ob1",
                    "subject": {"reference": "Patient/n1"},
                },
                {"resourceType": "Organization", "id": "o1", "name": "Org"},
            ],
        )
        report = normalize_ndjson_ingest(tmp_path)
        assert report["normalized"] == 1
        # Canonical shape.
        assert (tmp_path / "Patient" / "n1" / "n1.json").is_file()
        assert (tmp_path / "Patient" / "n1" / "Observation" / "ob1.json").is_file()
        assert (tmp_path / "Organization" / "o1.json").is_file()
        # The monolith is GONE from data/ and archived.
        assert not (data / "patients.ndjson").exists()
        assert any(
            "patients.ndjson" in str(p) for p in (tmp_path / "_attic").rglob("*")
        )

    def test_no_ndjson_noop(self, tmp_path):
        report = normalize_ndjson_ingest(tmp_path)
        assert report["normalized"] == 0

    def test_malformed_lines_skipped(self, tmp_path):
        data = tmp_path / "data"
        data.mkdir(parents=True)
        (data / "mixed.ndjson").write_text(
            json.dumps({"resourceType": "Patient", "id": "m1"})
            + "\nnot-json\n\n"
            + json.dumps({"resourceType": "Patient", "id": "m2"})
            + "\n"
        )
        report = normalize_ndjson_ingest(tmp_path)
        assert report["normalized"] == 1
        assert (tmp_path / "Patient" / "m1" / "m1.json").is_file()
        assert (tmp_path / "Patient" / "m2" / "m2.json").is_file()

    def test_existing_patient_appended_not_overwritten(self, tmp_path):
        (tmp_path / "Patient" / "n1").mkdir(parents=True)
        (tmp_path / "Patient" / "n1" / "n1.json").write_text(
            json.dumps({"resourceType": "Patient", "id": "n1", "gender": "male"})
        )
        _write_ndjson(
            tmp_path / "data" / "new.ndjson",
            [
                {"resourceType": "Patient", "id": "n1", "gender": "female"},
                {
                    "resourceType": "Encounter",
                    "id": "en9",
                    "subject": {"reference": "Patient/n1"},
                },
            ],
        )
        report = normalize_ndjson_ingest(tmp_path)
        # Existing patient resource KEPT (last-write-wins only for files
        # the ingest owns); the new clinical resource lands in the folder.
        kept = json.loads((tmp_path / "Patient" / "n1" / "n1.json").read_text())
        assert kept["gender"] == "male"
        assert (tmp_path / "Patient" / "n1" / "Encounter" / "en9.json").is_file()
        assert report["normalized"] == 1
