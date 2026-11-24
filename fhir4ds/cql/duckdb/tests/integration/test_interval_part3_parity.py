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
        # CQL-17 SKEPTIC QA-001: §19.31 Union (Interval) — either argument
        # null → null. Typed-null interval operands must NOT fall into
        # list-union semantics (jsonConcat / []).
        "UnionNullLeft": (None,),
        "UnionNullRight2": (None,),
        "UnionNullBoth": (None,),
        # CQL-17 SKEPTIC QA-002: Start/End of a Quantity interval returns the
        # Quantity point as valid JSON (not a Python dict repr).
        # CQL-17 HISTORIAN QA-004 (2nd launch): the JSON is the canonical
        # Quantity shape with code+system, matching Width/Size output.
        "StartOfQty": (
            '{"value":1.0,"unit":"g","code":"g","system":"http://unitsofmeasure.org"}',
        ),
        "EndOfQty": (
            '{"value":3.0,"unit":"g","code":"g","system":"http://unitsofmeasure.org"}',
        ),
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
        # CQL-17 SKEPTIC QA-003: intervalWidth Quantity output includes the
        # UCUM system field, matching interval_size and the native extension.
        (
            "SELECT json_extract_string(intervalWidth(intervalFromBounds("
            "'{\"value\":1,\"unit\":\"g\"}', '{\"value\":2000,\"unit\":\"mg\"}', true, true)), "
            "'$.system')",
            [],
            ("http://unitsofmeasure.org",),
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
define UnionNullLeft: (null as Interval<Integer>) union Interval[1, 5]
define UnionNullRight2: Interval[1, 5] union (null as Interval<Integer>)
define UnionNullBoth: (null as Interval<Integer>) union (null as Interval<Date>)
define StartOfQty: start of Interval[1 'g', 3 'g']
define EndOfQty: end of Interval[1 'g', 3 'g']
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


def test_cql_interval_part3_historian2_numeric_same_family_per_spec() -> None:
    """CQL-17 HISTORIAN (2nd launch) regression: no-precision interval
    ``same as`` / ``same or after`` / ``same or before`` with numeric
    (Integer/Decimal, incl. mixed) and Quantity point types.

    Spec: CQL v1.5.3 §19.27/§19.28/§19.29 apply to any interval point type;
    boundary comparisons use the point-type comparison semantics (§9).

    Previously the translator unconditionally lowered these to the temporal
    UDFs (cqlDateTimeEqual / cqlSameOrAfter / cqlSameOrBefore): Decimal
    bounds raised ValueError on the Python path (int('1.0')) and returned
    NULL on native. Integer intervals only worked by accident of the
    datetime parser reading '1' as year 1.
    """
    library = """library H2a version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DecSameAs: Interval[1.0, 5.0] same as Interval[1.00, 5.0]
define DecSameAsFalse: Interval[1.0, 5.0] same as Interval[1.0, 5.5]
define MixedSameAs: Interval[1, 5.5] same as Interval[1.0, 5.5]
define IntSameAs: Interval[1, 5] same as Interval[1, 5]
define DecSameOrAfter: Interval[3.0, 5.0] same or after Interval[1.0, 2.0]
define DecSameOrAfterFalse: Interval[1.0, 2.0] same or after Interval[3.0, 5.0]
define DecSameOrBefore: Interval[1.0, 2.0] same or before Interval[3.0, 5.0]
define IntSameOrAfter: Interval[3, 5] same or after Interval[1, 2]
define QtySameAs: Interval[1 'g', 2 'g'] same as Interval[1 'g', 2 'g']
define QtySameOrAfter: Interval[3 'g', 5 'g'] same or after Interval[1 'g', 2 'g']
define SameAsNull: Interval[1, 5] same as (null as Interval<Integer>)
define SameOrAfterNull: (null as Interval<Integer>) same or after Interval[1, 5]
define DateSameAsStillTemporal: Interval[@2024-01-01, @2024-01-31] same as Interval[@2024-01-01, @2024-01-31]
define DateSameAsFalseStillTemporal: Interval[@2024-01-01, @2024-01-10] same as Interval[@2024-01-01, @2024-01-31]
"""
    expected = {
        "DecSameAs": (True,),
        "DecSameAsFalse": (False,),
        "MixedSameAs": (True,),
        "IntSameAs": (True,),
        "DecSameOrAfter": (True,),
        "DecSameOrAfterFalse": (False,),
        "DecSameOrBefore": (True,),
        "IntSameOrAfter": (True,),
        "QtySameAs": (True,),
        "QtySameOrAfter": (True,),
        "SameAsNull": (None,),
        "SameOrAfterNull": (None,),
        "DateSameAsStillTemporal": (True,),
        "DateSameAsFalseStillTemporal": (False,),
    }
    translated = translate_cql(library)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, exp in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                py_r = py.execute(sql).fetchone()
                cpp_r = cpp.execute(sql).fetchone()
                no_py_r = no_py.execute(sql).fetchone()
                assert py_r == cpp_r == no_py_r, (name, py_r, cpp_r, no_py_r)
                assert py_r == exp, (name, py_r, exp)
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part3_historian2_mixed_width_size_per_spec() -> None:
    """CQL-17 HISTORIAN (2nd launch) regression: Width/Size of intervals with
    mixed Integer/Decimal bounds (CQL §2 implicit Integer->Decimal
    conversion) must compute numerically on ALL engines.

    Spec: CQL v1.5.3 §19.25 Width / §19.18 Size with §2 implicit
    conversions. Previously the native extension returned NULL: the
    width_string/size_string switch keyed on the LOW bound's type and
    required BOTH bounds of that numeric type.
    """
    library = """library H2b version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MixedWidth: width of Interval[1, 5.5]
define MixedSize: Size(Interval[1, 5.5])
define MixedWidthDecimalLow: width of Interval[1.0, 6]
define MixedSizeDecimalLow: Size(Interval[1.0, 6])
"""
    expected = {
        "MixedWidth": ("4.5",),
        "MixedSize": ("4.50000001",),
        "MixedWidthDecimalLow": ("5.0",),
        "MixedSizeDecimalLow": ("5.00000001",),
    }
    translated = translate_cql(library)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, exp in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                py_r = py.execute(sql).fetchone()
                cpp_r = cpp.execute(sql).fetchone()
                no_py_r = no_py.execute(sql).fetchone()
                assert py_r == cpp_r == no_py_r, (name, py_r, cpp_r, no_py_r)
                assert py_r == exp, (name, py_r, exp)
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part3_historian2_quantity_bound_json_canonical() -> None:
    """CQL-17 HISTORIAN (2nd launch) regression: start of/end of/point from
    on Quantity intervals emit the canonical Quantity JSON shape
    (value/unit/code/system), matching Width/Size output on all engines.
    """
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql in [
                "SELECT intervalStart(intervalFromBounds("
                "'{\"value\":1,\"unit\":\"g\"}', '{\"value\":3,\"unit\":\"g\"}', true, true))",
                "SELECT intervalEnd(intervalFromBounds("
                "'{\"value\":1,\"unit\":\"g\"}', '{\"value\":3,\"unit\":\"g\"}', true, true))",
                "SELECT pointFrom(intervalFromBounds("
                "'{\"value\":4,\"unit\":\"g\"}', '{\"value\":4,\"unit\":\"g\"}', true, true))",
            ]:
                py_r = py.execute(sql).fetchone()
                cpp_r = cpp.execute(sql).fetchone()
                no_py_r = no_py.execute(sql).fetchone()
                assert py_r == cpp_r == no_py_r, (sql, py_r, cpp_r, no_py_r)
                import json as _json

                obj = _json.loads(py_r[0])
                assert obj.get("system") == "http://unitsofmeasure.org", obj
                assert obj.get("code") == obj.get("unit") == "g", obj
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part3_explorer3_interval_scalar_arithmetic_numeric_quantity() -> None:
    """CQL-17 EXPLORER (3rd launch) regression: arithmetic over interval-derived
    scalars (start of / end of / point from / width of / Size) must follow the
    interval's point type.

    Spec: CQL v1.5.3 §19.19 Start (and §19.15 End, §19.22 Point From,
    §19.25 Width, §19.18 Size) return the interval's point type, so
    ``(start of Interval[1, 5]) + 1`` is Integer addition (§9 Add), and
    Quantity interval scalars use Quantity arithmetic.

    Previously the Integer-literal case lowered to dateAddQuantity(...,
    1 'year') (NULL for numeric points) and the decimal/width cases fell
    through to raw SQL '+'(VARCHAR, x) binder errors.
    """
    library = """library E3 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StartPlusOne: (start of Interval[1, 5]) + 1
define EndMinusOne: (end of Interval[1, 5]) - 1
define DecStartPlus: (start of Interval[1.5, 5]) + 1
define WidthPlusOne: (width of Interval[1, 5]) + 1
define SizeTimesTwo: Size(Interval[1, 5]) * 2
define PointFromPlus: (point from Interval[4, 4]) + 1
define SentinelStartPlusOne: (start of Interval[null as Integer, 5]) + 1
define ReversedPlus: 1 + (end of Interval[1, 5])
define QtyStartPlus: (start of Interval[1 'g', 3 'g']) + 1 'g'
define QtyWidthMinus: (width of Interval[1 'g', 3 'g']) - 1 'g'
define QtyEndDiv: (end of Interval[1 'g', 3 'g']) / 2
define DateStartPlusDay: (start of Interval[@2024-01-01, @2024-02-01]) + 1 day
"""
    translated = translate_cql(library)

    def _num(value):
        return None if value is None else float(value)

    cases = [
        # (define, expected-python-value, expected-native-value)
        ("StartPlusOne", 2, 2),
        ("EndMinusOne", 4, 4),
        ("DecStartPlus", 2.5, 2.5),
        ("WidthPlusOne", 5, 5),
        ("SizeTimesTwo", 10, 10),
        ("PointFromPlus", 5, 5),
        ("SentinelStartPlusOne", -2147483647, -2147483647),
        ("ReversedPlus", 6, 6),
        ("QtyStartPlus", '{"value":2.0,"unit":"g","code":"g","system":"http://unitsofmeasure.org"}', None),
        ("QtyWidthMinus", '{"value":1.0,"unit":"g","code":"g","system":"http://unitsofmeasure.org"}', None),
        ("QtyEndDiv", '{"value":1.5,"code":"g","system":"http://unitsofmeasure.org","unit":"g"}', None),
        ("DateStartPlusDay", "2024-01-02", "2024-01-02"),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expected_py, expected_cpp in cases:
                sql = f"SELECT {translated[name].to_sql()}"
                py_r = py.execute(sql).fetchone()[0]
                cpp_r = cpp.execute(sql).fetchone()[0]
                no_py_r = no_py.execute(sql).fetchone()[0]
                if expected_py is not None:
                    if isinstance(expected_py, (int, float)) and not isinstance(expected_py, bool):
                        assert _num(py_r) == expected_py, (name, py_r)
                    elif expected_py.startswith("{"):
                        import json as _json
                        assert _json.loads(py_r) == _json.loads(expected_py), (name, py_r)
                    else:
                        assert py_r == expected_py, (name, py_r)
                if expected_cpp is not None:
                    if isinstance(expected_cpp, (int, float)) and not isinstance(expected_cpp, bool):
                        assert _num(cpp_r) == expected_cpp, (name, cpp_r)
                        assert _num(no_py_r) == expected_cpp, (name, no_py_r)
                    else:
                        assert cpp_r == expected_cpp, (name, cpp_r)
                        assert no_py_r == expected_cpp, (name, no_py_r)
    finally:
        py.close()
        cpp.close()


def test_cql_interval_point_properly_includes_authored_bound_amux168() -> None:
    """AMUX-168: interval-point ``properly includes`` must compare the point
    against the AUTHORED interval bound, not the successor-normalized
    effective bound.

    Spec (cql.hl7.org 09-b, #properly-includes): "For the interval-point
    overload, this operator returns true if the interval contains (i.e.
    includes) the point, and the interval is not a unit interval containing
    only the point."  Reference implementation confirmation: cqframework
    ``ProperContainsEvaluator.properContains(Interval, BaseTemporal)``
    evaluates ``After(point, start) && Before(point, end)`` against the
    AUTHORED bounds.

    ``Interval(1, 5]`` contains 2 (its successor-normalized start), so the
    point is strictly inside the authored interval: true.  The Python
    fallback normalized the open bound to a CLOSED effective bound at
    ``_parse_interval`` and then kept the closed-boundary strict comparison,
    so every open-bound effective-start/end point returned false while the
    native engine returned true.

    Related root cause in the same normalization: a Time bound is stored as
    integer milliseconds, so ``_parse_interval`` stepped it through the
    plain-INTEGER branch and emitted the raw millisecond count as the
    effective bound -- ``start of Interval(@T12:00:00.000, ...)`` returned
    ``'43200001'`` instead of ``'T12:00:00.001'``.

    The pinned CLOSED-boundary strictness is unchanged (and is asserted here
    so a future "fix" cannot silently flip it): cql-tests ``version="1.0"``
    fixtures ``TimeProperContainsFalse`` / ``TimeProperInFalse`` (in
    ``fhir4ds/cql/tests/official/cql-tests/tests/cql/CqlIntervalOperatorsTest.xml``)
    require FALSE for a point equal to a CLOSED start boundary, and the
    conformance referee depends on it.  cql-tests PR #159 flips those two
    fixtures to true with no CQL-version distinction (the prose is identical
    in 1.5.3 and 2.0.0), so that adjudication is deliberately NOT applied
    here -- see the NOT A BUG registry entry in extensions/cql/AGENTS.md.
    """
    lib = """library IntervalPointProperlyIncludes168 version '1.0.0'
using FHIR version '4.0.1'
context Patient
// closed bounds: strict (fixture-pinned) -- unchanged
define ClosedStartPoint: Interval[@T12:00:00.000, @T21:59:59.999] properly includes @T12:00:00.000
define ClosedStartInPoint: @T12:00:00.000 properly included in Interval[@T12:00:00.000, @T21:59:59.999]
define IntClosedStart: Interval[1, 5] properly includes 1
define IntClosedEnd: Interval[1, 5] properly includes 5
define IntUnitPoint: Interval[1, 1] properly includes 1
define IntInterior: Interval[1, 5] properly includes 3
// open bounds: strict against the AUTHORED bound, so the effective boundary
// point is inside -> true; the authored boundary point stays outside -> false
define IntOpenLowEffectiveStart: Interval(1, 5] properly includes 2
define IntOpenLowAuthoredBoundary: Interval(1, 5] properly includes 1
define IntOpenHighEffectiveEnd: Interval[1, 5) properly includes 4
define IntOpenHighAuthoredBoundary: Interval[1, 5) properly includes 5
define IntOpenBothEffectiveStart: Interval(1, 5) properly includes 2
define IntOpenBothEffectiveEnd: Interval(1, 5) properly includes 4
define DecimalOpenLowEffectiveStart: Interval(1.0, 5.0] properly includes 1.00000001
define DecimalOpenHighEffectiveEnd: Interval[1.0, 5.0) properly includes 4.99999999
define DateOpenLowEffectiveStart: Interval(@2024-01-01, @2025-01-01) properly includes @2024-01-02
define DateOpenHighEffectiveEnd: Interval[@2024-01-01, @2025-01-01) properly includes @2024-12-31
define TimeOpenLowEffectiveStart: Interval(@T12:00:00.000, @T18:00:00.000) properly includes @T12:00:00.001
define TimeOpenLowAuthoredBoundary: Interval(@T12:00:00.000, @T18:00:00.000) properly includes @T12:00:00.000
define DateTimeOpenLowEffectiveStart: Interval(@2024-01-01T00:00:00.000, @2024-02-01T00:00:00.000) properly includes @2024-01-01T00:00:00.001
define QuantityOpenLowEffectiveStart: Interval(1 'g', 5 'g'] properly includes 1.00000001 'g'
// mirror direction (point properly included in interval) uses the same UDF
define MirrorOpenLowEffectiveStart: 2 properly included in Interval(1, 5]
define MirrorClosedStart: 1 properly included in Interval[1, 5]
define MirrorOpenLowAuthoredBoundary: 1 properly included in Interval(1, 5]
// an OPEN null bound is an UNKNOWN boundary (Start/End are null) -> null
define OpenNullLowUncertain: Interval(null as Integer, 5] properly includes 3
// open Time bounds must render as Time strings at the authored precision
define TimeOpenStart: start of Interval(@T12:00:00.000, @T18:00:00.000)
define TimeOpenEnd: end of Interval(@T12:00:00.000, @T18:00:00.000)
define TimeOpenStartHourPrecision: start of Interval(@T12, @T18)
define TimeOpenEndHourPrecision: end of Interval(@T12, @T18)
define TimeOpenStartMinutePrecision: start of Interval(@T12:30, @T18:30)
define TimeOpenEndMinutePrecision: end of Interval(@T12:30, @T18:30)
define TimeOpenStartSecondPrecision: start of Interval(@T12:00:00, @T18:00:00)
define TimeOpenEndSecondPrecision: end of Interval(@T12:00:00, @T18:00:00)
"""
    expected = {
        # fixture-pinned closed-boundary strictness (unchanged)
        "ClosedStartPoint": False,
        "ClosedStartInPoint": False,
        "IntClosedStart": False,
        "IntClosedEnd": False,
        "IntUnitPoint": False,
        "IntInterior": True,
        # open bounds compare strictly against the authored bound
        "IntOpenLowEffectiveStart": True,
        "IntOpenLowAuthoredBoundary": False,
        "IntOpenHighEffectiveEnd": True,
        "IntOpenHighAuthoredBoundary": False,
        "IntOpenBothEffectiveStart": True,
        "IntOpenBothEffectiveEnd": True,
        "DecimalOpenLowEffectiveStart": True,
        "DecimalOpenHighEffectiveEnd": True,
        "DateOpenLowEffectiveStart": True,
        "DateOpenHighEffectiveEnd": True,
        "TimeOpenLowEffectiveStart": True,
        "TimeOpenLowAuthoredBoundary": False,
        "DateTimeOpenLowEffectiveStart": True,
        "QuantityOpenLowEffectiveStart": True,
        "MirrorOpenLowEffectiveStart": True,
        "MirrorClosedStart": False,
        "MirrorOpenLowAuthoredBoundary": False,
        # open null bound -> uncertain
        "OpenNullLowUncertain": None,
        # open Time bounds render at the authored precision
        "TimeOpenStart": "T12:00:00.001",
        "TimeOpenEnd": "T17:59:59.999",
        "TimeOpenStartHourPrecision": "T13",
        "TimeOpenEndHourPrecision": "T17",
        "TimeOpenStartMinutePrecision": "T12:31",
        "TimeOpenEndMinutePrecision": "T18:29",
        "TimeOpenStartSecondPrecision": "T12:00:01",
        "TimeOpenEndSecondPrecision": "T17:59:59",
    }

    translated = translate_cql(lib)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_result = py.execute(sql).fetchone()
                cpp_result = cpp.execute(sql).fetchone()
                no_py_result = no_py.execute(sql).fetchone()
                assert no_py_result == py_result, (
                    f"{name}: python fallback {py_result} != native {no_py_result}"
                )
                assert cpp_result == py_result, f"{name}: cpp {cpp_result} != python {py_result}"
                assert py_result == (expected[name],), (
                    f"{name}: got {py_result}, expected {(expected[name],)}"
                )
    finally:
        py.close()
        cpp.close()


# ---------------------------------------------------------------------------
# FHIR4-38 — starts/ends against a CLOSED null bound (point-type sentinel)
#
# CQL 1.5 §9.14 Start / §9.15 End: "If the low [high] boundary is null and the
# boundary is closed, the result is the minimum [maximum] value of the point
# type." Starts (§19.30) and Ends (§19.13) are defined through Start/End, so a
# CLOSED null bound is the point-type EXTREME (a DEFINITE value), never unknown:
#
#   Interval[null, null] starts Interval[1, 10]   // false  (min Integer < 1)
#   Interval[1, 10] ends Interval[null, null]     // false  (max Integer > 10)
#
# The point type is Interval<T> — shared by both operands — so it is inferred
# from the PEER interval when the operand's own opposite bound is also null
# (the same peer-inference doctrine as the CQL-16 HISTORIAN
# `_cql_minimum_for_peer_bound` / `_cql_maximum_for_peer_bound` sentinels).
#
# An OPEN null bound stays UNKNOWN (Interval(null, null) is the unknown
# boundary form) and must keep returning null — fixtures
# TestUnknownIntervalStartsNull / TestUnknownIntervalEndsNull.
#
# Official fixtures pinning the closed-null cases:
#   CqlIntervalOperatorsTest.xml::TestMaxIntervalStartsFalse  -> false
#   CqlIntervalOperatorsTest.xml::TestMaxIntervalEndsFalse    -> false
# ---------------------------------------------------------------------------

_INTERVAL_PART3_CLOSED_NULL_LIBRARY = """library ClosedNullStartsEnds version '1.0'
using FHIR version '4.0.1'
context Patient

// Closed null bounds -> point-type sentinel -> DEFINITE results.
define MaxStartsFalse: Interval[null, null] starts Interval[1, 10]
define MaxEndsFalse: Interval[1, 10] ends Interval[null, null]
define MaxStartsDateFalse: Interval[null, null] starts Interval[@2024-01-01, @2024-12-31]
define MaxEndsDateFalse: Interval[@2024-01-01, @2024-12-31] ends Interval[null, null]
define MaxStartsQuantityFalse: Interval[null, 5.0 'g'] starts Interval[1.0 'g', 10.0 'g']
// Positive controls: the sentinel really resolves to the peer extreme.
define LowNullStartsSentinelEqualTrue: Interval[null, 5] starts Interval[-2147483648, 10]
define HighNullStartsSentinelEqualTrue: Interval[1, null] starts Interval[1, null]
define HighNullEndsSentinelEqualTrue: Interval[1, null] ends Interval[1, null]
define HighNullStartsLongerFalse: Interval[1, null] starts Interval[1, 10]
define UninferrablePointTypeNull: Interval[null, null] starts Interval[null, null]
// Open null bounds stay UNKNOWN (null) — unchanged by this fix.
define UnknownStartsNull: Interval(null, null) starts Interval[1, 10]
define UnknownEndsNull: Interval[1, 10] ends Interval(null, null)
define UnknownLowStartsNull: Interval(null, 5] starts Interval[1, 10]
define UnknownHighEndsNull: Interval[1, null) ends Interval[1, 10]
define NullScalarStartsNull: null starts Interval[1, 10]
define NullScalarEndsNull: Interval[1, 10] ends null
// Non-null controls (official fixture truth table, unchanged).
define IntegerStartsTrue: Interval[4, 10] starts Interval[4, 15]
define IntegerStartsFalse: Interval[1, 10] starts Interval[4, 10]
define IntegerEndsTrue: Interval[4, 10] ends Interval[1, 10]
define IntegerEndsFalse: Interval[44, 50] ends Interval[1, 10]
define DecimalStartsTrue: Interval[4.0, 10.0] starts Interval[4.0, 15.0]
define QuantityEndsTrue: Interval[5.0 'g', 10.0 'g'] ends Interval[1.0 'g', 10.0 'g']
define DateTimeStartsTrue: Interval[DateTime(2012, 1, 5), DateTime(2012, 1, 25)] starts Interval[DateTime(2012, 1, 5), DateTime(2012, 1, 27)]
define TimeEndsFalse: Interval[@T05:59:59.999, @T10:59:59.999] ends Interval[@T01:59:59.999, @T11:59:59.999]
// Precision-qualified variants. NOT part of the FHIR4-38 fix: the precision
// form lowers to cqlSameAsP(cqlSameOrBeforeP)(intervalStart(...),
// intervalStart(...), precision), and intervalStart cannot infer a point type
// from a single all-null interval, so the closed-null bound is unknown at that
// seam (same behaviour for a NON-null Integer interval, e.g.
// Interval[1, 10] starts day of Interval[1, 15] -> null, because the precision
// qualifier is only defined for Date/DateTime/Time point types). Resolving it
// needs a peer-aware Start/End arity that the bundled C++ surface does not
// implement; pinned here so the gap is visible rather than silent.
define MaxStartsPrecisionGapNull: Interval[null, null] starts day of Interval[1, 10]
define MaxEndsPrecisionGapNull: Interval[1, 10] ends day of Interval[null, null]
"""


def test_cql_interval_part3_closed_null_bound_starts_ends_fhir4_38() -> None:
    """FHIR4-38: starts/ends resolve a CLOSED null bound to the point extreme.

    CQL 1.5 §9.14/§9.15 (Start/End of a closed null boundary is the point-type
    extremum) applied to §19.30 Starts / §19.13 Ends. Official fixtures
    TestMaxIntervalStartsFalse / TestMaxIntervalEndsFalse pin the two headline
    cells at FALSE, not null; the OPEN form keeps returning null
    (TestUnknownIntervalStartsNull / TestUnknownIntervalEndsNull).
    """
    expected = {
        # Closed null bounds -> sentinel -> definite result.
        "MaxStartsFalse": False,
        "MaxEndsFalse": False,
        "MaxStartsDateFalse": False,
        "MaxEndsDateFalse": False,
        "MaxStartsQuantityFalse": False,
        # The sentinel is the peer extreme, so the comparison can be TRUE.
        "LowNullStartsSentinelEqualTrue": True,
        "HighNullStartsSentinelEqualTrue": True,
        "HighNullEndsSentinelEqualTrue": True,
        "HighNullStartsLongerFalse": False,
        # Point type uninferrable on both sides (Interval<Any>) -> null.
        "UninferrablePointTypeNull": None,
        # Open null bounds remain unknown (CQL §2: open = unknown boundary).
        "UnknownStartsNull": None,
        "UnknownEndsNull": None,
        "UnknownLowStartsNull": None,
        "UnknownHighEndsNull": None,
        "NullScalarStartsNull": None,
        "NullScalarEndsNull": None,
        # Non-null controls (official fixture truth table).
        "IntegerStartsTrue": True,
        "IntegerStartsFalse": False,
        "IntegerEndsTrue": True,
        "IntegerEndsFalse": False,
        "DecimalStartsTrue": True,
        "QuantityEndsTrue": True,
        "DateTimeStartsTrue": True,
        "TimeEndsFalse": False,
        # Precision-qualified gap (see the library comment).
        "MaxStartsPrecisionGapNull": None,
        "MaxEndsPrecisionGapNull": None,
    }

    # REBUILD REQUIRED (no-Python / browser surface): the bundled
    # cql.duckdb_extension still carries the pre-FHIR4-38 C++ sentinel tables,
    # whose IntervalStartsSameFunc / IntervalEndsSameFunc wrappers reject ANY
    # interval with a null bound -> NULL. The Python UDFs are the desktop
    # conformance authority (both `intervalStartsSame` and `intervalEndsSame`
    # are in _PYTHON_PREFERRED_CPP_CONFLICTS), so py and cpp agree above.
    # The C++ source (extensions/cql/src/cql/interval.cpp: peer-aware
    # sentinel_start_bound_with_peer / sentinel_end_bound_with_peer) carries
    # the same rule; DELETE this map when the bundles are rebuilt.
    translated = translate_cql(_INTERVAL_PART3_CLOSED_NULL_LIBRARY)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expr in translated.items():
                sql = f"SELECT {expr.to_sql()}"
                py_result = py.execute(sql).fetchone()
                cpp_result = cpp.execute(sql).fetchone()
                assert cpp_result == py_result, f"{name}: cpp {cpp_result} != python {py_result}"
                assert py_result == (expected[name],), (
                    f"{name}: got {py_result}, expected {(expected[name],)}"
                )
                assert no_py.execute(sql).fetchone() == (expected[name],), (
                    f"{name}: no-Python expected {(expected[name],)}"
                )
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part3_closed_null_bound_direct_udf_surface() -> None:
    """FHIR4-38: direct-UDF sentinel semantics for intervalStartsSame/EndsSame.

    Both UDFs are Python-preferred, so the py-fallback and native-loaded
    connections route through the same implementation; the closed-null
    sentinel must be inferred from the PEER interval (Interval<T> is shared).
    """
    closed_null = '{"low": null, "high": null, "lowClosed": true, "highClosed": true}'
    int_1_10 = '{"low":"1","high":"10","lowClosed":true,"highClosed":true}'
    int_min_10 = '{"low":"-2147483648","high":"10","lowClosed":true,"highClosed":true}'
    int_null_5 = '{"low": null, "high":"5","lowClosed":true,"highClosed":true}'
    open_null = '{"low": null, "high": null, "lowClosed": false, "highClosed": false}'
    date_year = '{"low":"2024-01-01","high":"2024-12-31","lowClosed":true,"highClosed":true}'

    cases = [
        # Closed null bound -> point-type extremum (definite false/true).
        ("intervalStartsSame", [closed_null, int_1_10], False),
        ("intervalEndsSame", [int_1_10, closed_null], False),
        ("intervalStartsSame", [closed_null, date_year], False),
        ("intervalEndsSame", [date_year, closed_null], False),
        ("intervalStartsSame", [int_null_5, int_min_10], True),
        ("intervalStartsSame", [closed_null, closed_null], None),
        # Open null bounds stay unknown.
        ("intervalStartsSame", [open_null, int_1_10], None),
        ("intervalEndsSame", [int_1_10, open_null], None),
        # Non-null controls.
        ("intervalStartsSame", [int_1_10, int_1_10], True),
        ("intervalEndsSame", [int_1_10, int_1_10], True),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for func, args, want in cases:
            placeholders = ", ".join("?" for _ in args)
            sql = f"SELECT {func}({placeholders})"
            py_result = py.execute(sql, args).fetchone()
            cpp_result = cpp.execute(sql, args).fetchone()
            assert cpp_result == py_result, f"{func}{tuple(args)}: cpp/py mismatch"
            assert py_result == (want,), f"{func}{tuple(args)}: got {py_result}, expected {(want,)}"
    finally:
        py.close()
        cpp.close()


# ---------------------------------------------------------------------------
# FHIR4-43 — `properly contains` is not CQL and must not reach SQL
# ---------------------------------------------------------------------------

#: Every behaviourally-meaningful shape of the rejected spelling: all seven
#: point types, the list form, the interval-interval form, and the
#: parenthesised/negated wrappers that keep the inner binary expression.
_FHIR4_43_REJECTED_SPELLINGS = [
    "Interval[1, 10] properly contains 5",
    "Interval[1, 10] properly contains 10",
    "Interval[1, 1] properly contains 1",
    "Interval(1, 10] properly contains 2",
    "Interval[1.0, 10.0] properly contains 5.5",
    "Interval[@2024-01-01, @2024-12-31] properly contains @2024-06-15",
    "Interval[@2024-01-01T00:00:00, @2024-06-01T00:00:00] properly contains @2024-03-01T00:00:00",
    "Interval[@T08:00:00, @T18:00:00] properly contains @T12:00:00",
    "Interval[1 'g', 10 'g'] properly contains 5 'g'",
    "{'a', 'b', 'c'} properly contains 'b'",
    "Interval[1, 10] properly contains Interval[2, 3]",
    "(Interval[1, 10]) properly contains 5",
    "not (Interval[1, 10] properly contains 5)",
    # Same defect class, one line away in the old parser: `properly` never
    # qualifies `in` in the CQL grammar either.
    "5 properly in Interval[1, 10]",
]


def test_cql_properly_contains_rejected_at_parse_fhir4_43() -> None:
    """FHIR4-43: `properly contains` / `properly in` are not CQL operators.

    The CQL grammar lets ``properly`` qualify only ``between``, ``includes``,
    ``during`` / ``included in`` and ``within ... of`` — verified against
    https://cql.hl7.org/2019May/grammar.html (1.5.3 ``expression`` /
    ``intervalOperatorPhrase``), https://cql.hl7.org/grammar.html (2.0), and
    the reference implementation's ``grammar/cql.g4``.  Appendix B has no
    ``properly contains`` entry in 1.5.3 or 2.0; the point-in-interval reads
    are spelled ``properly includes (left Interval<T>, right T)`` (§9.22) and
    ``properly included in (left T, right Interval<T>)`` (§9.23).

    Before the fix the lexer pre-tokenized ``properly contains`` into a
    dedicated token, the parser accepted it, and the translator had no
    dispatch for the resulting operator string — so the raw text
    ``... properly contains 5`` was emitted into the generated SQL and DuckDB
    raised a ``ParserException`` at execution for every point type.
    """
    import pytest  # local import to match this module's convention

    from fhir4ds.cql.errors import ParseError

    for expression in _FHIR4_43_REJECTED_SPELLINGS:
        with pytest.raises(ParseError) as excinfo:
            parse_expression(expression)
        message = str(excinfo.value)
        # The error must name the offending spelling AND point at the valid
        # CQL reads, so an author can fix it without consulting the spec.
        assert "cannot be used with 'properly'" in message, message
        assert "properly includes" in message, message
        assert "properly included in" in message, message


def test_cql_properly_contains_never_reaches_generated_sql_fhir4_43() -> None:
    """FHIR4-43: translation must fail loudly, never emit the raw operator text.

    Guards the CQL-19 doctrine ("a parser-emitted operator string with no
    translator dispatch falls through to SQL pass-through and produces
    Binder/Parser exceptions at execution") for this spelling: the failure
    has to happen at parse/translate time with a typed error, and no
    generated SQL may ever contain ``properly contains``.
    """
    import pytest  # local import to match this module's convention

    from fhir4ds.cql.errors import ParseError

    library = (
        "library ProperlyContains version '1.0.0'\n"
        "using FHIR version '4.0.1'\n"
        "context Patient\n"
        "define Ctl: Interval[1, 10] properly includes 5\n"
        "define Bad: Interval[1, 10] properly contains 5\n"
    )
    with pytest.raises(ParseError) as excinfo:
        translate_cql(library)
    assert "properly contains" in str(excinfo.value)

    # Control: without the rejected define the same library translates, and
    # the valid spelling lowers through the interval UDF family.
    ok_library = library.replace("define Bad: Interval[1, 10] properly contains 5\n", "")
    translated = translate_cql(ok_library)
    emitted = translated["Ctl"].to_sql()
    assert "properly contains" not in emitted, emitted
    assert "intervalProperlyContains" in emitted, emitted


def test_cql_properly_includes_point_family_translates_and_executes_fhir4_43() -> None:
    """FHIR4-43 control: the supported spellings still cover every point type.

    The rejected keyword is the *only* gap in this family: ``properly
    includes`` (interval left) and ``properly included in`` (interval right,
    plus the ``properly during`` synonym) lower to ``intervalProperlyContains``
    and ``intervalProperlyIncludes`` and execute correctly across
    Integer / Decimal / Date / DateTime / Time / Quantity / String points and
    the interval-interval overload.
    """
    library = """library ProperlyPointFamily version '1.0.0'
using FHIR version '4.0.1'
context Patient
define IntPoint: Interval[1, 10] properly includes 5
define IntEndPoint: Interval[1, 10] properly includes 10
define IntUnit: Interval[1, 1] properly includes 1
define IntOpenLow: Interval(1, 10] properly includes 2
define DecimalPoint: Interval[1.0, 10.0] properly includes 5.5
define DatePoint: Interval[@2024-01-01, @2024-12-31] properly includes @2024-06-15
define DateTimePoint: Interval[@2024-01-01T00:00:00, @2024-06-01T00:00:00] properly includes @2024-03-01T00:00:00
define TimePoint: Interval[@T08:00:00, @T18:00:00] properly includes @T12:00:00
define QuantityPoint: Interval[1 'g', 10 'g'] properly includes 5 'g'
define IntervalOverload: Interval[1, 10] properly includes Interval[2, 3]
define MirrorPoint: 5 properly included in Interval[1, 10]
define MirrorDuring: Interval[2, 3] properly during Interval[1, 10]
"""
    expected = {
        "IntPoint": True,
        "IntEndPoint": False,  # equal to the closed high bound
        "IntUnit": False,  # unit interval containing only the point
        "IntOpenLow": True,  # effective start of Interval(1, 10] is 2
        "DecimalPoint": True,
        "DatePoint": True,
        "DateTimePoint": True,
        "TimePoint": True,
        "QuantityPoint": True,
        "IntervalOverload": True,
        "MirrorPoint": True,
        "MirrorDuring": True,
    }

    translated = translate_cql(library)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, want in expected.items():
            sql = translated[name].to_sql()
            assert "properly" not in sql, f"{name}: raw operator text leaked: {sql}"
            if name == "IntervalOverload":
                assert "intervalProperlyIncludes" in sql, f"{name}: {sql}"
            elif name == "MirrorDuring":
                # `properly during` is the §9.23 synonym of `properly included in`.
                assert "intervalProperlyIncludedIn" in sql, f"{name}: {sql}"
            else:
                assert "intervalProperlyContains" in sql, f"{name}: {sql}"
            py_result = py.execute(f"SELECT {sql}").fetchone()
            cpp_result = cpp.execute(f"SELECT {sql}").fetchone()
            assert py_result == (want,), f"{name}: py got {py_result}, expected {(want,)}"
            assert cpp_result == py_result, f"{name}: cpp/py mismatch {cpp_result} vs {py_result}"
    finally:
        py.close()
        cpp.close()
