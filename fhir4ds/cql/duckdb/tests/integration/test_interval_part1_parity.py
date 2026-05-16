"""CQL interval operator part 1 parity checks."""

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


def test_cql_interval_part1_expressions_parse_and_translate() -> None:
    binary_expressions = [
        "Interval[@2024-02-01, @2024-02-28] after day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-01-01, @2024-01-31] before day of Interval[@2024-02-01, @2024-02-28]",
        "Interval[@2024-01-01, @2024-01-31] contains day of @2024-01-05",
        "Interval[@2024-01-01, @2024-01-31] ends day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[1, 5] = Interval[1, 5]",
        "Interval[1, 5] ~ Interval[1, 5]",
        "Interval[1, 5] except Interval[2, 3]",
        "@2024-01-05 in day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-01-01, @2024-01-31] includes day of Interval[@2024-01-05, @2024-01-10]",
    ]
    for expression in binary_expressions:
        assert isinstance(parse_expression(expression), BinaryExpression)

    assert isinstance(parse_expression("end of Interval[@2024-01-01, @2024-01-31]"), UnaryExpression)
    assert isinstance(parse_expression("collapse { Interval[1, 3], Interval[4, 6] }"), FunctionRef)
    assert isinstance(parse_expression("expand Interval[1, 3]"), FunctionRef)

    cql = """library Interval1 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AfterPrecision: Interval[@2024-02-01, @2024-02-28] after day of Interval[@2024-01-01, @2024-01-31]
define BeforePrecision: Interval[@2024-01-01, @2024-01-31] before day of Interval[@2024-02-01, @2024-02-28]
define ContainsPrecision: Interval[@2024-01-01, @2024-01-31] contains day of @2024-01-05
define EndCheck: end of Interval[@2024-01-01, @2024-01-31]
define EndsPrecision: Interval[@2024-01-01, @2024-01-31] ends day of Interval[@2024-01-01, @2024-01-31]
define EqualCheck: Interval[1, 5] = Interval[1, 5]
define EquivalentCheck: Interval[1, 5] ~ Interval[1, 5]
define ExceptCheck: Interval[1, 5] except Interval[2, 3]
define InPrecision: @2024-01-05 in day of Interval[@2024-01-01, @2024-01-31]
define IncludesPrecision: Interval[@2024-01-01, @2024-01-31] includes day of Interval[@2024-01-05, @2024-01-10]
define CollapseCheck: collapse { Interval[1, 3], Interval[4, 6] }
define ExpandCheck: expand Interval[1, 3]
"""
    translated = translate_cql(cql)

    assert "cqlAfterP" in str(translated["AfterPrecision"])
    assert "cqlBeforeP" in str(translated["BeforePrecision"])
    assert "intervalContains" in str(translated["ContainsPrecision"])
    assert "intervalEnd" in str(translated["EndCheck"])
    assert "intervalEnd" in str(translated["EndsPrecision"])
    assert "intervalExcept" in str(translated["ExceptCheck"])
    assert "2024-01-05" in str(translated["InPrecision"])
    assert "intervalIncludes" in str(translated["IncludesPrecision"])
    assert "collapse_intervals" in str(translated["CollapseCheck"])
    assert "expand_points1" in str(translated["ExpandCheck"])


def test_cql_interval_part1_translated_sql_matches_cpp_registration() -> None:
    cql = """library Interval1Eval version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AfterPrecision: Interval[@2024-02-01, @2024-02-28] after day of Interval[@2024-01-01, @2024-01-31]
define BeforePrecision: Interval[@2024-01-01, @2024-01-31] before day of Interval[@2024-02-01, @2024-02-28]
define ContainsPrecision: Interval[@2024-01-01, @2024-01-31] contains day of @2024-01-05
define EndCheck: end of Interval[@2024-01-01, @2024-01-31]
define EndsPrecision: Interval[@2024-01-01, @2024-01-31] ends day of Interval[@2024-01-01, @2024-01-31]
define ExceptCheck: Interval[1, 5] except Interval[2, 3]
define InPrecision: @2024-01-05 in day of Interval[@2024-01-01, @2024-01-31]
define IncludesPrecision: Interval[@2024-01-01, @2024-01-31] includes day of Interval[@2024-01-05, @2024-01-10]
define CollapseCheck: collapse { Interval[1, 3], Interval[4, 6] }
define ExpandCheck: expand Interval[1, 3]
"""
    translated = translate_cql(cql)
    py = _python_only_connection()
    cpp = _cpp_connection()
    expected = {
        "AfterPrecision": (True,),
        "BeforePrecision": (True,),
        "ContainsPrecision": (True,),
        "EndCheck": ("2024-01-31",),
        "EndsPrecision": (True,),
        "InPrecision": (True,),
        "IncludesPrecision": (True,),
    }
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


def test_cql_interval_part1_precision_udf_surface_matches_cpp_registration() -> None:
    outer = '{"low":"2024-01-01","high":"2024-01-31","lowClosed":true,"highClosed":true}'
    inner = '{"low":"2024-01-05","high":"2024-01-10","lowClosed":true,"highClosed":true}'
    before = '{"low":"2024-01-01","high":"2024-01-31","lowClosed":true,"highClosed":true}'
    after = '{"low":"2024-02-01","high":"2024-02-28","lowClosed":true,"highClosed":true}'

    cases = [
        ("SELECT intervalIncludesPrecise(?, ?, 'day')", [outer, inner], (True,)),
        ("SELECT intervalIncludesPrecise(?, ?, 'day')", [inner, outer], (False,)),
        ("SELECT intervalIncludedInPrecise(?, ?, 'day')", [inner, outer], (True,)),
        ("SELECT intervalContainsPrecise(?, ?, 'day')", [outer, "2024-01-05"], (True,)),
        ("SELECT intervalBeforePrecise(?, ?, 'day')", [before, after], (True,)),
        ("SELECT intervalAfterPrecise(?, ?, 'day')", [after, before], (True,)),
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
