"""Shared fixture for the capability-matrix test (FDD §3.8).

One small library (include FHIRHelpers NOT supplied inline — exercises
the §3.3.1 bundled tier), one 3-patient dataset, one cases file with an
unknown-patient case. CLI and MCP legs must produce identical
normalized envelopes from this fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MATRIX_LIBRARY = """library MatrixSimple version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.4.000' called FHIRHelpers

define "Initial Population":
  exists([Patient] P where P.gender = 'female')

define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
"""

MATRIX_OUTPUT_COLUMNS = {"IPP": "Initial Population", "NAME": "Has Name"}

MATRIX_RESOURCES = [
    {"resourceType": "Patient", "id": "pt-1", "gender": "female",
     "name": [{"given": ["Alice"]}]},
    {"resourceType": "Patient", "id": "pt-2", "gender": "male",
     "name": [{"given": ["Bob"]}]},
    {"resourceType": "Patient", "id": "pt-3", "gender": "female"},
]

MATRIX_CASES = {
    "schema": 1,
    "cases": [
        {"patient": "pt-1", "population": "IPP", "expect": True},
        {"patient": "pt-2", "population": "IPP", "expect": False},
        {"patient": "pt-3", "population": "NAME", "expect": False},
        {"patient": "pt-9", "population": "IPP", "expect": True},
    ],
}

MATRIX_LIBRARY_NAME = "MatrixSimple"


def write_matrix_fixture(tmp_dir: Path) -> dict[str, str]:
    """Materialize the fixture to files (CLI leg); returns paths."""
    tmp_dir.mkdir(parents=True, exist_ok=True)
    lib = tmp_dir / "MatrixSimple.cql"
    lib.write_text(MATRIX_LIBRARY, encoding="utf-8")
    ndjson = tmp_dir / "patients.ndjson"
    ndjson.write_text(
        "\n".join(json.dumps(r) for r in MATRIX_RESOURCES) + "\n", encoding="utf-8"
    )
    cases = tmp_dir / "cases.json"
    cases.write_text(json.dumps(MATRIX_CASES, indent=1), encoding="utf-8")
    return {"library": str(lib), "ndjson": str(ndjson), "cases": str(cases)}


def normalized_verify_envelope(envelope_dict: dict[str, Any]) -> dict[str, Any]:
    """Normalization rules shared by both matrix legs (drop volatile fields)."""
    out = json.loads(json.dumps(envelope_dict, default=str))
    out.pop("timing_ms", None)
    # CLI-only input echo; not part of the capability contract.
    out.pop("timeout_seconds", None)
    # Library reference differs by transport (file path vs inline name).
    if "library" in out:
        out["library"] = str(out["library"]).rsplit("/", 1)[-1].removesuffix(".cql")
    tests = out.get("tests", {})
    failures = tests.get("failures", [])
    tests["failures"] = sorted(failures, key=lambda f: (f.get("patient", ""), f.get("target", "")))
    out["tests"] = tests
    out.pop("patients_evaluated_note", None)
    return out
