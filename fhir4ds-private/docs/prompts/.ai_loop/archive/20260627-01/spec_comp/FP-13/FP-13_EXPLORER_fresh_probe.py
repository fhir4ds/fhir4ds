#!/usr/bin/env python3
"""Fresh FP-13 EXPLORER probe for FHIRPath §6.1 equality/equivalence.

This probe is intentionally independent of prior FP-13 artifacts. It compares
native DuckDB/C++ registration, forced Python fallback registration, and direct
Python fallback UDF surfaces for composed equality/equivalence cases.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import duckdb

from fhir4ds.fhirpath.duckdb import register_fhirpath
from fhir4ds.fhirpath.duckdb.udf import (
    fhirpath_bool_udf,
    fhirpath_json_udf,
    fhirpath_scalar,
    fhirpath_text_udf,
)


@dataclass(frozen=True)
class Case:
    expression: str
    expected_bool: bool | None
    expected_list: list[str]
    expected_json: str | None


RESOURCE = json.dumps(
    {
        "resourceType": "Observation",
        "id": "fp13-explorer",
        "valueQuantity": {
            "value": 185,
            "unit": "lbs",
            "code": "[lb_av]",
            "system": "http://unitsofmeasure.org",
        },
        "unitOne": {
            "value": 23,
            "unit": "1",
            "code": "1",
            "system": "http://unitsofmeasure.org",
        },
        "unitOneOther": {
            "value": 24,
            "unit": "1",
            "code": "1",
            "system": "http://unitsofmeasure.org",
        },
        "component": [
            {
                "valueQuantity": {
                    "value": 23,
                    "unit": "1",
                    "code": "1",
                    "system": "http://unitsofmeasure.org",
                }
            },
            {
                "valueQuantity": {
                    "value": 24,
                    "unit": "1",
                    "code": "1",
                    "system": "http://unitsofmeasure.org",
                }
            },
        ],
        "lengthRangeA": {
            "low": {"value": 1, "unit": "cm", "code": "cm"},
            "high": {"value": 2, "unit": "cm", "code": "cm"},
        },
        "lengthRangeB": {
            "high": {"value": 20, "unit": "mm", "code": "mm"},
            "low": {"value": 10, "unit": "mm", "code": "mm"},
        },
        "badRange": {
            "low": {"value": 1, "unit": "cm", "code": "cm"},
            "high": {"value": 1, "unit": "s", "code": "s"},
        },
        "stringsA": ["Alpha\u00a0Beta", "Gamma"],
        "stringsB": ["gamma", "alpha beta"],
        "a": 9007199254740992,
        "b": 9007199254740993,
        "largeA": {"value": 9007199254740992},
        "largeB": {"value": 9007199254740993},
        "largeArrayA": [9007199254740992, 9007199254740994],
        "largeArrayB": [9007199254740992, 9007199254740995],
    },
    separators=(",", ":"),
)


CASES = [
    Case("lengthRangeA = lengthRangeB", True, ["true"], "[true]"),
    Case("lengthRangeA != lengthRangeB", False, ["false"], "[false]"),
    Case("lengthRangeA ~ lengthRangeB", True, ["true"], "[true]"),
    Case("lengthRangeA !~ lengthRangeB", False, ["false"], "[false]"),
    Case("lengthRangeA = badRange", None, [], None),
    Case("lengthRangeA != badRange", None, [], None),
    Case("lengthRangeA ~ badRange", None, [], None),
    Case("lengthRangeA !~ badRange", None, [], None),
    Case("Observation.value = 185 '[lb_av]'", True, ["true"], "[true]"),
    Case("Observation.value ~ 83.9 'kg'", True, ["true"], "[true]"),
    Case("Observation.value !~ 83.9 'kg'", False, ["false"], "[false]"),
    Case("23 = 23 '1'", True, ["true"], "[true]"),
    Case("23 != 23 '1'", False, ["false"], "[false]"),
    Case("23 ~ 23 '1'", True, ["true"], "[true]"),
    Case("23 !~ 23 '1'", False, ["false"], "[false]"),
    Case("component[0].value = 23", True, ["true"], "[true]"),
    Case("component[0].value != 23", False, ["false"], "[false]"),
    Case("component.value = (23 | 24)", True, ["true"], "[true]"),
    Case("component.value ~ (24 | 23)", True, ["true"], "[true]"),
    Case("1 year = 1 'a'", None, [], None),
    Case("1 year != 1 'a'", None, [], None),
    Case("1 year ~ 1 'a'", True, ["true"], "[true]"),
    Case("1 'cm' = 1 's'", None, [], None),
    Case("1 'cm' != 1 's'", None, [], None),
    Case("1 'cm' ~ 1 's'", None, [], None),
    Case("1 'cm' !~ 1 's'", None, [], None),
    Case("@2017-11-05T01:30:00.0-04:00 = @2017-11-05T00:30:00.0-05:00", True, ["true"], "[true]"),
    Case("@2012 = @2012-01", None, [], None),
    Case("@2012 ~ @2012-01", False, ["false"], "[false]"),
    Case("stringsA ~ stringsB", True, ["true"], "[true]"),
    Case("stringsA !~ stringsB", False, ["false"], "[false]"),
    Case("a = b", False, ["false"], "[false]"),
    Case("a != b", True, ["true"], "[true]"),
    Case("a ~ b", False, ["false"], "[false]"),
    Case("a !~ b", True, ["true"], "[true]"),
    Case("largeA = largeB", False, ["false"], "[false]"),
    Case("largeA != largeB", True, ["true"], "[true]"),
    Case("largeA ~ largeB", False, ["false"], "[false]"),
    Case("largeA !~ largeB", True, ["true"], "[true]"),
    Case("largeArrayA = largeArrayB", False, ["false"], "[false]"),
    Case("largeArrayA != largeArrayB", True, ["true"], "[true]"),
    Case("largeArrayA ~ largeArrayB", False, ["false"], "[false]"),
    Case("largeArrayA !~ largeArrayB", True, ["true"], "[true]"),
]


def make_native() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    loaded = register_fhirpath(con)
    if not loaded:
        raise RuntimeError("native C++ extension did not load")
    return con


def make_fallback() -> duckdb.DuckDBPyConnection:
    original_version = duckdb.__version__
    try:
        duckdb.__version__ = "0.0.0-forced-python-fallback"
        con = duckdb.connect(config={"allow_unsigned_extensions": True})
        loaded = register_fhirpath(con)
        if loaded:
            raise RuntimeError("forced Python fallback unexpectedly loaded native extension")
        return con
    finally:
        duckdb.__version__ = original_version


def sql_outputs(con: duckdb.DuckDBPyConnection, expression: str) -> tuple[Any, ...]:
    return con.execute(
        """
        SELECT
          fhirpath(?::JSON, ?),
          fhirpath_text(?::JSON, ?),
          fhirpath_json(?::JSON, ?),
          fhirpath_bool(?::JSON, ?),
          fhirpath_is_valid(?)
        """,
        [
            RESOURCE,
            expression,
            RESOURCE,
            expression,
            RESOURCE,
            expression,
            RESOURCE,
            expression,
            expression,
        ],
    ).fetchone()


def direct_outputs(expression: str) -> tuple[Any, ...]:
    return (
        fhirpath_scalar(RESOURCE, expression),
        fhirpath_text_udf(RESOURCE, expression),
        fhirpath_json_udf(RESOURCE, expression),
        fhirpath_bool_udf(RESOURCE, expression),
    )


def main() -> int:
    failures: list[str] = []
    native = make_native()
    fallback = make_fallback()
    try:
        for case in CASES:
            expected_sql = (
                case.expected_list,
                case.expected_list[0] if case.expected_list else None,
                case.expected_json,
                case.expected_bool,
                True,
            )
            expected_direct = expected_sql[:4]
            native_row = sql_outputs(native, case.expression)
            fallback_row = sql_outputs(fallback, case.expression)
            direct_row = direct_outputs(case.expression)
            if native_row != expected_sql:
                failures.append(
                    f"native mismatch: {case.expression!r}: {native_row!r} != {expected_sql!r}"
                )
            if fallback_row != expected_sql:
                failures.append(
                    f"fallback mismatch: {case.expression!r}: {fallback_row!r} != {expected_sql!r}"
                )
            if direct_row != expected_direct:
                failures.append(
                    f"direct fallback mismatch: {case.expression!r}: {direct_row!r} != {expected_direct!r}"
                )
            if native_row != fallback_row:
                failures.append(
                    f"backend drift: {case.expression!r}: native {native_row!r}, fallback {fallback_row!r}"
                )
    finally:
        native.close()
        fallback.close()

    if failures:
        print("FP-13 EXPLORER fresh probe failures:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"FP-13 EXPLORER fresh probe passed: {len(CASES)} expressions")
    return 0


if __name__ == "__main__":
    sys.exit(main())
