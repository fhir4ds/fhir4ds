"""CQL interval operator part 3 parity checks."""

from __future__ import annotations

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression, FunctionRef, UnaryExpression
from fhir4ds.cql.translator import translate_cql

from .wasm_runtime_helpers import no_python_connection


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
        "Interval[1, 5] properly includes 1",
        "1 properly included in Interval[1, 5]",
        "Interval[@2024-01-01, @2024-01-31] same day as Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-01-01, @2024-01-10] same day as Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-02-01, @2024-02-28] same or after day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024-01-01, @2024-01-31] same or before day of Interval[@2024-02-01, @2024-02-28]",
        "Interval(0, 5] starts Interval[1, 5]",
        "Interval[1, 10] starts Interval[1, 5]",
        "Interval[@2024-01-01, @2024-01-10] starts day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[@2024, @2024] starts day of Interval[@2024-01-01, @2024-01-31]",
        "Interval[1, 3] union Interval[4, 6]",
    ]:
        assert isinstance(parse_expression(expression), BinaryExpression)

    translated = translate_cql(_cql_interval_part3_library())
    assert "pointFrom" in str(translated["PointFrom"])
    assert "intervalIncludesPrecise" in str(translated["ProperIncludes"])
    assert "intervalIncludesPrecise" in str(translated["ProperIncludesUncertain"])
    assert "intervalIncludesPrecise" in str(translated["ProperIncludedIn"])
    assert "intervalIncludesPrecise" in str(translated["ProperIncludedInUncertain"])
    assert "cqlSameAsP" in str(translated["SameAs"])
    assert "intervalStart" in str(translated["SameAs"])
    assert "intervalEnd" in str(translated["SameAs"])
    assert "cqlSameAsP" in str(translated["SameAsDifferentEnd"])
    assert "cqlSameOrAfterP" in str(translated["SameAfter"])
    assert "intervalStart" in str(translated["SameAfter"])
    assert "intervalEnd" in str(translated["SameAfter"])
    assert "cqlSameOrBeforeP" in str(translated["SameBefore"])
    assert "interval_size" in str(translated["SizeCheck"])
    assert "intervalStart" in str(translated["StartCheck"])
    assert "intervalStart" in str(translated["StartsPrecision"])
    assert "intervalUnion" in str(translated["UnionCheck"])
    assert "intervalWidth" in str(translated["WidthCheck"])
    assert "intervalStart" in str(translated["DecimalOpenStart"])
    assert "intervalEnd" in str(translated["DecimalOpenEnd"])
    assert "intervalWidth" in str(translated["DecimalOpenWidth"])
    assert "interval_size" in str(translated["DecimalClosedSize"])
    assert "intervalUnion" in str(translated["UnionOpenLowContainsExcluded"])


def test_cql_interval_part3_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_interval_part3_library())
    expected = {
        "PointFrom": ("5",),
        "PointLeftOpen": ("5",),
        "PointRightOpen": ("4",),
        "ProperIncludes": (True,),
        "ProperIncludesUncertain": (None,),
        "ProperIncludesStartPoint": (False,),
        "ProperIncludesEndPoint": (False,),
        "ProperIncludesUnitPoint": (False,),
        "ProperIncludedIn": (True,),
        "ProperIncludedInUncertain": (None,),
        "ProperIncludedStartPoint": (False,),
        "ProperIncludedEndPoint": (False,),
        "ProperIncludedUnitPoint": (False,),
        "SameAs": (True,),
        "SameAsDifferentEnd": (False,),
        "SameAfter": (True,),
        "SameAfterUncertain": (None,),
        "SameBefore": (True,),
        "SameBeforeUncertain": (None,),
        "SizeCheck": ("5",),
        "StartCheck": ("2024-01-01",),
        "StartsOpenEffective": (True,),
        "StartsLongerFalse": (False,),
        "StartsPrecision": (True,),
        "StartsPrecisionUncertain": (None,),
        "WidthCheck": ("4",),
        "UnionOpenLowContainsExcluded": (False,),
        "UnionOpenHighContainsExcluded": (False,),
        "DecimalOpenStart": ("1.00000001",),
        "DecimalOpenEnd": ("4.99999999",),
        "DecimalOpenWidth": ("3.99999999",),
        "DecimalClosedSize": ("4.00000001",),
        "DecimalOpenSize": ("4.0",),
        "DecimalOpenPointFrom": ("1.00000001",),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_result = py.execute(sql).fetchone()
                cpp_result = cpp.execute(sql).fetchone()
                no_py_result = no_py.execute(sql).fetchone()
                assert cpp_result == py_result, name
                assert no_py_result == py_result, name
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
        (
            "SELECT pointFrom(intervalFromBounds('4', '5', false, true))",
            [],
            ("5",),
        ),
        (
            "SELECT pointFrom(intervalFromBounds('4', '5', true, false))",
            [],
            ("4",),
        ),
        ("SELECT intervalWidth(?)", [numeric], ("4",)),
        (
            "SELECT intervalWidth(intervalFromBounds('4', '9', false, true))",
            [],
            ("4",),
        ),
        ("SELECT interval_size(?)", [numeric], ("5",)),
        (
            "SELECT intervalProperlyContains(intervalFromBounds('1', '5', true, true), '1')",
            [],
            (False,),
        ),
        (
            "SELECT intervalProperlyContains(intervalFromBounds('1', '5', true, true), '5')",
            [],
            (False,),
        ),
        (
            "SELECT intervalProperlyContains(intervalFromBounds('1', '1', true, true), '1')",
            [],
            (False,),
        ),
        ("SELECT intervalProperlyIncludes(?, ?)", [outer, inner], (True,)),
        ("SELECT intervalProperlyIncludedIn(?, ?)", [inner, outer], (True,)),
        ("SELECT intervalStartsSame(?, ?)", [starts, outer], (True,)),
        (
            "SELECT intervalStartsSame(intervalFromBounds('0', '5', false, true), intervalFromBounds('1', '5', true, true))",
            [],
            (True,),
        ),
        (
            "SELECT intervalStartsSame(intervalFromBounds('1', '10', true, true), intervalFromBounds('1', '5', true, true))",
            [],
            (False,),
        ),
        (
            "SELECT intervalEndsSame(intervalFromBounds('0', '5', true, true), intervalFromBounds('1', '5', true, true))",
            [],
            (False,),
        ),
        ("SELECT intervalUnion(?, ?) IS NOT NULL", [union_left, union_right], (True,)),
        (
            "SELECT intervalContains(intervalUnion(intervalFromBounds('0', '3', false, true), "
            "intervalFromBounds('1', '6', true, true)), '0')",
            [],
            (False,),
        ),
        (
            "SELECT intervalStart(intervalUnion(intervalFromBounds('0', '3', false, true), "
            "intervalFromBounds('1', '6', true, true)))",
            [],
            ("1",),
        ),
        (
            "SELECT intervalContains(intervalUnion(intervalFromBounds('1', '3', true, false), "
            "intervalFromBounds('1', '2', true, true)), '3')",
            [],
            (False,),
        ),
        (
            "SELECT intervalEnd(intervalUnion(intervalFromBounds('1', '3', true, false), "
            "intervalFromBounds('1', '2', true, true)))",
            [],
            ("2",),
        ),
        (
            "SELECT intervalStart(intervalFromBounds('1.0', '5.0', false, true))",
            [],
            ("1.00000001",),
        ),
        (
            "SELECT intervalEnd(intervalFromBounds('1.0', '5.0', true, false))",
            [],
            ("4.99999999",),
        ),
        (
            "SELECT intervalWidth(intervalFromBounds('1.0', '5.0', true, false))",
            [],
            ("3.99999999",),
        ),
        (
            "SELECT interval_size(intervalFromBounds('1.0', '5.0', true, true))",
            [],
            ("4.00000001",),
        ),
        (
            "SELECT interval_size(intervalFromBounds('1.0', '5.0', true, false))",
            [],
            ("4.0",),
        ),
        (
            "SELECT pointFrom(intervalFromBounds('1.0', '1.00000002', false, false))",
            [],
            ("1.00000001",),
        ),
        (
            "SELECT CAST(json_extract_string(intervalWidth(intervalFromBounds("
            "'{\"value\":1,\"unit\":\"g\"}', '{\"value\":2000,\"unit\":\"mg\"}', true, true)), "
            "'$.value') AS DOUBLE)",
            [],
            (1.0,),
        ),
        (
            "SELECT json_extract_string(intervalWidth(intervalFromBounds("
            "'{\"value\":1,\"unit\":\"g\"}', '{\"value\":2000,\"unit\":\"mg\"}', true, true)), "
            "'$.unit')",
            [],
            ("g",),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, params, expected in cases:
                assert py.execute(sql, params).fetchone() == expected
                assert cpp.execute(sql, params).fetchone() == expected
                assert no_py.execute(sql, params).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def _cql_interval_part3_library() -> str:
    return """library Interval3 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define PointFrom: point from Interval[5, 5]
define PointLeftOpen: point from Interval(4, 5]
define PointRightOpen: point from Interval[4, 5)
define ProperIncludes: Interval[@2024-01-01, @2024-01-31] properly includes day of Interval[@2024-01-05, @2024-01-10]
define ProperIncludesUncertain: Interval[@2024, @2024] properly includes day of Interval[@2024-01-01, @2024-01-01]
define ProperIncludesStartPoint: Interval[1, 5] properly includes 1
define ProperIncludesEndPoint: Interval[1, 5] properly includes 5
define ProperIncludesUnitPoint: Interval[1, 1] properly includes 1
define ProperIncludedIn: Interval[@2024-01-05, @2024-01-10] properly included in day of Interval[@2024-01-01, @2024-01-31]
define ProperIncludedInUncertain: Interval[@2024-01-01, @2024-01-01] properly included in day of Interval[@2024, @2024]
define ProperIncludedStartPoint: 1 properly included in Interval[1, 5]
define ProperIncludedEndPoint: 5 properly included in Interval[1, 5]
define ProperIncludedUnitPoint: 1 properly included in Interval[1, 1]
define SameAs: Interval[@2024-01-01, @2024-01-31] same day as Interval[@2024-01-01, @2024-01-31]
define SameAsDifferentEnd: Interval[@2024-01-01, @2024-01-10] same day as Interval[@2024-01-01, @2024-01-31]
define SameAfter: Interval[@2024-02-01, @2024-02-28] same or after day of Interval[@2024-01-01, @2024-01-31]
define SameAfterUncertain: Interval[@2024, @2024] same or after day of Interval[@2024-01-01, @2024-01-01]
define SameBefore: Interval[@2024-01-01, @2024-01-31] same or before day of Interval[@2024-02-01, @2024-02-28]
define SameBeforeUncertain: Interval[@2024, @2024] same or before day of Interval[@2024-01-01, @2024-01-01]
define SizeCheck: Size(Interval[1, 5])
define StartCheck: start of Interval[@2024-01-01, @2024-01-31]
define StartsOpenEffective: Interval(0, 5] starts Interval[1, 5]
define StartsLongerFalse: Interval[1, 10] starts Interval[1, 5]
define StartsPrecision: Interval[@2024-01-01, @2024-01-10] starts day of Interval[@2024-01-01, @2024-01-31]
define StartsPrecisionUncertain: Interval[@2024, @2024] starts day of Interval[@2024-01-01, @2024-01-31]
define UnionCheck: Interval[1, 3] union Interval[4, 6]
define WidthCheck: width of Interval[1, 5]
define UnionOpenLowContainsExcluded: 0 in (Interval(0, 3] union Interval[1, 6])
define UnionOpenHighContainsExcluded: 3 in (Interval[1, 3) union Interval[1, 2])
define DecimalOpenStart: start of Interval(1.0, 5.0]
define DecimalOpenEnd: end of Interval[1.0, 5.0)
define DecimalOpenWidth: width of Interval[1.0, 5.0)
define DecimalClosedSize: Size(Interval[1.0, 5.0])
define DecimalOpenSize: Size(Interval[1.0, 5.0))
define DecimalOpenPointFrom: point from Interval(1.0, 1.00000002)
"""
