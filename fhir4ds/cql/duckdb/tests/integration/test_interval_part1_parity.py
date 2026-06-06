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
        ("SELECT intervalContains(NULL, '5')", (None,)),
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
        "CollapseValidPer": [
            {"low": "1", "high": "2", "lowClosed": True, "highClosed": True},
            {"low": "5", "high": "6", "lowClosed": True, "highClosed": True},
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
                if isinstance(expected_result, list):
                    assert _load_json(py_value) == _load_json(cpp_value) == _load_json(no_py_value), name
                    assert _load_json(py_value) == expected_result
                else:
                    assert cpp_value == py_value == no_py_value, name
                    assert py_value == expected_result
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
