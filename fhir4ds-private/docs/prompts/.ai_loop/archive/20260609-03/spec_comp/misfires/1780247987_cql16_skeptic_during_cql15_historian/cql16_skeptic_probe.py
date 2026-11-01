#!/usr/bin/env python3
"""Fresh CQL-16 SKEPTIC probe for interval operators part 2."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.duckdb.tests.integration.wasm_runtime_helpers import no_python_connection
from fhir4ds.cql.translator import translate_cql


def forced_python_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def native_loaded_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def normalize_cell(value):
    if isinstance(value, str) and value.startswith("{"):
        return json.loads(value)
    return value


def run_sql_case(con, sql: str):
    row = con.execute(sql).fetchone()
    return tuple(normalize_cell(cell) for cell in row)


def expect_all(connections, name: str, sql: str, expected):
    observed = {}
    for surface, con in connections.items():
        observed[surface] = run_sql_case(con, sql)
    failures = []
    for surface, row in observed.items():
        if row != expected:
            failures.append(f"{name} on {surface}: expected {expected!r}, observed {row!r}; sql={sql}")
    if len(set(map(repr, observed.values()))) != 1:
        failures.append(f"{name} parity mismatch: {observed!r}")
    return failures


def main() -> None:
    interval_quantity_g = (
        'intervalFromBounds(\'{"value":1,"unit":"g"}\', '
        '\'{"value":3,"unit":"g"}\', true, true)'
    )
    interval_quantity_cm = (
        'intervalFromBounds(\'{"value":1,"unit":"cm"}\', '
        '\'{"value":2,"unit":"cm"}\', true, true)'
    )

    direct_cases = {
        "included-in-precision": (
            "SELECT intervalIncludedInPrecise("
            "intervalFromBounds('2024-01-05','2024-01-10',true,true), "
            "intervalFromBounds('2024-01-01','2024-01-31',true,true), 'day')",
            (True,),
        ),
        "intersect-open-disjoint": (
            "SELECT intervalIntersect(intervalFromBounds('1','5',true,false), "
            "intervalFromBounds('5','7',true,true))",
            (None,),
        ),
        "intersect-unbounded-low": (
            "SELECT intervalIntersect(intervalFromBounds('__null__','5',true,true), "
            "intervalFromBounds('3','7',true,true))",
            ({"low": "3", "high": "5", "lowClosed": True, "highClosed": True},),
        ),
        "meets-before-open-boundary": (
            "SELECT intervalMeetsBefore(intervalFromBounds('1','3',true,true), "
            "intervalFromBounds('3','5',false,true))",
            (True,),
        ),
        "meets-after-open-boundary": (
            "SELECT intervalMeetsAfter(intervalFromBounds('3','5',false,true), "
            "intervalFromBounds('1','3',true,true))",
            (True,),
        ),
        "on-or-after-effective-start": (
            "SELECT intervalOnOrAfter(intervalFromBounds('3','6',false,true), "
            "intervalFromBounds('1','4',true,true))",
            (True,),
        ),
        "on-or-before-effective-end": (
            "SELECT intervalOnOrBefore(intervalFromBounds('1','4',true,false), "
            "intervalFromBounds('3','6',true,true))",
            (True,),
        ),
        "partial-overlaps-is-unknown": (
            "SELECT intervalOverlaps(intervalFromBounds('2014','2014',true,true), "
            "intervalFromBounds('2014-06-01','2014-06-02',true,true))",
            (None,),
        ),
        "partial-overlaps-before-is-unknown": (
            "SELECT intervalOverlapsBefore(intervalFromBounds('2014','2014',true,true), "
            "intervalFromBounds('2014-06-01','2014-06-02',true,true))",
            (None,),
        ),
        "partial-overlaps-after-is-unknown": (
            "SELECT intervalOverlapsAfter(intervalFromBounds('2014-06-01','2014-06-02',true,true), "
            "intervalFromBounds('2014','2014',true,true))",
            (None,),
        ),
        "quantity-overlaps-is-unknown": (
            f"SELECT intervalOverlaps({interval_quantity_g}, {interval_quantity_cm})",
            (None,),
        ),
        "quantity-overlaps-before-is-unknown": (
            f"SELECT intervalOverlapsBefore({interval_quantity_g}, {interval_quantity_cm})",
            (None,),
        ),
        "quantity-overlaps-after-is-unknown": (
            f"SELECT intervalOverlapsAfter({interval_quantity_cm}, {interval_quantity_g})",
            (None,),
        ),
        "not-equivalent-null-null": (
            "SELECT NOT intervalEquivalent(NULL, NULL)",
            (False,),
        ),
        "not-equal-null-null": (
            "SELECT NOT intervalEquals(NULL, NULL)",
            (None,),
        ),
    }

    translated_cql = """library CQL16Skeptic version '1.0.0'
using FHIR version '4.0.1'
context Patient
define IncludedInPrecision: Interval[@2024-01-05, @2024-01-10] included in day of Interval[@2024-01-01, @2024-01-31]
define IntersectCheck: Interval[1, 5] intersect Interval[3, 7]
define IntersectOpenDisjoint: Interval[1, 5) intersect Interval[5, 7]
define MeetsBeforeOpen: Interval[1, 3] meets before Interval(3, 5]
define MeetsAfterOpen: Interval(3, 5] meets after Interval[1, 3]
define NotEqualNull: (null as Interval<Integer>) != (null as Interval<Integer>)
define NotEquivalentNull: (null as Interval<Integer>) !~ (null as Interval<Integer>)
define OnAfterOpen: Interval(3, 6] on or after Interval[1, 4]
define OnBeforeOpen: Interval[1, 4) on or before Interval[3, 6]
define PartialOverlapsBefore: Interval[@2014, @2014] overlaps before Interval[@2014-06-01, @2014-06-02]
define PartialOverlapsAfter: Interval[@2014-06-01, @2014-06-02] overlaps after Interval[@2014, @2014]
define QuantityOverlapsBefore: Interval[1 'g', 3 'g'] overlaps before Interval[1 'cm', 2 'cm']
define QuantityOverlapsAfter: Interval[1 'cm', 2 'cm'] overlaps after Interval[1 'g', 3 'g']
"""
    translated_expected = {
        "IncludedInPrecision": (True,),
        "IntersectCheck": ({"low": "3", "high": "5", "lowClosed": True, "highClosed": True},),
        "IntersectOpenDisjoint": (None,),
        "MeetsBeforeOpen": (True,),
        "MeetsAfterOpen": (True,),
        "NotEqualNull": (None,),
        "NotEquivalentNull": (False,),
        "OnAfterOpen": (True,),
        "OnBeforeOpen": (True,),
        "PartialOverlapsBefore": (None,),
        "PartialOverlapsAfter": (None,),
        "QuantityOverlapsBefore": (None,),
        "QuantityOverlapsAfter": (None,),
    }
    translated = translate_cql(translated_cql)

    py = forced_python_connection()
    native = native_loaded_connection()
    try:
        with no_python_connection() as no_py:
            connections = {
                "forced-python": py,
                "native-loaded": native,
                "no-python-cpp": no_py,
            }
            failures = []
            for name, (sql, expected) in direct_cases.items():
                failures.extend(expect_all(connections, name, sql, expected))
            for name, expected in translated_expected.items():
                failures.extend(
                    expect_all(connections, f"translated-{name}", f"SELECT {translated[name].to_sql()}", expected)
                )
            if failures:
                raise AssertionError("\n".join(failures))
    finally:
        py.close()
        native.close()


if __name__ == "__main__":
    main()
