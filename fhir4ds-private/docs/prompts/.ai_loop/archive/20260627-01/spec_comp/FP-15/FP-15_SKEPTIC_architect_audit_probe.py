#!/usr/bin/env python3
"""Architect audit probe for FP-15 type-operator remediation boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath


RESOURCE = json.dumps(
    {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "CodeSystem",
                    "id": "cs",
                    "status": "active",
                    "content": "complete",
                }
            },
            {
                "resource": {
                    "resourceType": "Binary",
                    "id": "bin",
                    "contentType": "text/plain",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs",
                    "valueString": "five",
                    "component": [
                        {"valueQuantity": {"value": 3, "unit": "mg", "code": "mg"}},
                        {"valueString": "text"},
                    ],
                }
            },
        ],
    }
)

CASES = {
    "entry.resource.ofType(CodeSystem).single() is DomainResource": (["true"], "true", True),
    "entry.resource.ofType(Binary).single() is Resource": (["true"], "true", True),
    "entry.resource.ofType(Observation).value.is(Integer)": (["false"], "false", True),
    "entry.resource.ofType(Observation).value.as(Integer)": ([], None, True),
    # as() remains singleton-only; ofType() is the collection filter.
    "entry.resource.ofType(Observation).component.value.as(Quantity).unit": ([], None, True),
    "entry.resource.ofType(Observation).component.value.ofType(Quantity).unit": (["mg"], "mg", True),
    "entry.resource.ofType(Observation).value.is(FHIR.Integer)": ([], None, False),
    "Patient.is(System.Patient).not()": ([], None, True),
}


def _make_connections():
    native = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(native) is True
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    fallback = duckdb.connect(config={"allow_unsigned_extensions": True})
    assert register_fhirpath(fallback) is False
    return native, fallback


def _result(con, expression):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_text(?::JSON, ?), fhirpath_is_valid(?)",
        [RESOURCE, expression, RESOURCE, expression, expression],
    ).fetchone()


def main() -> int:
    native, fallback = _make_connections()
    failures = []
    try:
        for expression, expected in CASES.items():
            native_result = _result(native, expression)
            fallback_result = _result(fallback, expression)
            if native_result != fallback_result:
                failures.append((expression, "native != fallback", native_result, fallback_result))
            elif native_result != expected:
                failures.append((expression, "unexpected result", expected, native_result))
    finally:
        native.close()
        fallback.close()

    if failures:
        print("FP-15 architect probe failures:")
        for expression, reason, expected, actual in failures:
            print(f"- {expression}: {reason}")
            print(f"  expected: {expected}")
            print(f"  actual:   {actual}")
        return 1

    print(f"FP-15 architect audit probe passed: {len(CASES)} expressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
