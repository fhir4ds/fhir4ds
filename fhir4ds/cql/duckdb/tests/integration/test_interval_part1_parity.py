"""CQL interval operator part 1 parity checks."""

from __future__ import annotations

import json

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


def _load_json(value: str):
    return json.loads(value)


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
define OpenEqualCheck: Interval(1, 6] = Interval[2, 6]
define OpenEquivalentCheck: Interval(1, 6] ~ Interval[2, 6]
define ExceptCheck: Interval[1, 5] except Interval[2, 3]
define NestedExceptContains: (Interval[1, 10] except Interval[1, 4]) contains 5
define InPrecision: @2024-01-05 in day of Interval[@2024-01-01, @2024-01-31]
define IncludesPrecision: Interval[@2024-01-01, @2024-01-31] includes day of Interval[@2024-01-05, @2024-01-10]
define CollapseCheck: collapse { Interval[1, 3], Interval[4, 6] }
define DateTimeContains: Interval[DateTime(2012, 1, 1), DateTime(2012, 1, 15)] contains DateTime(2012, 1, 10)
define DateTimeCollapse: collapse { Interval[DateTime(2012, 1, 1), DateTime(2012, 1, 15)], Interval[DateTime(2012, 1, 16), DateTime(2012, 5, 25)] }
define DateTimeExcept: Interval[DateTime(2012, 1, 5), DateTime(2012, 1, 25)] except Interval[DateTime(2012, 1, 7), DateTime(2012, 1, 25)]
define ExpandCheck: expand Interval[1, 3]
"""
    translated = translate_cql(cql)

    assert "cqlAfterP" in str(translated["AfterPrecision"])
    assert "cqlBeforeP" in str(translated["BeforePrecision"])
    assert "intervalContains" in str(translated["ContainsPrecision"])
    assert "intervalEnd" in str(translated["EndCheck"])
    assert "intervalEnd" in str(translated["EndsPrecision"])
    assert "intervalExcept" in str(translated["ExceptCheck"])
    assert "intervalContains" in str(translated["NestedExceptContains"])
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
define NestedExceptContains: (Interval[1, 10] except Interval[1, 4]) contains 5
define InPrecision: @2024-01-05 in day of Interval[@2024-01-01, @2024-01-31]
define IncludesPrecision: Interval[@2024-01-01, @2024-01-31] includes day of Interval[@2024-01-05, @2024-01-10]
define CollapseCheck: collapse { Interval[1, 3], Interval[4, 6] }
define DateTimeContains: Interval[DateTime(2012, 1, 1), DateTime(2012, 1, 15)] contains DateTime(2012, 1, 10)
define DateTimeCollapse: collapse { Interval[DateTime(2012, 1, 1), DateTime(2012, 1, 15)], Interval[DateTime(2012, 1, 16), DateTime(2012, 5, 25)] }
define DateTimeExcept: Interval[DateTime(2012, 1, 5), DateTime(2012, 1, 25)] except Interval[DateTime(2012, 1, 7), DateTime(2012, 1, 25)]
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
        "EqualCheck": (True,),
        "EquivalentCheck": (True,),
        "OpenEqualCheck": (True,),
        "OpenEquivalentCheck": (True,),
        "DateTimeContains": (True,),
        "NestedExceptContains": (True,),
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
        dt_collapse = py.execute(f"SELECT {translated['DateTimeCollapse'].to_sql()}").fetchone()[0]
        assert "2012-01-01T" in dt_collapse
        assert "2012-05-25T" in dt_collapse
        dt_except = py.execute(f"SELECT {translated['DateTimeExcept'].to_sql()}").fetchone()[0]
        assert "2012-01-05T" in dt_except
        assert "2012-01-06T" in dt_except
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


def test_cql_interval_part1_precision_uncertainty_matches_no_python_cpp() -> None:
    """Partial temporal bounds remain uncertain at finer explicit precision."""
    cases = [
        (
            "SELECT intervalBeforePrecise("
            "'{\"low\":\"2012-01-01\",\"high\":\"2012-01-01\",\"lowClosed\":true,\"highClosed\":true}', "
            "'{\"low\":\"2012-01-01T12\",\"high\":\"2012-01-01T12\",\"lowClosed\":true,\"highClosed\":true}', "
            "'millisecond')",
            (None,),
        ),
        (
            "SELECT intervalIncludesPrecise("
            "'{\"low\":\"2012-01-01\",\"high\":\"2012-01-02\",\"lowClosed\":true,\"highClosed\":true}', "
            "'{\"low\":\"2012-01-01T12\",\"high\":\"2012-01-01T12\",\"lowClosed\":true,\"highClosed\":true}', "
            "'millisecond')",
            (None,),
        ),
        (
            "SELECT intervalEndsSame("
            "'{\"low\":null,\"high\":null,\"lowClosed\":false,\"highClosed\":false}', "
            "'{\"low\":1,\"high\":10,\"lowClosed\":true,\"highClosed\":true}')",
            (None,),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in cases:
                assert py.execute(sql).fetchone() == expected
                assert cpp.execute(sql).fetchone() == expected
                assert no_py.execute(sql).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_contains_null_container_semantics_match_no_python_cpp() -> None:
    """CQL contains/in null-container rules return false, not SQL NULL."""
    cql = """library IntervalNullContainment version '1.0.0'
using FHIR version '4.0.1'
context Patient
define NullContainsPoint: null contains 5
define PointInNullInterval: 5 in (null as Interval<Integer>)
define NullBoundsContainsPoint: Interval[null, null] contains 5
define PointInNullBounds: 5 in Interval[null, null]
define ContainsNullPoint: Interval[1, 10] contains null
"""
    translated = translate_cql(cql)
    expected = {
        "NullContainsPoint": (False,),
        "PointInNullInterval": (False,),
        "NullBoundsContainsPoint": (False,),
        "PointInNullBounds": (False,),
        "ContainsNullPoint": (None,),
    }
    direct_cases = [
        # CQL §19.3 Contains: "If the first argument is null, the result
        # is false." Both intervalContains and intervalContainsPrecise
        # must short-circuit null first arg to False.
        ("SELECT intervalContains(NULL, '5')", (False,)),
        ("SELECT intervalContains(intervalFromBounds('1', '10', true, true), NULL)", (None,)),
        ("SELECT intervalContainsPrecise(NULL, '2024-01-05', 'day')", (False,)),
        (
            "SELECT intervalContainsPrecise("
            "intervalFromBounds('2024-01-01', '2024-01-31', true, true), NULL, 'day')",
            (None,),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected_result in direct_cases:
                assert py.execute(sql).fetchone() == expected_result
                assert cpp.execute(sql).fetchone() == expected_result
                assert no_py.execute(sql).fetchone() == expected_result
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                assert py.execute(sql).fetchone() == expected_result
                assert cpp.execute(sql).fetchone() == expected_result
                assert no_py.execute(sql).fetchone() == expected_result
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_collapse_expand_empty_and_incompatible_per_match_no_python_cpp() -> None:
    """Empty collapse and incompatible per units preserve spec-shaped outputs."""
    cql = """library IntervalCollapseExpandPer version '1.0.0'
using FHIR version '4.0.1'
context Patient
define CollapseEmpty: collapse { }
define CollapseInvalidPer: collapse { Interval[1, 3] } per 1 'cm'
define CollapseValidPer: collapse { Interval[1, 3], Interval[5, 6] } per 2
define CollapsePerOne: collapse { Interval[1, 3], Interval[5, 6] } per 1
define CollapsePerZero: collapse { Interval[1, 3], Interval[4, 6] } per 0
define CollapsePerNoMerge: collapse { Interval[1, 3], Interval[7, 9] } per 2
define CollapsePerDecimal: collapse { Interval[1.0, 3.0], Interval[3.5, 6.0] } per 1.0
define CollapsePerTemporalOne: collapse { Interval[@2024-01-01, @2024-01-03], Interval[@2024-01-05, @2024-01-08] } per day
define CollapsePerTemporalTwo: collapse { Interval[@2024-01-01, @2024-01-03], Interval[@2024-01-06, @2024-01-08] } per 2 days
define EndsPrecStartConjunct: Interval[@2012-01-01, @2012-01-15] ends day of Interval[@2012-01-05, @2012-01-15]
define EndsPrecTrue: Interval[@2012-01-05, @2012-01-15] ends day of Interval[@2012-01-01, @2012-01-15]
define EndsSpecFalse: Interval[-1, 7] ends Interval[0, 7]
define ExceptListInterval: { Interval[1, 5], Interval[10, 12] } except Interval[2, 3]
define ExpandNull: expand null
define ExpandInvalidPer: expand Interval[1, 3] per 1 'cm'
define ExpandValidNumericPer: expand Interval[1, 5] per 2
"""
    translated = translate_cql(cql)
    direct_cases = [
        ("SELECT collapse_intervals('[]')", "[]"),
        (
            "SELECT expand_points(intervalFromBounds('1', '3', true, true), "
            "'{\"value\":1,\"unit\":\"cm\",\"code\":\"cm\"}')",
            "[]",
        ),
    ]
    expected = {
        "CollapseEmpty": "[]",
        "CollapseInvalidPer": None,
        # CQL 1.5 §9 Collapse per: each interval's end is extended by `per`
        # for the merge decision (reference getIntervalWithPerApplied);
        # output intervals keep their ORIGINAL boundaries.
        "CollapseValidPer": [
            {"low": "1", "high": "6", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerOne": [
            {"low": "1", "high": "6", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerZero": [
            {"low": "1", "high": "6", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerNoMerge": [
            {"low": "1", "high": "3", "lowClosed": True, "highClosed": True},
            {"low": "7", "high": "9", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerDecimal": [
            {"low": "1.0", "high": "6.0", "lowClosed": True, "highClosed": True},
        ],
        # Temporal per of exactly 1 unit: precision-based meets — no merge.
        "CollapsePerTemporalOne": [
            {"low": "2024-01-01", "high": "2024-01-03", "lowClosed": True, "highClosed": True},
            {"low": "2024-01-05", "high": "2024-01-08", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerTemporalTwo": [
            {"low": "2024-01-01", "high": "2024-01-08", "lowClosed": True, "highClosed": True},
        ],
        # CQL 1.5 §9 Ends at precision: start(left) >= start(right) AND
        # end(left) == end(right), both at the given precision.
        "EndsPrecStartConjunct": False,
        "EndsPrecTrue": True,
        "EndsSpecFalse": False,
        "ExceptListInterval": [
            '{"low": "1", "high": "5", "lowClosed": true, "highClosed": true}',
            '{"low": "10", "high": "12", "lowClosed": true, "highClosed": true}',
        ],
        "ExpandNull": None,
        "ExpandInvalidPer": "[]",
        "ExpandValidNumericPer": [1, 3],
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected_result in direct_cases:
                assert py.execute(sql).fetchone()[0] == expected_result
                assert cpp.execute(sql).fetchone()[0] == expected_result
                assert no_py.execute(sql).fetchone()[0] == expected_result
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                if isinstance(py_value, list):
                    # List-returning results (e.g. list except) arrive as
                    # DuckDB LISTs, not JSON text.
                    assert py_value == cpp_value == no_py_value, name
                    assert py_value == expected_result
                elif isinstance(expected_result, list):
                    assert _load_json(py_value) == _load_json(cpp_value) == _load_json(no_py_value), name
                    assert _load_json(py_value) == expected_result
                else:
                    assert cpp_value == py_value == no_py_value, name
                    assert py_value == expected_result
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_expand_hour_precision_time_interval_matches_cpp_per_spec() -> None:
    """CQL §19.25 Expand: hour-precision Time intervals must dispatch correctly.

    Spec example: `expand { Interval[@T10, @T12] } per hour` produces
    `{ Interval[@T10, @T10], Interval[@T11, @T11], Interval[@T12, @T12] }`.

    Previously the Python fallback returned `[]` for hour-only Time bounds
    (no colon in raw string) while the C++ extension returned the correct
    3 intervals. The fix uses `_is_time_like_string()` for dispatch.
    """
    cql = """library IntervalExpandHour version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ExpandHourPrecision: expand { Interval[@T10, @T12] } per hour
define ExpandHourRange: expand { Interval[@T10, @T15] } per hour
define ExpandPer2Hours: expand { Interval[@T10, @T14] } per 2 hours
define ExpandPerMinuteEmpty: expand { Interval[@T10, @T10] } per minute
"""
    translated = translate_cql(cql)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            # Spec example: hour-precision bound + per hour = 3 unit intervals
            sql = f"SELECT {translated['ExpandHourPrecision'].to_sql()}"
            py_result = _load_json(py.execute(sql).fetchone()[0])
            cpp_result = _load_json(cpp.execute(sql).fetchone()[0])
            no_py_result = _load_json(no_py.execute(sql).fetchone()[0])
            assert py_result == cpp_result == no_py_result
            assert len(py_result) == 3
            assert py_result[0]["low"] == "T10"
            assert py_result[1]["low"] == "T11"
            assert py_result[2]["low"] == "T12"

            # Range covering 6 hours
            sql = f"SELECT {translated['ExpandHourRange'].to_sql()}"
            py_result = _load_json(py.execute(sql).fetchone()[0])
            cpp_result = _load_json(cpp.execute(sql).fetchone()[0])
            no_py_result = _load_json(no_py.execute(sql).fetchone()[0])
            assert py_result == cpp_result == no_py_result
            assert len(py_result) == 6

            # Per 2 hours: T10, T12, T14
            sql = f"SELECT {translated['ExpandPer2Hours'].to_sql()}"
            py_result = _load_json(py.execute(sql).fetchone()[0])
            cpp_result = _load_json(cpp.execute(sql).fetchone()[0])
            no_py_result = _load_json(no_py.execute(sql).fetchone()[0])
            assert py_result == cpp_result == no_py_result
            assert len(py_result) == 3
            assert [iv["low"] for iv in py_result] == ["T10", "T12", "T14"]

            # Spec example: less-precise boundary + more-precise per = empty
            sql = f"SELECT {translated['ExpandPerMinuteEmpty'].to_sql()}"
            py_result = py.execute(sql).fetchone()[0]
            cpp_result = cpp.execute(sql).fetchone()[0]
            no_py_result = no_py.execute(sql).fetchone()[0]
            assert _load_json(py_result) == []
            assert _load_json(cpp_result) == []
            assert _load_json(no_py_result) == []
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_expand_open_bounds_time_interval_matches_cpp_per_spec() -> None:
    """CQL §19.25 Expand: open-bound Time intervals dispatch partitions correctly.

    Per spec: "contribute all the intervals of size per that start on or after
    the lower boundary and end on or before the upper boundary". For open
    bounds, partitions whose start equals the open boundary are excluded
    (the boundary itself is not contained in the interval).

    - `expand { Interval(T10, T12] } per hour` → 2 intervals {T11, T12}
      (T10 partition excluded; T10:00:00.000 itself is not in the open-low
      interval)
    - `expand { Interval[T10, T12) } per hour` → 2 intervals {T10, T11}
      (T12 partition excluded; T12:00:00.000 itself is not in the open-high
      interval)
    - `expand { Interval(T10, T12) } per hour` → 1 interval {T11}
      (both T10 and T12 partitions excluded)
    """
    cql = """library IntervalExpandOpen version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ExpandOpenLow: expand { Interval(@T10, @T12] } per hour
define ExpandOpenHigh: expand { Interval[@T10, @T12) } per hour
define ExpandOpenBoth: expand { Interval(@T10, @T12) } per hour
"""
    translated = translate_cql(cql)
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            # Open low: T10 partition excluded, T11 and T12 included
            sql = f"SELECT {translated['ExpandOpenLow'].to_sql()}"
            py_result = _load_json(py.execute(sql).fetchone()[0])
            cpp_result = _load_json(cpp.execute(sql).fetchone()[0])
            no_py_result = _load_json(no_py.execute(sql).fetchone()[0])
            assert py_result == cpp_result == no_py_result
            assert len(py_result) == 2
            assert [iv["low"] for iv in py_result] == ["T11", "T12"]

            # Open high: T12 partition excluded, T10 and T11 included
            sql = f"SELECT {translated['ExpandOpenHigh'].to_sql()}"
            py_result = _load_json(py.execute(sql).fetchone()[0])
            cpp_result = _load_json(cpp.execute(sql).fetchone()[0])
            no_py_result = _load_json(no_py.execute(sql).fetchone()[0])
            assert py_result == cpp_result == no_py_result
            assert len(py_result) == 2
            assert [iv["low"] for iv in py_result] == ["T10", "T11"]

            # Open both: only T11 partition included
            sql = f"SELECT {translated['ExpandOpenBoth'].to_sql()}"
            py_result = _load_json(py.execute(sql).fetchone()[0])
            cpp_result = _load_json(cpp.execute(sql).fetchone()[0])
            no_py_result = _load_json(no_py.execute(sql).fetchone()[0])
            assert py_result == cpp_result == no_py_result
            assert len(py_result) == 1
            assert py_result[0]["low"] == "T11"
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_open_interval_equality_uses_start_end_semantics() -> None:
    cql = """library IntervalEquality version '1.0.0'
using FHIR version '4.0.1'
context Patient
define OpenEqual: Interval(1, 6] = Interval[2, 6]
define OpenNotEqual: Interval(1, 6] != Interval[2, 6]
define OpenEquivalent: Interval(1, 6] ~ Interval[2, 6]
define OpenNotEquivalent: Interval(1, 6] !~ Interval[2, 6]
"""
    translated = translate_cql(cql)
    expected = {
        "OpenEqual": (True,),
        "OpenNotEqual": (False,),
        "OpenEquivalent": (True,),
        "OpenNotEquivalent": (False,),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                assert py.execute(sql).fetchone() == expected_result
                assert cpp.execute(sql).fetchone() == expected_result
                assert no_py.execute(sql).fetchone() == expected_result
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_unbounded_interval_equality_matches_no_python_cpp() -> None:
    """Matching unbounded starts/ends are equal on every public surface."""
    cql = """library IntervalUnboundedEquality version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MissingHighEqual: Interval[1, null) = Interval[1, null)
define MissingHighNotEqual: Interval[1, null) != Interval[1, null)
define MissingHighEquivalent: Interval[1, null) ~ Interval[1, null)
define MissingLowEqual: Interval(null, 5] = Interval(null, 5]
define MissingLowEquivalent: Interval(null, 5] ~ Interval(null, 5]
define OneMissingEndEqual: Interval[1, null) = Interval[1, 5]
"""
    translated = translate_cql(cql)
    expected = {
        "MissingHighEqual": (True,),
        "MissingHighNotEqual": (False,),
        "MissingHighEquivalent": (True,),
        "MissingLowEqual": (True,),
        "MissingLowEquivalent": (True,),
        "OneMissingEndEqual": (False,),
    }
    direct_cases = [
        (
            "SELECT intervalEquals("
            "intervalFromBounds(CAST(1 AS VARCHAR), NULL, TRUE, FALSE), "
            "intervalFromBounds(CAST(1 AS VARCHAR), NULL, TRUE, FALSE))",
            (True,),
        ),
        (
            "SELECT intervalEquals("
            "intervalFromBounds(NULL, CAST(5 AS VARCHAR), FALSE, TRUE), "
            "intervalFromBounds(NULL, CAST(5 AS VARCHAR), FALSE, TRUE))",
            (True,),
        ),
        (
            "SELECT intervalEquals("
            "intervalFromBounds(CAST(1 AS VARCHAR), NULL, TRUE, FALSE), "
            "intervalFromBounds(CAST(1 AS VARCHAR), CAST(5 AS VARCHAR), TRUE, TRUE))",
            (False,),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected_result in direct_cases:
                assert py.execute(sql).fetchone() == expected_result
                assert cpp.execute(sql).fetchone() == expected_result
                assert no_py.execute(sql).fetchone() == expected_result
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                assert py.execute(sql).fetchone() == expected_result
                assert cpp.execute(sql).fetchone() == expected_result
                assert no_py.execute(sql).fetchone() == expected_result
    finally:
        py.close()
        cpp.close()


def test_cql_interval_quantity_contains_uses_unit_aware_comparison() -> None:
    cql = """library IntervalQuantityContains version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ContainsCompatibleQuantity: Interval[1 'g', 2 'g'] contains 1500 'mg'
define ContainsIncompatibleQuantity: Interval[1 'g', 2 'g'] contains 1 'cm'
define IncludesCompatibleQuantity: Interval[1 'g', 2 'g'] includes Interval[1500 'mg', 1600 'mg']
"""
    translated = translate_cql(cql)
    direct_cases = [
        (
            "SELECT intervalContains("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}', "
            "'{\"value\":2,\"unit\":\"g\",\"code\":\"g\"}', true, true), "
            "'{\"value\":1500,\"unit\":\"mg\",\"code\":\"mg\"}')",
            (True,),
        ),
        (
            "SELECT intervalContains("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}', "
            "'{\"value\":2,\"unit\":\"g\",\"code\":\"g\"}', true, true), "
            "'{\"value\":1,\"unit\":\"cm\",\"code\":\"cm\"}')",
            (None,),
        ),
        (
            "SELECT intervalIncludes("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}', "
            "'{\"value\":2,\"unit\":\"g\",\"code\":\"g\"}', true, true), "
            "intervalFromBounds('{\"value\":1500,\"unit\":\"mg\",\"code\":\"mg\"}', "
            "'{\"value\":1600,\"unit\":\"mg\",\"code\":\"mg\"}', true, true))",
            (True,),
        ),
    ]
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in direct_cases:
                assert py.execute(sql).fetchone() == expected
                assert cpp.execute(sql).fetchone() == expected
                assert no_py.execute(sql).fetchone() == expected
            expected = {
                "ContainsCompatibleQuantity": (True,),
                "ContainsIncompatibleQuantity": (None,),
                "IncludesCompatibleQuantity": (True,),
            }
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                assert py.execute(sql).fetchone() == expected_result
                assert cpp.execute(sql).fetchone() == expected_result
                assert no_py.execute(sql).fetchone() == expected_result
    finally:
        py.close()
        cpp.close()


def test_cql_interval_quantity_membership_preserves_fhir_quantity_projection() -> None:
    cql = """library IntervalQuantityFHIRPath version '1.0.0'
using FHIR version '4.0.1'
codesystem "LOINC": 'http://loinc.org'
code "Systolic blood pressure": '8480-6' from "LOINC" display 'Systolic blood pressure'
context Patient
define LastBP: First([Observation])
define SystolicInRange:
  (singleton from (LastBP.component C where C.code ~ "Systolic blood pressure")).value in Interval[120 'mm[Hg]', 129 'mm[Hg]']
"""
    translated = translate_cql(cql)
    sql = translated["SystolicInRange"].to_sql()

    assert "intervalContains" in sql
    assert "fhirpath_text" in sql
    assert "valueQuantity'))" in sql
    assert "valueQuantity.value')" not in sql


def test_cql_interval_quantity_boundaries_and_expand_preserve_quantity_shape() -> None:
    cql = """library IntervalQuantityExpand version '1.0.0'
using FHIR version '4.0.1'
context Patient
define EndOpenQuantity: end of Interval[1 'g', 2 'g')
define QuantityExceptLeft: Interval[1 'g', 2 'g'] except Interval[1500 'mg', 2 'g']
define QuantityExpandList: expand { Interval[1 'g', 3 'g'] } per 1 'g'
define QuantityExpandPoints: expand Interval[1 'g', 3 'g'] per 1 'g'
"""
    translated = translate_cql(cql)
    direct_cases = {
        "QuantityContainsScalar": (
            "SELECT intervalContains("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}', "
            "'{\"value\":2,\"unit\":\"g\",\"code\":\"g\"}', true, true), '1.5')",
            None,
        ),
        "QuantityExpandList": (
            "SELECT expand([intervalFromBounds('{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}', "
            "'{\"value\":3,\"unit\":\"g\",\"code\":\"g\"}', true, true)], "
            "'{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}')",
            [
                {"low": {"value": 1.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"}, "high": {"value": 1.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"}, "lowClosed": True, "highClosed": True},
                {"low": {"value": 2.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"}, "high": {"value": 2.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"}, "lowClosed": True, "highClosed": True},
                {"low": {"value": 3.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"}, "high": {"value": 3.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"}, "lowClosed": True, "highClosed": True},
            ],
        ),
        "QuantityExpandPoints": (
            "SELECT expand_points(intervalFromBounds('{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}', "
            "'{\"value\":3,\"unit\":\"g\",\"code\":\"g\"}', true, true), "
            "'{\"value\":1,\"unit\":\"g\",\"code\":\"g\"}')",
            [
                {"value": 1.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"},
                {"value": 2.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"},
                {"value": 3.0, "unit": "g", "code": "g", "system": "http://unitsofmeasure.org"},
            ],
        ),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            end_sql = f"SELECT {translated['EndOpenQuantity'].to_sql()}"
            assert _load_json(py.execute(end_sql).fetchone()[0])["value"] == 1.99999999
            assert _load_json(cpp.execute(end_sql).fetchone()[0])["value"] == 1.99999999
            assert _load_json(no_py.execute(end_sql).fetchone()[0])["value"] == 1.99999999

            except_sql = f"SELECT {translated['QuantityExceptLeft'].to_sql()}"
            for con in (py, cpp, no_py):
                result = _load_json(con.execute(except_sql).fetchone()[0])
                assert result["high"]["value"] == 1499.99999999
                assert result["high"]["unit"] == "mg"

            for sql, expected in direct_cases.values():
                for con in (py, cpp, no_py):
                    actual = con.execute(sql).fetchone()[0]
                    if isinstance(expected, list):
                        assert _load_json(actual) == expected
                    else:
                        assert actual is expected

            translated_expected = {
                "QuantityExpandList": direct_cases["QuantityExpandList"][1],
                "QuantityExpandPoints": direct_cases["QuantityExpandPoints"][1],
            }
            for name, expected in translated_expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                for con in (py, cpp, no_py):
                    assert _load_json(con.execute(sql).fetchone()[0]) == expected
    finally:
        py.close()
        cpp.close()


def test_cql_day_precision_datetime_bounds_preserve_full_day_surface() -> None:
    first_half_2026 = (
        '{"low":"2026-01-01T00:00:00.000","high":"2026-07-01T00:00:00",'
        '"lowClosed":true,"highClosed":false}'
    )
    noon_june_30 = (
        '{"low":"2026-06-30T23:59:59.000+00:00","high":"2026-06-30T23:59:59.000+00:00",'
        '"lowClosed":true,"highClosed":true}'
    )
    quantity = '{"value":6,"unit":"month","system":"http://unitsofmeasure.org"}'

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for con in (py, cpp):
            assert con.execute("SELECT dateAddQuantity('2026-01-01T', ?)", [quantity]).fetchone() == (
                "2026-07-01T",
            )
            assert con.execute("SELECT intervalOverlaps(?, ?)", [noon_june_30, first_half_2026]).fetchone() == (
                True,
            )
            assert con.execute(
                "SELECT intervalContains(?, ?)",
                [
                    '{"low":"2026-01-01","high":"2026-12-31","lowClosed":true,"highClosed":true}',
                    "2026-06-30T12:00:00.000",
                ],
            ).fetchone() == (True,)
    finally:
        py.close()
        cpp.close()


def test_cql_interval_start_end_open_boundaries_use_effective_bounds() -> None:
    """Open interval boundaries expose successor/predecessor through start/end."""
    cases = [
        (
            "SELECT intervalStart('{\"low\":1,\"high\":5,\"lowClosed\":false,\"highClosed\":true}')",
            ("2",),
        ),
        (
            "SELECT intervalEnd('{\"low\":1,\"high\":5,\"lowClosed\":true,\"highClosed\":false}')",
            ("4",),
        ),
        (
            "SELECT intervalStart('{\"low\":\"2024-01-01\",\"high\":\"2024-01-31\",\"lowClosed\":false,\"highClosed\":true}')",
            ("2024-01-02",),
        ),
        (
            "SELECT intervalEnd('{\"low\":\"2024-01-01\",\"high\":\"2024-01-31\",\"lowClosed\":true,\"highClosed\":false}')",
            ("2024-01-30",),
        ),
        (
            "SELECT intervalStart('{\"low\":\"2024-01-01T\",\"high\":\"2024-01-31T\",\"lowClosed\":false,\"highClosed\":true}')",
            ("2024-01-02T",),
        ),
        (
            "SELECT intervalEnd('{\"low\":\"2024-01-01T\",\"high\":\"2024-01-31T\",\"lowClosed\":true,\"highClosed\":false}')",
            ("2024-01-30T",),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for sql, expected in cases:
            assert py.execute(sql).fetchone() == expected
            assert cpp.execute(sql).fetchone() == expected
    finally:
        py.close()
        cpp.close()


def test_cql_translated_start_end_open_boundaries_use_effective_bounds() -> None:
    cql = """library IntervalOpenBounds version '1.0.0'
using FHIR version '4.0.1'
context Patient
define StartOpenInt: start of Interval(1, 5]
define EndOpenInt: end of Interval[1, 5)
define StartOpenDate: start of Interval(@2024-01-01, @2024-01-31]
define EndOpenDate: end of Interval[@2024-01-01, @2024-01-31)
define EndOpenDateTimeDay: end of Interval[DateTime(2024, 1, 1), DateTime(2024, 1, 31))
define EndsDuringHalfOpenDay: Interval[DateTime(2025, 10, 31, 14, 35), DateTime(2025, 10, 31, 14, 45)] ends during day of Interval[DateTime(2024, 11, 1, 0, 0), DateTime(2025, 11, 1, 0, 0))
"""
    translated = translate_cql(cql)
    expected = {
        "StartOpenInt": ("2",),
        "EndOpenInt": ("4",),
        "StartOpenDate": ("2024-01-02",),
        "EndOpenDate": ("2024-01-30",),
        "EndOpenDateTimeDay": ("2024-01-30T",),
        "EndsDuringHalfOpenDay": (True,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected_result in expected.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == expected_result
            assert cpp.execute(sql).fetchone() == expected_result
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_historian_contains_in_precision_and_null_short_circuit() -> None:
    """CQL-15 HISTORIAN iteration 1 fresh-run regression coverage.

    Three spec violations were discovered by fresh HISTORIAN spec-walkthrough
    on 2026-07-02 and fixed:

    1. ``Interval<T> contains <precision> of <point>`` previously dropped the
       precision wrapper, falling through to ``intervalContains`` without
       precision and returning False for cases that must be NULL under
       partial-precision Date/DateTime/Time uncertainty (CQL §19.3).
    2. ``<point> in <precision> of <interval>`` previously built raw SQL
       ``>=``/``<=`` comparisons via ``_truncate_to_precision``, losing
       uncertainty detection for partial-precision Date bounds (CQL §19.11).
    3. ``(null as Interval<T>) contains (null as T)`` previously returned
       NULL; spec §19.3 Contains says first-arg-null short-circuits to
       False. Same for ``(null as Interval<T>) includes 5`` (point-interval
       overload is a synonym for contains per §19.12).
    """
    cql = """library HistorianCql15 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ContainsDayOfYearPrecision: Interval[@2024, @2024] contains day of @2024-06-15
define ContainsDayOfFullDate: Interval[@2024-01-01, @2024-12-31] contains day of @2024-06-15
define InDayOfYearPrecision: @2024-06-15 in day of Interval[@2024, @2024]
define InDayOfFullDate: @2024-06-15 in day of Interval[@2024-01-01, @2024-12-31]
define BothNullContains: (null as Interval<Integer>) contains (null as Integer)
define NullContainerContains: (null as Interval<Integer>) contains 5
define NullPointContains: Interval[1, 10] contains (null as Integer)
define NullContainerIncludesPoint: (null as Interval<Integer>) includes 5
define IncludesDayOfYearPrecision: Interval[@2024, @2024] includes day of @2024-06-15
"""
    translated = translate_cql(cql)
    expected = {
        # Partial-precision Date bounds → uncertain → NULL (was False)
        "ContainsDayOfYearPrecision": (None,),
        "ContainsDayOfFullDate": (True,),
        "InDayOfYearPrecision": (None,),
        "InDayOfFullDate": (True,),
        # Null-container short-circuit: first-arg null → False (was None)
        "BothNullContains": (False,),
        "NullContainerContains": (False,),
        "NullPointContains": (None,),
        "NullContainerIncludesPoint": (False,),
        # Includes precision overload (synonym for contains point-interval)
        "IncludesDayOfYearPrecision": (None,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                assert py.execute(sql).fetchone() == expected_result, (
                    f"PY {name}: expected {expected_result}, got "
                    f"{py.execute(sql).fetchone()}"
                )
                assert cpp.execute(sql).fetchone() == expected_result, (
                    f"CPP {name}: expected {expected_result}, got "
                    f"{cpp.execute(sql).fetchone()}"
                )
                assert no_py.execute(sql).fetchone() == expected_result, (
                    f"NO_PY {name}: expected {expected_result}, got "
                    f"{no_py.execute(sql).fetchone()}"
                )
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_explorer_expand_precision_truncation_and_parity() -> None:
    """CQL-15 EXPLORER iteration 1 fresh-run regression coverage.

    Four Expand-surface issues were discovered by fresh EXPLORER fuzz/pathological
    probes on 2026-07-02 and fixed:

    1. ``expand Interval[...] per year`` previously returned malformed ``"YYYYT"``
       literals on the native C++ extension (C++ ``DateTimeValue::to_string()``
       appended ``"T"`` for year precision). CQL §9 Date: year-precision dates
       serialize as 4-digit year YYYY.
    2. Python ``expand`` did not truncate temporal bounds to per-precision.
       CQL §19.10 Expand: "If the interval boundaries are more precise than the
       per quantity, the more precise values will be truncated to the precision
       specified by the per quantity." Spec example: ``expand { Interval[@T10:00,
       @T12:30] } per hour`` -> ``{ Interval[@T10, @T10], ... }``.
    3. ``expand Interval[null, null]`` returned ``[]`` on Python vs ``None`` on
       C++. Spec is permissive ("implementations are allowed to not return
       results"), but both backends must agree.
    4. ``expand Interval[1 'g', 5 'g'] per 1 'mg'`` had IEEE 754 floating-point
       accumulation drift in C++ (e.g., ``4.9990000000000006`` instead of
       ``4.999``).
    """
    cql = """library ExplorerCql15 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ExpandPerYear: expand Interval[@2024-01-01, @2025-01-01] per 1 year
define ExpandPerMonth: expand Interval[@2024-01-01, @2024-03-31] per 1 month
define ExpandPerDay: expand Interval[@2024-01-01, @2024-01-05] per 1 day
define ExpandPerHourTime: expand Interval[@T10:00:00, @T12:30:00] per 1 hour
define ExpandEmptyInterval: expand Interval[null as Integer, null as Integer]
define ExpandPerMgQuantity: expand Interval[1 'g', 5 'g'] per 1 'mg'
"""
    translated = translate_cql(cql)
    expected = {
        # Year-precision truncation: "2024" not "2024T"
        "ExpandPerYear": ('["2024","2025"]',),
        # Month-precision truncation
        "ExpandPerMonth": ('["2024-01","2024-02","2024-03"]',),
        # Day-precision unchanged
        "ExpandPerDay": (
            '["2024-01-01","2024-01-02","2024-01-03","2024-01-04","2024-01-05"]',
        ),
        # Time hour-precision truncation
        "ExpandPerHourTime": ('["T10","T11","T12"]',),
        # Null-bounds interval → null (parity with C++)
        "ExpandEmptyInterval": (None,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                assert py.execute(sql).fetchone() == expected_result, (
                    f"PY {name}: expected {expected_result}, got "
                    f"{py.execute(sql).fetchone()}"
                )
                assert cpp.execute(sql).fetchone() == expected_result, (
                    f"CPP {name}: expected {expected_result}, got "
                    f"{cpp.execute(sql).fetchone()}"
                )
                assert no_py.execute(sql).fetchone() == expected_result, (
                    f"NO_PY {name}: expected {expected_result}, got "
                    f"{no_py.execute(sql).fetchone()}"
                )

        # Quantity FP drift check: compare value-by-value (4001 items).
        # C++ must not produce values like 4.9990000000000006.
        sql_qty = f"SELECT {translated['ExpandPerMgQuantity'].to_sql()}"
        py_result = py.execute(sql_qty).fetchone()[0]
        cpp_result = cpp.execute(sql_qty).fetchone()[0]
        assert py_result == cpp_result, (
            f"ExpandPerMgQuantity parity: py={py_result[:120]}, "
            f"cpp={cpp_result[:120]}"
        )
        # Sanity: spot-check a known FP-trouble value (n=3999 -> 4.999).
        items = json.loads(py_result)
        assert len(items) == 4001, f"expected 4001 items, got {len(items)}"
        # Index 3999 should be exactly 4.999 (was 4.9990000000000006 pre-fix).
        assert items[3999]["value"] == 4.999, (
            f"index 3999 value: expected 4.999, got {items[3999]['value']!r}"
        )
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_historian_collapse_per_precision_and_includes_expand() -> None:
    """CQL-15 HISTORIAN pins: collapse per 0/1 precision meets, includes
    [precision] interval-interval routing, expand null-bound semantics.

    - CQL 1.5 §9 Collapse(argument, per): reference CollapseEvaluator keeps
      the interval unextended for a temporal per of exactly 0 or 1 unit and
      performs the overlaps/meets decision at the per-unit precision.
    - CQL 1.5 §9 Includes [precision] (Interval): comparisons are performed
      at the specified precision (determined results must not be null).
    - CQL 1.5 §9 Expand: an OPEN null boundary contributes no results;
      a CLOSED null boundary is an implementation choice not to expand
      (returns null, matching the native extension).
    """
    cql = """library IntervalHistorian version '1.0.0'
using FHIR version '4.0.1'
context Patient
define CollapsePerMonthMeets: collapse { Interval[@2024-01-15, @2024-01-31], Interval[@2024-02-02, @2024-02-10] } per month
define CollapsePerZeroMonthsMeets: collapse { Interval[@2024-01-15, @2024-01-31], Interval[@2024-02-02, @2024-02-10] } per 0 months
define CollapsePerMonthNoMerge: collapse { Interval[@2024-01-15, @2024-01-31], Interval[@2024-03-02, @2024-03-10] } per month
define CollapsePerYearMeets: collapse { Interval[@2024-01, @2024-03], Interval[@2024-05, @2024-06] } per year
define CollapsePerHourNoMerge: collapse { Interval[@2024-01-15T10, @2024-01-15T11], Interval[@2024-01-15T13, @2024-01-15T14] } per hour
define CollapsePerHourMeets: collapse { Interval[@2024-01-15T10, @2024-01-15T11], Interval[@2024-01-15T12, @2024-01-15T14] } per hour
define CollapsePerWeekMeets: collapse { Interval[@2024-01-02, @2024-01-03], Interval[@2024-01-05, @2024-01-06] } per week
define IncludesPrecMonthTrue: Interval[@2024-01-05, @2024-03-31] includes month of Interval[@2024-01-01, @2024-02-15]
define IncludesPrecMonthFalse: Interval[@2024-01-05, @2024-03-31] includes month of Interval[@2024-04-01, @2024-04-15]
define IncludesPrecDayTrue: Interval[@2024-01-01, @2024-03-31] includes day of Interval[@2024-02-01, @2024-02-15]
define IncludesPrecPoint: Interval[@2024-01-01, @2024-01-31] includes day of @2024-01-15
define ExpandClosedNullHigh: expand Interval[1, null]
define ExpandOpenNullHigh: expand Interval[1, null)
define ExpandOpenNullLow: expand Interval(null, 5]
"""
    translated = translate_cql(cql)
    expected = {
        "CollapsePerMonthMeets": [
            {"low": "2024-01-15", "high": "2024-02-10", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerZeroMonthsMeets": [
            {"low": "2024-01-15", "high": "2024-02-10", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerMonthNoMerge": [
            {"low": "2024-01-15", "high": "2024-01-31", "lowClosed": True, "highClosed": True},
            {"low": "2024-03-02", "high": "2024-03-10", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerYearMeets": [
            {"low": "2024-01", "high": "2024-06", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerHourNoMerge": [
            {"low": "2024-01-15T10", "high": "2024-01-15T11", "lowClosed": True, "highClosed": True},
            {"low": "2024-01-15T13", "high": "2024-01-15T14", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerHourMeets": [
            {"low": "2024-01-15T10", "high": "2024-01-15T14", "lowClosed": True, "highClosed": True},
        ],
        "CollapsePerWeekMeets": [
            {"low": "2024-01-02", "high": "2024-01-06", "lowClosed": True, "highClosed": True},
        ],
        "IncludesPrecMonthTrue": True,
        "IncludesPrecMonthFalse": False,
        "IncludesPrecDayTrue": True,
        "IncludesPrecPoint": True,
        "ExpandClosedNullHigh": None,
        "ExpandOpenNullHigh": [],
        "ExpandOpenNullLow": [],
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                if isinstance(expected_result, list) and not isinstance(py_value, list):
                    assert _load_json(py_value) == _load_json(cpp_value) == _load_json(no_py_value), name
                    assert _load_json(py_value) == expected_result
                else:
                    assert py_value == cpp_value == no_py_value, name
                    assert py_value == expected_result, name
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_explorer3_list_extract_interval_operands_route_as_intervals() -> None:
    """CQL-15 EXPLORER (iter 1) QA-001 regression: LIST_EXTRACT operands.

    Element selection over interval lists — ``First({Interval[4, 6]})``,
    ``Last(...)``, and indexers over ``collapse(...)`` output — lower to
    ``LIST_EXTRACT`` which the interval-expression recognition
    (``_is_fhir_interval_expression``) must classify as an Interval operand
    for CQL 1.5 §9 operator routing. Before the fix: contains/in degraded
    to DuckDB string-contains Binder Errors, after/before raised UDF
    TypeErrors, ends/starts silently re-wrapped the selection as a
    degenerate intervalFromBounds(x, x) -> false, except returned null, and
    expand emitted degenerate interval structs instead of points.
    """
    cql = """library IntervalExplorer3 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define FirstContains: First({ Interval[4, 6] }) contains 5
define FirstIn: 5 in First({ Interval[4, 6] })
define FirstIncludesPoint: First({ Interval[4, 6] }) includes 5
define FirstIncludesInterval: First({ Interval[4, 6] }) includes Interval[4, 5]
define IncludedFirst: Interval[3, 9] includes First({ Interval[4, 6] })
define FirstAfter: First({ Interval[4, 6] }) after Interval[1, 2]
define FirstBefore: First({ Interval[4, 6] }) before Interval[9, 10]
define FirstStart: start of First({ Interval[4, 6] })
define FirstEnd: end of First({ Interval[4, 6] })
define FirstEqual: First({ Interval[4, 6] }) = Interval[4, 6]
define FirstEquivalent: First({ Interval[4, 6] }) ~ Interval[4, 6]
define FirstEnds: First({ Interval[4, 6] }) ends Interval[1, 6]
define FirstStarts: First({ Interval[4, 6] }) starts Interval[4, 9]
define LastContains: Last({ Interval[4, 6] }) contains 6
define FirstExpand: expand First({ Interval[4, 6] }) per 1
define CollapseIdxContains: (collapse { Interval[1, 2], Interval[4, 6] })[1] contains 5
define CollapseIdxExcept: (collapse { Interval[1, 2], Interval[4, 6] })[1] except Interval[4, 5]
define ContainsStartOfFirst: Interval[4, 6] contains start of First({ Interval[4, 6] })
"""
    translated = translate_cql(cql)
    expected = {
        "FirstContains": True,
        "FirstIn": True,
        "FirstIncludesPoint": True,
        "FirstIncludesInterval": True,
        "IncludedFirst": True,
        "FirstAfter": True,
        "FirstBefore": True,
        "FirstStart": "4",
        "FirstEnd": "6",
        "FirstEqual": True,
        "FirstEquivalent": True,
        "FirstEnds": True,
        "FirstStarts": True,
        "LastContains": True,
        "FirstExpand": "[4,5,6]",
        "CollapseIdxContains": True,
        "CollapseIdxExcept": '{"low": 6, "high": "6", "lowClosed": true, "highClosed": true}',
        "ContainsStartOfFirst": True,
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                py_value = py.execute(sql).fetchone()[0]
                cpp_value = cpp.execute(sql).fetchone()[0]
                no_py_value = no_py.execute(sql).fetchone()[0]
                if name == "CollapseIdxExcept":
                    # intervalExcept JSON scalar quoting of numeric bounds
                    # differs between the Python UDF ("low": 6) and the pure
                    # C++ serializer ("low": "6") — a pre-existing transport
                    # convention; normalize before comparing.
                    def _norm(v):
                        parsed = json.loads(v)
                        parsed["low"] = str(parsed["low"])
                        parsed["high"] = str(parsed["high"])
                        return parsed
                    py_value = _norm(py_value)
                    cpp_value = _norm(cpp_value)
                    no_py_value = _norm(no_py_value)
                    expected_iv = json.loads(expected_result)
                    expected_iv["low"] = str(expected_iv["low"])
                    expected_iv["high"] = str(expected_iv["high"])
                    expected_result = expected_iv
                assert py_value == cpp_value == no_py_value == expected_result, (
                    f"{name}: py={py_value!r}, cpp={cpp_value!r}, "
                    f"no_py={no_py_value!r}, expected={expected_result!r}"
                )
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part1_explorer3_expand_temporal_boundary_truncation() -> None:
    """CQL-15 EXPLORER (iter 1) QA-002 regression: Expand boundary semantics.

    CQL 1.5 §9 Expand: "If the interval boundaries are more precise than
    the per quantity, the more precise values will be truncated to the
    precision specified by the per quantity." For Date/Time boundaries
    LESS precise than per (temporal uncertainty): "the interval will not
    contribute any results to the output." Spec examples:
    ``expand Interval[@T10:30, @T12:00] per hour`` -> {T10, T11, T12};
    ``expand Interval[@T10, @T10] per minute`` -> {}.

    The numeric case (``expand Interval[1.2, 3.0] per 1`` -> [1.2, 2.2],
    grid from interval start) matches the HL7 DBCG Java reference engine
    (ExpandEvaluator.java) and is preserved verbatim.
    """
    cql = """library IntervalExplorer3B version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ExpandTruncHour: expand Interval[@2024-01-01T10:30, @2024-01-01T12:00] per hour
define ExpandTruncTimeHour: expand Interval[@T10:30, @T12:00] per hour
define ExpandLessPreciseDay: expand Interval[@2024-01, @2024-01] per day
define ExpandLessPreciseMinute: expand Interval[@T10, @T10] per minute
define ExpandNumericDbcg: expand Interval[1.2, 3.0] per 1
define ExpandTruncMonth: expand Interval[@2024-01-15, @2024-03-20] per month
"""
    translated = translate_cql(cql)
    expected = {
        "ExpandTruncHour": ('["2024-01-01T10","2024-01-01T11","2024-01-01T12"]',),
        "ExpandTruncTimeHour": ('["T10","T11","T12"]',),
        "ExpandLessPreciseDay": ("[]",),
        "ExpandLessPreciseMinute": ("[]",),
        "ExpandNumericDbcg": ("[1.2,2.2]",),
        "ExpandTruncMonth": ('["2024-01","2024-02","2024-03"]',),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, expected_result in expected.items():
                sql = f"SELECT {translated[name].to_sql()}"
                assert py.execute(sql).fetchone() == expected_result, name
                assert cpp.execute(sql).fetchone() == expected_result, name
                assert no_py.execute(sql).fetchone() == expected_result, name
    finally:
        py.close()
        cpp.close()
