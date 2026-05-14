"""CQL interval operator part 2 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_interval_part2_expressions_parse_and_translate() -> None:
    expressions = [
        "Interval[@2024-01-05, @2024-01-10] included in day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[1, 5] intersect Interval[3, 7]",
        "Interval[1, 3] meets Interval[4, 6]",
        "Interval[1, 3] meets before Interval[4, 6]",
        "Interval[4, 6] meets after Interval[1, 3]",
        "Interval[1, 5] != Interval[1, 6]",
        "Interval[1, 5] !~ Interval[1, 6]",
        "Interval[@2024-02-01, @2024-02-28] on or after day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-01-01, @2024-01-31] on or before day of Interval[@2024-02-01, @2024-02-28]",
        "Interval[@2024-01-01, @2024-01-31] overlaps day of Interval[@2024-01-15, @2024-02-15]",
        "Interval[@2024-01-01, @2024-01-31] overlaps before day of Interval[@2024-01-15, @2024-02-15]",
        "Interval[@2024-01-15, @2024-02-15] overlaps after day of Interval[@2024-01-01, @2024-01-31]",
    ]
    for expression in expressions:
        assert isinstance(parse_expression(expression), BinaryExpression)

    translated = translate_cql(_cql_interval_part2_library())
    assert "intervalIncludedIn" in str(translated["IncludedInPrecision"])
    assert "intervalIntersect" in str(translated["IntersectCheck"])
    assert "intervalMeets" in str(translated["MeetsCheck"])
    assert "intervalMeetsBefore" in str(translated["MeetsBefore"])
    assert "intervalMeetsAfter" in str(translated["MeetsAfter"])
    assert "!=" in translated["NotEqualCheck"].to_sql()
    assert "NOT CASE" in translated["NotEquivalentCheck"].to_sql()
    assert "cqlSameOrAfterP" in str(translated["OnAfter"])
    assert "cqlSameOrBeforeP" in str(translated["OnBefore"])
    assert "intervalOverlaps" in str(translated["OverlapsBefore"])
    assert "intervalOverlaps" in str(translated["OverlapsAfter"])


def test_cql_interval_part2_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_interval_part2_library())
    expected = {
        "IncludedInPrecision": (True,),
        "MeetsCheck": (True,),
        "MeetsBefore": (True,),
        "MeetsAfter": (True,),
        "NotEqualCheck": (True,),
        "NotEquivalentCheck": (True,),
        "OnAfter": (True,),
        "OnBefore": (True,),
        "Overlaps": (True,),
        "OverlapsBefore": (True,),
        "OverlapsAfter": (True,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expr in translated.items():
            sql = f"SELECT {expr.to_sql()}"
            py_result = py.execute(sql).fetchone()
            cpp_result = cpp.execute(sql).fetchone()
            assert cpp_result == py_result, name
            if name in expected:
                assert py_result == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part2_precision_udf_surface_matches_cpp_registration() -> None:
    outer = '{"low":"2024-01-01","high":"2024-01-31","lowClosed":true,"highClosed":true}'
    inner = '{"low":"2024-01-05","high":"2024-01-10","lowClosed":true,"highClosed":true}'
    left = '{"low":"2024-01-01","high":"2024-01-31","lowClosed":true,"highClosed":true}'
    right = '{"low":"2024-01-15","high":"2024-02-15","lowClosed":true,"highClosed":true}'

    cases = [
        ("SELECT intervalIncludedInPrecise(?, ?, 'day')", [inner, outer], (True,)),
        ("SELECT intervalOverlapsPrecise(?, ?, 'day')", [left, right], (True,)),
        ("SELECT intervalOverlapsBeforePrecise(?, ?, 'day')", [left, right], (True,)),
        ("SELECT intervalOverlapsAfterPrecise(?, ?, 'day')", [right, left], (True,)),
        ("SELECT intervalBeforePrecise(?, ?, 'day')", [left, right], (False,)),
        ("SELECT intervalAfterPrecise(?, ?, 'day')", [right, left], (False,)),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, params, expected in cases:
            assert py.execute(sql, params).fetchone() == expected
            assert cpp.execute(sql, params).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def _cql_interval_part2_library() -> str:
    return """library Interval2 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define IncludedInPrecision: Interval[@2024-01-05, @2024-01-10] included in day of Interval[@2024-01-01, @2024-01-31]
define IntersectCheck: Interval[1, 5] intersect Interval[3, 7]
define MeetsCheck: Interval[1, 3] meets Interval[4, 6]
define MeetsBefore: Interval[1, 3] meets before Interval[4, 6]
define MeetsAfter: Interval[4, 6] meets after Interval[1, 3]
define NotEqualCheck: Interval[1, 5] != Interval[1, 6]
define NotEquivalentCheck: Interval[1, 5] !~ Interval[1, 6]
define OnAfter: Interval[@2024-02-01, @2024-02-28] on or after day of Interval[@2024-01-01, @2024-01-31]
define OnBefore: Interval[@2024-01-01, @2024-01-31] on or before day of Interval[@2024-02-01, @2024-02-28]
define Overlaps: Interval[@2024-01-01, @2024-01-31] overlaps day of Interval[@2024-01-15, @2024-02-15]
define OverlapsBefore: Interval[@2024-01-01, @2024-01-31] overlaps before day of Interval[@2024-01-15, @2024-02-15]
define OverlapsAfter: Interval[@2024-01-15, @2024-02-15] overlaps after day of Interval[@2024-01-01, @2024-01-31]
"""
