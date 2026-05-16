import json
import os
import shutil
import tempfile
from pathlib import Path

import duckdb
import pytest


def _repo_root() -> Path:
    path = Path(__file__).resolve()
    for parent in path.parents:
        if (parent / "extensions").exists() and (parent / "fhir4ds").exists():
            return parent
    raise RuntimeError("Could not locate repository root")


@pytest.fixture
def cpp_con():
    ext = (
        _repo_root()
        / "extensions"
        / "cql"
        / "build"
        / "release"
        / "extension"
        / "cql"
        / "cql.duckdb_extension"
    )
    if not ext.exists():
        pytest.skip(f"CQL extension is not built: {ext}")

    with tempfile.TemporaryDirectory() as tmpdir:
        load_path = Path(tmpdir) / "cql.duckdb_extension"
        shutil.copy2(ext, load_path)
        con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": "true"})
        con.execute(f"LOAD '{load_path}'")
        try:
            yield con
        finally:
            con.close()


def _load_cache(con, valueset_url: str, system: str, code: str) -> None:
    assert con.execute("SELECT cql_valueset_cache_clear()").fetchone()[0] is True
    assert con.execute(
        "SELECT cql_valueset_cache_add(?, ?, ?)",
        [valueset_url, system, code],
    ).fetchone()[0] is True


def test_extension_where_codeable_concept_path(cpp_con):
    valueset_url = "http://example.org/fhir/ValueSet/refusal"
    _load_cache(cpp_con, valueset_url, "http://snomed.info/sct", "1296859006")
    resource = json.dumps({
        "resourceType": "ServiceRequest",
        "extension": [{
            "url": "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-doNotPerformReason",
            "valueCodeableConcept": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "1296859006",
                }],
            },
        }],
    })

    path = (
        "extension.where(url='http://hl7.org/fhir/us/qicore/StructureDefinition/"
        "qicore-doNotPerformReason').valueCodeableConcept"
    )

    assert cpp_con.execute(
        "SELECT in_valueset(?, ?, ?)",
        [resource, path, valueset_url],
    ).fetchone()[0] is True


def test_extension_value_does_not_apply_choice_fallback_after_array_step(cpp_con):
    valueset_url = "http://example.org/fhir/ValueSet/refusal"
    _load_cache(cpp_con, valueset_url, "http://snomed.info/sct", "1296859006")
    resource = json.dumps({
        "resourceType": "ServiceRequest",
        "extension": [{
            "url": "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-doNotPerformReason",
            "valueCodeableConcept": {
                "coding": [{
                    "system": "http://snomed.info/sct",
                    "code": "1296859006",
                }],
            },
        }],
    })

    assert cpp_con.execute(
        "SELECT in_valueset(?, 'extension.value', ?)",
        [resource, valueset_url],
    ).fetchone()[0] is False


def test_json_encoded_synthetic_terminology_field(cpp_con):
    valueset_url = "http://example.org/fhir/ValueSet/medical-reason"
    _load_cache(cpp_con, valueset_url, "http://snomed.info/sct", "183932001")
    resource = json.dumps({
        "id": "synthetic",
        "medicationStatusReason": json.dumps({
            "coding": [{
                "system": "http://snomed.info/sct",
                "code": "183932001",
            }],
        }),
    })

    assert cpp_con.execute(
        "SELECT in_valueset(?, 'medicationStatusReason', ?)",
        [resource, valueset_url],
    ).fetchone()[0] is True


def test_valueset_profile_is_opt_in(cpp_con):
    valueset_url = "http://example.org/fhir/ValueSet/profiled"
    _load_cache(cpp_con, valueset_url, "http://loinc.org", "1234")
    resource = json.dumps({
        "code": {
            "coding": [{
                "system": "http://loinc.org",
                "code": "1234",
            }],
        },
    })

    previous = os.environ.get("FHIR4DS_PROFILE_CPP_VALUESET")
    os.environ.pop("FHIR4DS_PROFILE_CPP_VALUESET", None)
    try:
        assert cpp_con.execute("SELECT cql_valueset_profile_clear()").fetchone()[0] is True
        assert cpp_con.execute(
            "SELECT in_valueset(?, 'code', ?)",
            [resource, valueset_url],
        ).fetchone()[0] is True
        assert json.loads(cpp_con.execute("SELECT cql_valueset_profile_json()").fetchone()[0]) == []

        os.environ["FHIR4DS_PROFILE_CPP_VALUESET"] = "1"
        assert cpp_con.execute(
            "SELECT in_valueset(?, 'code', ?)",
            [resource, valueset_url],
        ).fetchone()[0] is True
        profile = json.loads(cpp_con.execute("SELECT cql_valueset_profile_json()").fetchone()[0])
        assert profile[0]["path"] == "code"
        assert profile[0]["valueset_url"] == valueset_url
        assert profile[0]["calls"] == 1
        assert profile[0]["code_matches"] == 1
    finally:
        if previous is None:
            os.environ.pop("FHIR4DS_PROFILE_CPP_VALUESET", None)
        else:
            os.environ["FHIR4DS_PROFILE_CPP_VALUESET"] = previous
