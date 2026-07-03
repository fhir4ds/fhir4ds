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
        "ProperIncludedInTypedNull": (None,),
        "ProperIncludedInNullBounds": (True,),
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
        "StartClosedNullInteger": ("-2147483648",),
        "EndClosedNullInteger": ("2147483647",),
        "StartClosedNullDecimal": ("-99999999999999999999.99999999",),
        "EndClosedNullDecimal": ("99999999999999999999.99999999",),
        "StartOpenNullInteger": (None,),
        "EndOpenNullInteger": (None,),
        "StartClosedNullDate": ("0001-01-01",),
        "EndClosedNullDate": ("9999-12-31",),
        "StartClosedNullTime": ("T00:00:00.000",),
        "EndClosedNullTime": ("T23:59:59.999",),
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
        # CQL-17 SKEPTIC QA-001: Size(null as Interval<T>) must return null
        # per CQL §19.18 ("If the argument is null, the result is null"),
        # NOT 0 (which is the List Size semantics from §12.4).
        "SizeTypedNullInterval": (None,),
        # List Size of null list still returns 0 per CQL §12.4 (unchanged).
        "SizeTypedNullList": (0,),
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
            "SELECT intervalStart(intervalFromBounds('__null__', '5', true, true))",
            [],
            ("-2147483648",),
        ),
        (
            "SELECT intervalEnd(intervalFromBounds('5', '__null__', true, true))",
            [],
            ("2147483647",),
        ),
        (
            "SELECT intervalStart(intervalFromBounds('__null__', '5.0', true, true))",
            [],
            ("-99999999999999999999.99999999",),
        ),
        (
            "SELECT intervalEnd(intervalFromBounds('5.0', '__null__', true, true))",
            [],
            ("99999999999999999999.99999999",),
        ),
        (
            "SELECT intervalStart(intervalFromBounds('__null__', '5', false, true))",
            [],
            (None,),
        ),
        (
            "SELECT intervalEnd(intervalFromBounds('5', '__null__', true, false))",
            [],
            (None,),
        ),
        (
            "SELECT intervalStart(intervalFromBounds('__null__', '2024-01-01', true, true))",
            [],
            ("0001-01-01",),
        ),
        (
            "SELECT intervalEnd(intervalFromBounds('2024-01-01', '__null__', true, true))",
            [],
            ("9999-12-31",),
        ),
        (
            "SELECT intervalStart(intervalFromBounds('__null__', 'T12', true, true))",
            [],
            ("T00:00:00.000",),
        ),
        (
            "SELECT intervalEnd(intervalFromBounds('T12', '__null__', true, true))",
            [],
            ("T23:59:59.999",),
        ),
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
        (
            "SELECT intervalProperlyIncludedIn(?, CAST(NULL AS VARCHAR))",
            [numeric],
            (None,),
        ),
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
        (
            "SELECT expand([intervalFromBounds('1', '3', true, true)], "
            "'{\"value\":\"bad\",\"unit\":\"1\"}')",
            [],
            (None,),
        ),
        (
            "SELECT expand([intervalUnion(intervalFromBounds('1', '2', true, true), "
            "intervalFromBounds('3', '4', true, true))], "
            "'{\"value\":\"bad\",\"unit\":\"1\"}')",
            [],
            (None,),
        ),
        (
            "SELECT expand_points(intervalFromBounds('1', '3', true, true), "
            "'{\"value\":\"bad\",\"unit\":\"1\"}')",
            [],
            (None,),
        ),
        (
            "SELECT expand([intervalFromBounds('1', '3', true, true)], CAST(NULL AS VARCHAR))",
            [],
            (
                '[{"low":1,"high":1,"lowClosed":true,"highClosed":true},'
                '{"low":2,"high":2,"lowClosed":true,"highClosed":true},'
                '{"low":3,"high":3,"lowClosed":true,"highClosed":true}]',
            ),
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
define ProperIncludedInTypedNull: Interval[1, 5] properly included in (null as Interval<Integer>)
define ProperIncludedInNullBounds: Interval[1, 5] properly included in Interval[null, null]
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
define StartClosedNullInteger: start of Interval[null as Integer, 5]
define EndClosedNullInteger: end of Interval[5, null as Integer]
define StartClosedNullDecimal: start of Interval[null as Decimal, 5.0]
define EndClosedNullDecimal: end of Interval[5.0, null as Decimal]
define StartOpenNullInteger: start of Interval(null as Integer, 5]
define EndOpenNullInteger: end of Interval[5, null as Integer)
define StartClosedNullDate: start of Interval[null as Date, @2024-01-01]
define EndClosedNullDate: end of Interval[@2024-01-01, null as Date]
define StartClosedNullTime: start of Interval[null as Time, @T12]
define EndClosedNullTime: end of Interval[@T12, null as Time]
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
define SizeTypedNullInterval: Size(null as Interval<Integer>)
define SizeTypedNullList: Size(null as List<Integer>)
"""


def test_cql_interval_part3_historian_size_temporal_raises_per_spec() -> None:
    """CQL-17 HISTORIAN regression: Size must raise on Date/DateTime/Time.

    Spec: CQL v1.5.3 §19.18 Size cross-references §19.25 Width which says
    "this operator is not defined" for date/time intervals. Both backends
    must raise InvalidInputException to preserve backend parity.

    Previously C++ silently returned null while Python raised ValueError.
    """
    import pytest  # local import to avoid module-level dep

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql in [
            "SELECT interval_size('{\"low\":\"2024-01-01\",\"high\":\"2024-12-31\","
            "\"lowClosed\":true,\"highClosed\":true}')",
            "SELECT interval_size('{\"low\":\"2024-01-01T00:00:00\","
            "\"high\":\"2024-12-31T23:59:59\",\"lowClosed\":true,\"highClosed\":true}')",
            "SELECT interval_size('{\"low\":\"T00:00:00\",\"high\":\"T23:59:59\","
            "\"lowClosed\":true,\"highClosed\":true}')",
        ]:
            with pytest.raises(Exception):
                py.execute(sql).fetchone()
            with pytest.raises(Exception):
                cpp.execute(sql).fetchone()
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part3_historian_size_quantity_includes_system_per_spec() -> None:
    """CQL-17 HISTORIAN regression: Size on Quantity intervals must include
    the UCUM ``system`` field on both backends.

    Previously Python omitted ``"system":"http://unitsofmeasure.org"`` while
    C++ included it, producing divergent JSON shapes for the same Size call.
    """
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        sql = (
            "SELECT interval_size(intervalFromBounds("
            "'{\"value\":1.0,\"unit\":\"g\"}', "
            "'{\"value\":5.0,\"unit\":\"g\"}', true, true))"
        )
        py_r = py.execute(sql).fetchone()[0]
        cpp_r = cpp.execute(sql).fetchone()[0]

        # Parse both JSON strings to compare semantically.
        import json as _json
        py_obj = _json.loads(py_r)
        cpp_obj = _json.loads(cpp_r)
        assert py_obj.get("system") == "http://unitsofmeasure.org", py_obj
        assert cpp_obj.get("system") == "http://unitsofmeasure.org", cpp_obj
        assert py_obj.get("value") == cpp_obj.get("value")
        assert py_obj.get("unit") == cpp_obj.get("unit")
        assert py_obj.get("code") == cpp_obj.get("code")
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part3_explorer_pointfrom_time_returns_time_string_per_spec() -> None:
    """CQL-17 EXPLORER regression: ``point from Interval[@T..., @T...]`` must
    return a Time-formatted string (``'T12:30:00'``), NOT a raw
    millisecond-since-midnight integer (``'45000000'``).

    Spec: CQL v1.5.3 §19.22 Point From: "If the argument is a unit interval,
    the operator returns the point value." For a Time-typed interval the
    point value is a Time, not an int.

    Previously the Python UDF ``pointFrom`` at
    ``fhir4ds/cql/duckdb/udf/interval.py:775-802`` parsed Time bounds to
    integer ms via ``_parse_interval_bound:366`` and then formatted via
    ``_format_adjusted_bound_for_raw`` which has no Time-string
    round-trip path, returning the int as-is via ``str(formatted)``. The
    C++ extension used ``start_string()`` / ``end_string()`` which
    preserve raw lexical forms, returning the correct Time string. The
    WASM/browser runtime (which uses only C++ UDFs) was correct; the
    Python runtime (conformance suite, batch CLI) returned raw ints.
    """
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            cases = [
                '{"low":"T00:00:00","high":"T00:00:00","lowClosed":true,"highClosed":true}',
                '{"low":"T12:30:00","high":"T12:30:00","lowClosed":true,"highClosed":true}',
                '{"low":"T23:59:59.999","high":"T23:59:59.999","lowClosed":true,"highClosed":true}',
                '{"low":"T05:00","high":"T05:00","lowClosed":true,"highClosed":true}',
            ]
            for raw_iv in cases:
                sql = "SELECT pointFrom(?)"
                py_r = py.execute(sql, [raw_iv]).fetchone()
                cpp_r = cpp.execute(sql, [raw_iv]).fetchone()
                no_py_r = no_py.execute(sql, [raw_iv]).fetchone()
                # All three backends must agree.
                assert py_r == cpp_r == no_py_r, (
                    f"pointFrom divergence on {raw_iv}: "
                    f"py={py_r} cpp={cpp_r} no_py={no_py_r}"
                )
                # Result must be a Time string, not a raw int.
                result = py_r[0]
                assert isinstance(result, str) and (
                    result.startswith("T") or ":" in result
                ), f"pointFrom({raw_iv}) returned non-Time result {result!r}"
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part3_explorer_long_minmax_width_size_exact_per_spec() -> None:
    """CQL-17 EXPLORER regression: Width/Size of Long MIN..MAX interval must
    return exact integer values, not float approximations.

    Spec: CQL v1.5.3 §19.25 Width / §19.18 Size on Integer/Long intervals
    return the same type as the point type (Integer/Long). For
    ``Interval[-9223372036854775808L, 9223372036854775807L]``:
      - Width = ``9223372036854775807 - (-9223372036854775808) = 2^64 - 1``
      - Size  = ``Width + 1 = 2^64``

    Previously the C++ extension classified Long MIN..MAX bounds as Decimal
    (the cutoff `d <= 9.22e18` was too narrow; INT64_MAX ~ 9.223372036854776e18
    exceeds it). The bound was then stored as double, lost precision in
    width/size arithmetic, and returned ``"18446744073709551616.0"`` (off by
    one for width). The WASM/browser runtime (C++ only) produced the wrong
    value; the Python runtime (Python UDF supplements) produced the correct
    value, masking the bug from conformance.
    """
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            raw_iv = (
                '{"low":"-9223372036854775808","high":"9223372036854775807",'
                '"lowClosed":true,"highClosed":true}'
            )
            # Width = 2^64 - 1
            expected_width = "18446744073709551615"
            # Size = 2^64
            expected_size = "18446744073709551616"

            for sql, expected in [
                ("SELECT intervalWidth(?)", expected_width),
                ("SELECT interval_size(?)", expected_size),
            ]:
                py_r = py.execute(sql, [raw_iv]).fetchone()
                cpp_r = cpp.execute(sql, [raw_iv]).fetchone()
                no_py_r = no_py.execute(sql, [raw_iv]).fetchone()
                # All three must agree on the integer-formatted string.
                assert py_r == cpp_r == no_py_r, (
                    f"divergence on {sql}: py={py_r} cpp={cpp_r} no_py={no_py_r}"
                )
                # Result must be the exact expected integer (no .0 suffix).
                assert py_r[0] == expected, (
                    f"{sql} returned {py_r[0]!r}, expected {expected!r}"
                )
    finally:
        py.close()
        cpp.close()
