"""CQL interval operator part 3 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef, UnaryExpression
from fhir4ds.cql.translator import translate_cql


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def test_cql_interval_part3_expressions_parse_and_translate() -> None:
    assert isinstance(parse_expression("point from Interval[5, 5]"), UnaryExpression)
    assert isinstance(parse_expression("Size(Interval[1, 5])"), FunctionRef)
    assert isinstance(parse_expression("start of Interval[@2024-01-01, @2024-01-31]"), UnaryExpression)
    assert isinstance(parse_expression("width of Interval[1, 5]"), UnaryExpression)

    for expression in [
        "Interval[@2024-01-01, @2024-01-31] properly includes day of Interval[@2024-01-05, @2024-01-10]",
        "Interval[@2024-01-05, @2024-01-10] properly included in day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-01-01, @2024-01-31] same day as Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-02-01, @2024-02-28] same or after day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-01-01, @2024-01-31] same or before day of Interval[@2024-02-01, @2024-02-28]",
        "Interval[@2024-01-01, @2024-01-10] starts day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[1, 3] union Interval[4, 6]",
    ]:
        assert isinstance(parse_expression(expression), BinaryExpression)

    translated = translate_cql(_cql_interval_part3_library())
    assert "pointFrom" in str(translated["PointFrom"])
    assert "intervalProperlyIncludes" in str(translated["ProperIncludes"])
    assert "intervalProperlyIncludedIn" in str(translated["ProperIncludedIn"])
    assert "cqlSameAsP" in str(translated["SameAs"])
    assert "cqlSameOrAfterP" in str(translated["SameAfter"])
    assert "cqlSameOrBeforeP" in str(translated["SameBefore"])
    assert "interval_size" in str(translated["SizeCheck"])
    assert "intervalStart" in str(translated["StartCheck"])
    assert "intervalStart" in str(translated["StartsPrecision"])
    assert "intervalUnion" in str(translated["UnionCheck"])
    assert "intervalWidth" in str(translated["WidthCheck"])


def test_cql_interval_part3_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_interval_part3_library())
    expected = {
        "PointFrom": ("5",),
        "ProperIncludes": (True,),
        "ProperIncludedIn": (True,),
        "SameAs": (True,),
        "SameAfter": (True,),
        "SameBefore": (True,),
        "SizeCheck": ("5",),
        "StartCheck": ("2024-01-01",),
        "StartsPrecision": (True,),
        "WidthCheck": ("4",),
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


def test_cql_interval_part3_direct_udf_surface_matches_cpp_registration() -> None:
    unit = '{"low":"5","high":"5","lowClosed":true,"highClosed":true}'
    numeric = '{"low":"1","high":"5","lowClosed":true,"highClosed":true}'
    outer = '{"low":"2024-01-01","high":"2024-01-31","lowClosed":true,"highClosed":true}'
    inner = '{"low":"2024-01-05","high":"2024-01-10","lowClosed":true,"highClosed":true}'
    starts = '{"low":"2024-01-01","high":"2024-01-10","lowClosed":true,"highClosed":true}'
    union_left = '{"low":"1","high":"3","lowClosed":true,"highClosed":true}'
    union_right = '{"low":"4","high":"6","lowClosed":true,"highClosed":true}'

    cases = [
        ("SELECT pointFrom(?)", [unit], ("5",)),
        ("SELECT intervalWidth(?)", [numeric], ("4",)),
        ("SELECT interval_size(?)", [numeric], ("5",)),
        ("SELECT intervalProperlyIncludes(?, ?)", [outer, inner], (True,)),
        ("SELECT intervalProperlyIncludedIn(?, ?)", [inner, outer], (True,)),
        ("SELECT intervalStartsSame(?, ?)", [starts, outer], (True,)),
        ("SELECT intervalUnion(?, ?) IS NOT NULL", [union_left, union_right], (True,)),
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


def _cql_interval_part3_library() -> str:
    return """library Interval3 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define PointFrom: point from Interval[5, 5]
define ProperIncludes: Interval[@2024-01-01, @2024-01-31] properly includes day of Interval[@2024-01-05, @2024-01-10]
define ProperIncludedIn: Interval[@2024-01-05, @2024-01-10] properly included in day of Interval[@2024-01-01, @2024-01-31]
define SameAs: Interval[@2024-01-01, @2024-01-31] same day as Interval[@2024-01-01, @2024-01-31]
define SameAfter: Interval[@2024-02-01, @2024-02-28] same or after day of Interval[@2024-01-01, @2024-01-31]
define SameBefore: Interval[@2024-01-01, @2024-01-31] same or before day of Interval[@2024-02-01, @2024-02-28]
define SizeCheck: Size(Interval[1, 5])
define StartCheck: start of Interval[@2024-01-01, @2024-01-31]
define StartsPrecision: Interval[@2024-01-01, @2024-01-10] starts day of Interval[@2024-01-01, @2024-01-31]
define UnionCheck: Interval[1, 3] union Interval[4, 6]
define WidthCheck: width of Interval[1, 5]
"""
