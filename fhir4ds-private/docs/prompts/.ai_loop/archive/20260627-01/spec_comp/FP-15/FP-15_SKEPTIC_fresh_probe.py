#!/usr/bin/env python3
"""Fresh FP-15 probe for FHIRPath §6.3 type operators."""

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
                    "resourceType": "QuestionnaireResponse",
                    "id": "qr",
                    "status": "completed",
                }
            },
            {
                "resource": {
                    "resourceType": "Binary",
                    "id": "bin",
                    "contentType": "text/plain",
                    "data": "SGVsbG8=",
                }
            },
            {
                "resource": {
                    "resourceType": "Parameters",
                    "id": "params",
                    "parameter": [
                        {"name": "n", "valueInteger": 7},
                        {"name": "s", "valueString": "seven"},
                    ],
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": "obs",
                    "valueInteger": 5,
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
    # Primitive operator/function forms.
    "1 is Integer": (["true"], "true", "[true]", True),
    "1.is(Integer)": (["true"], "true", "[true]", True),
    "1 as Integer": (["1"], "1", "[1]", True),
    "1.as(Integer)": (["1"], "1", "[1]", True),
    "1 is Decimal": (["false"], "false", "[false]", True),
    "1 as Decimal": ([], None, None, True),
    "true is Boolean": (["true"], "true", "[true]", True),
    "true.as(Boolean)": (["true"], "true", "[true]", True),
    # Empty and multi-item singleton behavior at the public UDF boundary.
    "{} is Integer": ([], None, None, True),
    "{} as Integer": ([], None, None, True),
    "(1 | 2) is Integer": ([], None, None, False),
    "(1 | 2).as(Integer)": ([], None, None, False),
    # Invalid type specifiers should make the expression invalid.
    "1 is NoSuchType": ([], None, None, False),
    "1.is(NoSuchType)": ([], None, None, False),
    "1 as NoSuchType": ([], None, None, False),
    "1.as(NoSuchType)": ([], None, None, False),
    # Choice type and complex/FHIR model type behavior.
    "entry.resource.ofType(Observation).value.is(Integer)": (
        ["true"],
        "true",
        "[true]",
        True,
    ),
    "entry.resource.ofType(Observation).value.as(Integer)": (
        ["5"],
        "5",
        "[5]",
        True,
    ),
    "entry.resource.ofType(Observation) is DomainResource": (
        ["true"],
        "true",
        "[true]",
        True,
    ),
    "entry.resource.ofType(Observation) as Resource": (
        [
            '{"resourceType":"Observation","id":"obs","valueInteger":5,'
            '"component":[{"valueQuantity":{"value":3,"unit":"mg","code":"mg"}},'
            '{"valueString":"text"}]}'
        ],
        '{"resourceType":"Observation","id":"obs","valueInteger":5,'
        '"component":[{"valueQuantity":{"value":3,"unit":"mg","code":"mg"}},'
        '{"valueString":"text"}]}',
        '[{"resourceType":"Observation","id":"obs","valueInteger":5,'
        '"component":[{"valueQuantity":{"value":3,"unit":"mg","code":"mg"}},'
        '{"valueString":"text"}]}]',
        True,
    ),
    # Valid R4 resource type specifiers called out by review-10.
    "entry.resource.ofType(CodeSystem).id": (["cs"], "cs", "[\"cs\"]", True),
    "entry.resource.ofType(QuestionnaireResponse).id": (
        ["qr"],
        "qr",
        "[\"qr\"]",
        True,
    ),
    "entry.resource.ofType(Binary).id": (["bin"], "bin", "[\"bin\"]", True),
    "entry.resource.ofType(Parameters).id": (
        ["params"],
        "params",
        "[\"params\"]",
        True,
    ),
    "entry.resource.ofType(CodeSystem).single() is DomainResource": (
        ["true"],
        "true",
        "[true]",
        True,
    ),
    "entry.resource.ofType(Binary).single() is Resource": (
        ["true"],
        "true",
        "[true]",
        True,
    ),
    "entry.resource.ofType(Parameters).single().as(Resource).id": (
        ["params"],
        "params",
        "[\"params\"]",
        True,
    ),
}


def _make_native():
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if not loaded:
        raise AssertionError("native extension did not load")
    return con


def _make_fallback():
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if loaded:
        raise AssertionError("forced fallback unexpectedly loaded native extension")
    return con


def _surfaces(con, expression):
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_is_valid(?)
        """,
        [RESOURCE, expression, RESOURCE, expression, RESOURCE, expression, expression],
    ).fetchone()


def main() -> int:
    native = _make_native()
    fallback = _make_fallback()
    failures = []
    try:
        for expression, expected in CASES.items():
            native_result = _surfaces(native, expression)
            fallback_result = _surfaces(fallback, expression)
            if native_result != fallback_result:
                failures.append((expression, "native != fallback", native_result, fallback_result))
                continue
            if native_result != expected:
                failures.append((expression, "unexpected result", expected, native_result))
    finally:
        native.close()
        fallback.close()

    if failures:
        print("FP-15 failures:")
        for expression, reason, expected, actual in failures:
            print(f"- {expression}: {reason}")
            print(f"  expected: {expected}")
            print(f"  actual:   {actual}")
        return 1

    print(f"FP-15 fresh probe passed: {len(CASES)} expressions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
