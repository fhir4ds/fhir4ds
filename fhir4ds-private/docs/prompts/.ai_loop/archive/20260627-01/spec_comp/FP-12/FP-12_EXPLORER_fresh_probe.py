#!/usr/bin/env python3
"""Fresh FP-12 EXPLORER probe for FHIRPath tree navigation and utilities."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fhir4ds.fhirpath.duckdb import register_fhirpath


PATIENT_WITH_PRIMITIVE_EXTENSIONS = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "birthDate": "1970-01-01",
        "_birthDate": {
            "extension": [
                {
                    "url": "http://example.org/fhir/StructureDefinition/birth-note",
                    "valueString": "midday",
                }
            ]
        },
        "name": [
            {
                "given": ["Ann"],
                "_given": [
                    {
                        "extension": [
                            {
                                "url": "http://example.org/fhir/StructureDefinition/given-note",
                                "valueString": "alias",
                            }
                        ]
                    }
                ],
                "family": "Able",
            },
            {"given": ["Bob"], "family": "Baker"},
        ],
        "telecom": [
            {"system": "phone", "value": "555"},
            {"system": "email", "value": "ann@example.test"},
        ],
    }
)

DUPLICATE_TREE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "dup",
        "left": {"x": 1, "y": 2},
        "right": {"y": 2, "x": 1},
        "tags": ["same", "same"],
    }
)


EXPECTED_ROWS = [
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "birthDate.extension('http://example.org/fhir/StructureDefinition/birth-note').valueString",
        (["midday"], '["midday"]', True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "birthDate.children().where(url = 'http://example.org/fhir/StructureDefinition/birth-note').valueString",
        (["midday"], '["midday"]', True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "birthDate.descendants().where($this = 'midday').count()",
        (["1"], "[1]", True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "name.given.extension('http://example.org/fhir/StructureDefinition/given-note').valueString",
        (["alias"], '["alias"]', True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "name.given.children().where(url = 'http://example.org/fhir/StructureDefinition/given-note').valueString",
        (["alias"], '["alias"]', True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "name.given.descendants().where($this = 'alias').count()",
        (["1"], "[1]", True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "name.trace('names', given.single()).given.count() = 2",
        (["true"], "[true]", True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "name.trace(id, given.single()).given.count() = 2",
        (["true"], "[true]", True),
    ),
    (
        PATIENT_WITH_PRIMITIVE_EXTENSIONS,
        "name.trace('idx', $index.single()).given.count() = 2",
        (["true"], "[true]", True),
    ),
    (
        DUPLICATE_TREE,
        "descendants().count() = repeat(children()).count()",
        (["true"], "[true]", True),
    ),
    (
        DUPLICATE_TREE,
        "children(1)",
        ([], None, False),
    ),
    (
        DUPLICATE_TREE,
        "descendants(1)",
        ([], None, False),
    ),
    (
        DUPLICATE_TREE,
        "trace()",
        ([], None, False),
    ),
    (
        DUPLICATE_TREE,
        "trace('x', id, id)",
        ([], None, False),
    ),
    (
        DUPLICATE_TREE,
        "now(1)",
        ([], None, False),
    ),
    (
        DUPLICATE_TREE,
        "today(1)",
        ([], None, False),
    ),
    (
        DUPLICATE_TREE,
        "timeOfDay(1)",
        ([], None, False),
    ),
    (
        DUPLICATE_TREE,
        "now() = now()",
        (["true"], "[true]", True),
    ),
    (
        DUPLICATE_TREE,
        "today() = today()",
        (["true"], "[true]", True),
    ),
    (
        DUPLICATE_TREE,
        "timeOfDay() = timeOfDay()",
        (["true"], "[true]", True),
    ),
    (
        DUPLICATE_TREE,
        "now().toString().length() > 10",
        (["true"], "[true]", True),
    ),
    (
        DUPLICATE_TREE,
        "today().toString().length() = 10",
        (["true"], "[true]", True),
    ),
]


def connect_native() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if loaded is not True:
        raise AssertionError(f"expected native extension registration, got {loaded!r}")
    return con


def connect_fallback() -> duckdb.DuckDBPyConnection:
    duckdb.__version__ = "0.0.0-forced-python-fallback"
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if loaded is not False:
        raise AssertionError(f"expected forced Python fallback registration, got {loaded!r}")
    return con


def evaluate(con: duckdb.DuckDBPyConnection, resource: str, expression: str):
    return con.execute(
        "SELECT fhirpath(?::JSON, ?), fhirpath_json(?::JSON, ?), fhirpath_is_valid(?)",
        [resource, expression, resource, expression, expression],
    ).fetchone()


def main() -> int:
    failures: list[str] = []
    native = connect_native()
    fallback = connect_fallback()
    try:
        for resource, expression, expected in EXPECTED_ROWS:
            native_row = evaluate(native, resource, expression)
            fallback_row = evaluate(fallback, resource, expression)
            if native_row != fallback_row:
                failures.append(
                    f"backend mismatch for {expression!r}: native={native_row!r}, fallback={fallback_row!r}"
                )
            if native_row != expected:
                failures.append(f"native wrong for {expression!r}: actual={native_row!r}, expected={expected!r}")
            if fallback_row != expected:
                failures.append(f"fallback wrong for {expression!r}: actual={fallback_row!r}, expected={expected!r}")
    finally:
        native.close()
        fallback.close()

    if failures:
        print("FP-12 EXPLORER probe found failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"FP-12 EXPLORER probe passed: {len(EXPECTED_ROWS)} expressions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
