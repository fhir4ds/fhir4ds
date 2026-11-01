#!/usr/bin/env python3
"""Fresh FP-12 HISTORIAN probe for FHIRPath §5.8 and §5.9.

This script compares the bundled native DuckDB extension with the forced
Python fallback registration for tree navigation and utility functions.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402

from fhir4ds.fhirpath.duckdb import register_fhirpath  # noqa: E402


RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "active": None,
        "birthDate": "1970-01-01",
        "_birthDate": {
            "extension": [
                {
                    "url": "http://example.org/ext/birth",
                    "valueString": "hidden-by-children",
                }
            ]
        },
        "name": [
            {"given": ["Ann"], "family": "Able"},
            {"given": ["Bob"], "family": "Baker"},
        ],
        "contact": [{"telecom": [{"value": "555"}]}],
        "dupeA": {"x": 1, "y": 2},
        "dupeB": {"y": 2, "x": 1},
    },
    separators=(",", ":"),
)

MULTI_GIVEN_RESOURCE = json.dumps(
    {
        "resourceType": "Patient",
        "id": "p1",
        "name": [{"given": ["Ann", "Al"], "family": "Able"}],
    },
    separators=(",", ":"),
)

DEEP_RESOURCE_OBJ = {"resourceType": "Patient", "id": "p1"}
_cursor = DEEP_RESOURCE_OBJ
for depth in range(115):
    _cursor["child"] = {"valueString": f"v{depth}"}
    _cursor = _cursor["child"]
DEEP_RESOURCE = json.dumps(DEEP_RESOURCE_OBJ, separators=(",", ":"))


def make_native_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded_native = register_fhirpath(con)
    if not loaded_native:
        raise RuntimeError("Expected native FHIRPath extension to load")
    return con


def make_fallback_connection() -> duckdb.DuckDBPyConnection:
    original_version = duckdb.__version__
    try:
        duckdb.__version__ = "0.0.0-fp12-forced-python-fallback"
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        loaded_native = register_fhirpath(con)
    finally:
        duckdb.__version__ = original_version
    if loaded_native:
        con.close()
        raise RuntimeError("Expected forced Python fallback registration")
    return con


def eval_row(con: duckdb.DuckDBPyConnection, resource: str, expression: str) -> tuple:
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_number(?::JSON, ?),
          fhirpath_is_valid(?)
        """,
        [
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            resource,
            expression,
            expression,
        ],
    ).fetchone()


def assert_same(native: duckdb.DuckDBPyConnection, fallback: duckdb.DuckDBPyConnection, resource: str, expression: str) -> tuple:
    native_row = eval_row(native, resource, expression)
    fallback_row = eval_row(fallback, resource, expression)
    if native_row != fallback_row:
        raise AssertionError(
            f"native/fallback mismatch for {expression!r}\n"
            f"native={native_row!r}\n"
            f"fallback={fallback_row!r}"
        )
    return native_row


def assert_expected(row: tuple, expected: tuple, expression: str) -> None:
    if row != expected:
        raise AssertionError(f"unexpected result for {expression!r}: expected={expected!r} actual={row!r}")


def main() -> None:
    native = make_native_connection()
    fallback = make_fallback_connection()
    checked = 0
    try:
        expected_cases = {
            "children().count()": (["8"], "[8]", "8", None, 8.0, True),
            "children().where($this = 'hidden-by-children').count()": (["0"], "[0]", "0", False, 0.0, True),
            "descendants().where($this = 'hidden-by-children').count()": (["0"], "[0]", "0", False, 0.0, True),
            "descendants().count() = repeat(children()).count()": (["true"], "[true]", "true", True, None, True),
            "descendants().where($this = 'Ann').count()": (["1"], "[1]", "1", True, 1.0, True),
            "descendants().where($this = '555').count()": (["1"], "[1]", "1", True, 1.0, True),
            "children().where($this.empty()).count()": (["0"], "[0]", "0", False, 0.0, True),
            "name.children().count()": (["4"], "[4]", "4", None, 4.0, True),
            "name.descendants().where($this = 'Bob').count()": (["1"], "[1]", "1", True, 1.0, True),
            "name.trace('names').given.count() = 2": (["true"], "[true]", "true", True, None, True),
            "name.trace('names', given).given.count() = 2": (["true"], "[true]", "true", True, None, True),
            "name.trace('names', given.single()).given.count() = 2": (["true"], "[true]", "true", True, None, True),
            "name.trace('idx', $index.single()).given.count() = 2": (["true"], "[true]", "true", True, None, True),
            "name.trace(id).given.count() = 2": (["true"], "[true]", "true", True, None, True),
            "name.select($this.trace('t', given.single()).given.count() = 1 and $index >= 0).allTrue()": (
                ["true"],
                "[true]",
                "true",
                True,
                None,
                True,
            ),
            "now() = now()": (["true"], "[true]", "true", True, None, True),
            "today() = today()": (["true"], "[true]", "true", True, None, True),
            "timeOfDay() = timeOfDay()": (["true"], "[true]", "true", True, None, True),
            "today().toString().length() = 10": (["true"], "[true]", "true", True, None, True),
            "now().toString().length() > 10": (["true"], "[true]", "true", True, None, True),
        }
        for expression, expected in expected_cases.items():
            row = assert_same(native, fallback, RESOURCE, expression)
            assert_expected(row, expected, expression)
            checked += 1

        deep_expression = "descendants().where($this = 'v114').count()"
        row = assert_same(native, fallback, DEEP_RESOURCE, deep_expression)
        assert_expected(row, (["1"], "[1]", "1", True, 1.0, True), deep_expression)
        checked += 1

        projection_error_expression = "name.trace('names', given.single()).given.count() = 2"
        row = assert_same(native, fallback, MULTI_GIVEN_RESOURCE, projection_error_expression)
        assert_expected(row, ([], None, None, None, None, True), projection_error_expression)
        checked += 1

        invalid_cases = [
            "children(1)",
            "descendants(1)",
            "trace()",
            "trace(1)",
            "trace('x', id, id)",
            "now(1)",
            "today(1)",
            "timeOfDay(1)",
        ]
        for expression in invalid_cases:
            row = assert_same(native, fallback, RESOURCE, expression)
            assert_expected(row, ([], None, None, None, None, False), expression)
            checked += 1

        for expression, pattern in [
            ("now().toString()", r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"),
            ("today().toString()", r"^\d{4}-\d{2}-\d{2}$"),
            ("timeOfDay().toString()", r"^T?\d{2}:\d{2}:\d{2}(?:\.\d+)?$"),
        ]:
            native_text = eval_row(native, RESOURCE, expression)[2]
            fallback_text = eval_row(fallback, RESOURCE, expression)[2]
            if not re.match(pattern, native_text or ""):
                raise AssertionError(f"native {expression!r} text has wrong shape: {native_text!r}")
            if not re.match(pattern, fallback_text or ""):
                raise AssertionError(f"fallback {expression!r} text has wrong shape: {fallback_text!r}")
            checked += 1

    finally:
        native.close()
        fallback.close()

    print(f"FP-12 HISTORIAN fresh probe passed: {checked} expressions")


if __name__ == "__main__":
    main()
