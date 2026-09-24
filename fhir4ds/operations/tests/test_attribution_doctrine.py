"""Shared attribution-doctrine fixture tests (test-data-authoring F5).

Drives BOTH the Python loader authority AND records the shared JSON
contract consumed by the vitest mirror (web/cql-cleanroom
tests/unit/attribution.test.ts). The JSON is the single source; if a
case changes here it must change there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from fhir4ds.cql.loader.fhir_loader import FHIRDataLoader

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "attribution_doctrine_cases.json"


def _loader() -> FHIRDataLoader:
    # Attribution extraction is pure; a bare in-memory conn suffices.
    import duckdb

    return FHIRDataLoader(duckdb.connect())


def _cases() -> list[dict]:
    with open(FIXTURE, encoding="utf-8") as f:
        payload = json.load(f)
    cases = payload["cases"]
    assert cases, "fixture must carry cases"
    return cases


class TestAttributionDoctrineMirror:
    @pytest.mark.parametrize(
        "case", _cases(), ids=lambda c: c["id"]
    )
    def test_loader_authority(self, case: dict) -> None:
        loader = _loader()
        got = loader._extract_patient_ref(case["resource"])
        assert got == case["expected"], (
            f"{case['id']}: expected {case['expected']!r}, got {got!r} — {case['why']}"
        )

    def test_fixture_shape_contract(self) -> None:
        """The vitest mirror relies on this exact shape."""
        for case in _cases():
            assert set(case) == {"id", "why", "resource", "expected"}, case["id"]
            assert isinstance(case["resource"], dict)
            assert case["expected"] is None or isinstance(case["expected"], str)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
