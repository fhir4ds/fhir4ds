"""CQL interval operator part 2 parity checks."""

from __future__ import annotations

import duckdb
import json

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.parser import parse_cql, parse_expression
from fhir4ds.cql.parser.ast_nodes import BinaryExpression
from fhir4ds.cql.translator import CQLToSQLTranslator, translate_cql

from .wasm_runtime_helpers import no_python_connection


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
        "@2014-06-01T12 included in day of Interval[@2014-06-01T00, @2014-06-01T01]",
        "Interval[@2014, @2014] overlaps day of Interval[@2014-06-01, @2014-06-02]",
        "Interval[@2014, @2014] on or after Interval[@2014-06-01, @2014-06-02]",
        "Interval[@2014, @2014] on or before Interval[@2014-06-01, @2014-06-02]",
        "Interval[1 'g', 3 'g'] overlaps Interval[1 'cm', 2 'cm']",
        "Interval[1, 5) intersect Interval[5, 7]",
        "Interval[@2014, @2014] overlaps before day of Interval[@2014-06-01, @2014-06-02]",
        "Interval[@2014-06-01, @2014-06-02] overlaps after day of Interval[@2014, @2014]",
        "Interval[1 'g', 3 'g'] overlaps before Interval[1 'cm', 2 'cm']",
        "Interval[1 'cm', 2 'cm'] overlaps after Interval[1 'g', 3 'g']",
    ]
    for expression in expressions:
        assert isinstance(parse_expression(expression), BinaryExpression)

    translated = translate_cql(_cql_interval_part2_library())
    assert "intervalIncludedInPrecise" in str(translated["IncludedInPrecision"])
    assert "intervalContainsPrecise" in str(translated["DateTimePointIncludedDay"])
    assert "intervalIntersect" in str(translated["IntersectCheck"])
    assert "intervalMeets" in str(translated["MeetsCheck"])
    assert "intervalMeetsBefore" in str(translated["MeetsBefore"])
    assert "intervalMeetsAfter" in str(translated["MeetsAfter"])
    assert "intervalEquals" in translated["NotEqualCheck"].to_sql()
    assert "intervalEquivalent" in translated["NotEquivalentCheck"].to_sql()
    assert "cqlSameOrAfterP" in str(translated["OnAfter"])
    assert "cqlSameOrBeforeP" in str(translated["OnBefore"])
    assert "intervalStart" in str(translated["Overlaps"])
    assert "intervalStart" in str(translated["OverlapsBefore"])
    assert "intervalEnd" in str(translated["OverlapsAfter"])
    assert translated["PartialYearOverlapsDayNull"].to_sql() == "NULL"


def test_cql_interval_part2_translated_sql_matches_cpp_registration() -> None:
    translated = translate_cql(_cql_interval_part2_library())
    expected = {
        "IncludedInPrecision": (True,),
        "MeetsClosedOverlap": (False,),
        "OnAfterOpen": (True,),
        "OnBeforeOpen": (True,),
        "MeetsCheck": (True,),
        "DateTimeMeets": (True,),
        "MeetsAtHours": (True,),
        "MeetsDateTimeAtHours": (True,),
        "MeetsBefore": (True,),
        "DateTimeMeetsBefore": (True,),
        "MeetsAfter": (True,),
        "DateTimeMeetsAfter": (True,),
        "MeetsNullLow": (None,),
        "MeetsAfterNullHigh": (False,),
        "TimeProperContainsUncertain": (None,),
        "TimeProperInUncertain": (None,),
        "TimeProperContainsPrecisionUncertain": (None,),
        "TimeProperInPrecisionUncertain": (None,),
        "NotEqualCheck": (True,),
        "NotEquivalentCheck": (True,),
        "OnAfter": (True,),
        "OnBefore": (True,),
        "Overlaps": (True,),
        "OverlapsBefore": (True,),
        "OverlapsAfter": (True,),
        "DateTimePointIncludedDay": (True,),
        "PartialYearIncludedDayNull": (None,),
        "PartialYearOverlapsDayNull": (None,),
        "OnAfterPartialYearNull": (None,),
        "OnBeforePartialYearNull": (None,),
        "QuantityOverlapIncompatibleNull": (None,),
        "IntersectHalfOpenEmpty": (None,),
        "PartialYearOverlapsBeforeDayNull": (None,),
        "PartialYearOverlapsAfterDayNull": (None,),
        "QuantityOverlapsBeforeIncompatibleNull": (None,),
        "QuantityOverlapsAfterIncompatibleNull": (None,),
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
        (
            "SELECT intervalOverlapsPrecise(intervalFromBounds('2014','2014',true,true), "
            "intervalFromBounds('2014-06-01','2014-06-02',true,true), 'day')",
            [],
            (None,),
        ),
        (
            "SELECT intervalContainsPrecise(intervalFromBounds('2014-06-01T00','2014-06-01T01',true,true), "
            "'2014-06-01T12', 'day')",
            [],
            (True,),
        ),
        (
            "SELECT intervalContainsPrecise(intervalFromBounds('2014-01-01','2014-12-31',true,true), "
            "'2014', 'day')",
            [],
            (None,),
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


def test_cql_interval_part2_boundary_regressions_match_no_python_cpp() -> None:
    cases = [
        (
            "SELECT intervalEquivalent(NULL, NULL)",
            (True,),
        ),
        (
            "SELECT intervalEquivalent(NULL, intervalFromBounds('1', '2', true, true))",
            (False,),
        ),
        (
            "SELECT intervalEquivalent(intervalFromBounds('1', '2', true, true), NULL)",
            (False,),
        ),
        (
            "SELECT intervalIncludedIn(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014-01-01', '2014-12-31', true, true))",
            (None,),
        ),
        (
            "SELECT intervalIntersect(intervalFromBounds('__null__', '5', true, true), "
            "intervalFromBounds('3', '7', true, true))",
            ('{"low": "3", "high": "5", "lowClosed": true, "highClosed": true}',),
        ),
        (
            "SELECT intervalIntersect(intervalFromBounds('3', '__null__', true, true), "
            "intervalFromBounds('1', '5', true, true))",
            ('{"low": "3", "high": "5", "lowClosed": true, "highClosed": true}',),
        ),
        (
            "SELECT intervalIntersect(intervalFromBounds('1', '10', true, true), "
            "intervalFromBounds('5', '__null__', true, false))",
            ('{"low": "5", "high": null, "lowClosed": true, "highClosed": false}',),
        ),
        (
            "SELECT intervalIntersect(intervalFromBounds('1', '5', true, false), "
            "intervalFromBounds('5', '7', true, true))",
            (None,),
        ),
        (
            "SELECT intervalIntersect(intervalFromBounds('1', '5', true, true), "
            "intervalFromBounds('5', '7', true, true))",
            ('{"low": "5", "high": "5", "lowClosed": true, "highClosed": true}',),
        ),
        (
            "SELECT intervalMeetsBefore(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('3', '5', true, true))",
            (False,),
        ),
        (
            "SELECT intervalMeetsBefore(intervalFromBounds('1', '3', true, false), "
            "intervalFromBounds('3', '5', true, true))",
            (True,),
        ),
        (
            "SELECT intervalOnOrAfter(intervalFromBounds('3', '6', false, true), "
            "intervalFromBounds('1', '4', true, true))",
            (True,),
        ),
        (
            "SELECT intervalOnOrBefore(intervalFromBounds('1', '4', true, false), "
            "intervalFromBounds('3', '6', true, true))",
            (True,),
        ),
        (
            "SELECT intervalMeets(intervalFromBounds('T03', 'T04', true, true), "
            "intervalFromBounds('T05', 'T06', true, true))",
            (True,),
        ),
        (
            "SELECT intervalMeets(intervalFromBounds('2012-01-01T03', '2012-01-01T04', true, true), "
            "intervalFromBounds('2012-01-01T05', '2012-01-01T06', true, true))",
            (True,),
        ),
        (
            "SELECT intervalMeets(intervalFromBounds('__null__', '5', false, true), "
            "intervalFromBounds('__null__', '15', false, false))",
            (None,),
        ),
        (
            "SELECT intervalMeetsAfter(intervalFromBounds('__null__', '5', false, true), "
            "intervalFromBounds('11', '__null__', true, false))",
            (False,),
        ),
        (
            "SELECT intervalProperlyContains("
            "intervalFromBounds('T12:00:00.001', 'T21:59:59.999', true, true), 'T12:00:00')",
            (None,),
        ),
        (
            "SELECT intervalIncludesPrecise("
            "intervalFromBounds('T12:00:00.001', 'T21:59:59.999', true, true), "
            "intervalFromBounds('T12:00:00', 'T12:00:00', true, true), 'millisecond')",
            (None,),
        ),
        (
            "SELECT intervalOverlapsBefore(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014-06-01', '2014-06-02', true, true))",
            (None,),
        ),
        (
            "SELECT intervalOverlapsAfter(intervalFromBounds('2014-06-01', '2014-06-02', true, true), "
            "intervalFromBounds('2014', '2014', true, true))",
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


def test_cql_interval_part2_explorer_regressions_match_no_python_cpp() -> None:
    direct_cases = [
        (
            "SELECT intervalOnOrAfter(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014-06-01', '2014-06-02', true, true))",
            (None,),
        ),
        (
            "SELECT intervalOnOrBefore(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014-06-01', '2014-06-02', true, true))",
            (None,),
        ),
        (
            "SELECT intervalOverlaps(intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', "
            "'{\"value\":3,\"unit\":\"g\"}', true, true), "
            "intervalFromBounds('{\"value\":1,\"unit\":\"cm\"}', "
            "'{\"value\":2,\"unit\":\"cm\"}', true, true))",
            (None,),
        ),
        (
            "SELECT intervalOverlapsBefore(intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', "
            "'{\"value\":3,\"unit\":\"g\"}', true, true), "
            "intervalFromBounds('{\"value\":1,\"unit\":\"cm\"}', "
            "'{\"value\":2,\"unit\":\"cm\"}', true, true))",
            (None,),
        ),
        (
            "SELECT intervalOverlapsAfter(intervalFromBounds('{\"value\":1,\"unit\":\"cm\"}', "
            "'{\"value\":2,\"unit\":\"cm\"}', true, true), "
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', "
            "'{\"value\":3,\"unit\":\"g\"}', true, true))",
            (None,),
        ),
    ]

    quantity_interval_sql = (
        "SELECT intervalFromBounds('{\"value\":1000,\"unit\":\"mg\"}', "
        "'{\"value\":2,\"unit\":\"g\"}', true, true)"
    )
    quantity_intersect_sql = (
        "SELECT intervalIntersect("
        "intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', '{\"value\":3,\"unit\":\"g\"}', true, true), "
        "intervalFromBounds('{\"value\":1500,\"unit\":\"mg\"}', '{\"value\":2500,\"unit\":\"mg\"}', true, true))"
    )

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in direct_cases:
                assert py.execute(sql).fetchone() == expected
                assert cpp.execute(sql).fetchone() == expected
                assert no_py.execute(sql).fetchone() == expected

            for con in (py, cpp, no_py):
                quantity_interval = json.loads(con.execute(quantity_interval_sql).fetchone()[0])
                assert quantity_interval["low"] == {"value": 1000, "unit": "mg"}
                assert quantity_interval["high"] == {"value": 2, "unit": "g"}

                quantity_intersect = json.loads(con.execute(quantity_intersect_sql).fetchone()[0])
                assert quantity_intersect["low"] == {"value": 1500, "unit": "mg"}
                assert quantity_intersect["high"] == {"value": 2500, "unit": "mg"}
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part2_set_ops_incompatible_quantity_dimensions_null_cql16_skeptic() -> None:
    """CQL §9.3 / §19.12 / §19.15: set ops on intervals with incompatible
    quantity dimensions must return NULL, not raise.

    Regression for CQL-16 SKEPTIC QA-001/QA-002: intervalIntersect and
    intervalExcept crashed with TypeError because _normalize_for_compare
    returns the original dicts when pint raises DimensionalityError, then
    `l1 > l2` / `h1 < l2` failed on non-orderable dicts. The no-Python
    C++ path had a parallel bug in Interval::except_of, which returned
    interval1 unchanged when BoundValue::compare returned -2.
    """
    cases = [
        # Intersect of intervals with incompatible quantity dimensions
        (
            "SELECT intervalIntersect("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', '{\"value\":3,\"unit\":\"g\"}', true, true), "
            "intervalFromBounds('{\"value\":1,\"unit\":\"cm\"}', '{\"value\":2,\"unit\":\"cm\"}', true, true))",
            None,
        ),
        # Except of intervals with incompatible quantity dimensions
        (
            "SELECT intervalExcept("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', '{\"value\":3,\"unit\":\"g\"}', true, true), "
            "intervalFromBounds('{\"value\":1,\"unit\":\"cm\"}', '{\"value\":2,\"unit\":\"cm\"}', true, true))",
            None,
        ),
        # Sanity: compatible units still work for intersect
        (
            "SELECT intervalIntersect("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', '{\"value\":3,\"unit\":\"g\"}', true, true), "
            "intervalFromBounds('{\"value\":2,\"unit\":\"g\"}', '{\"value\":5,\"unit\":\"g\"}', true, true))",
            {"low": {"value": 2, "unit": "g"}, "high": {"value": 3, "unit": "g"},
             "lowClosed": True, "highClosed": True},
        ),
        # Sanity: compatible units still work for except
        (
            "SELECT intervalExcept("
            "intervalFromBounds('{\"value\":1,\"unit\":\"g\"}', '{\"value\":5,\"unit\":\"g\"}', true, true), "
            "intervalFromBounds('{\"value\":2,\"unit\":\"g\"}', '{\"value\":4,\"unit\":\"g\"}', true, true))",
            # iv2 splits iv1 → null per spec ("if second is properly contained within the first
            # and does not start or end it, this operator returns null")
            None,
        ),
    ]

    def _norm(row):
        """Compare parsed JSON structures; Python uses spaced json.dumps,
        C++ serializes compactly."""
        if row is None:
            return None
        val = row[0] if isinstance(row, tuple) else row
        if val is None:
            return None
        if isinstance(val, str) and val.strip().startswith("{"):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val
        return val

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in cases:
                assert _norm(py.execute(sql).fetchone()) == expected, (
                    f"PY mismatch for {sql}"
                )
                assert _norm(cpp.execute(sql).fetchone()) == expected, (
                    f"CPP mismatch for {sql}"
                )
                assert _norm(no_py.execute(sql).fetchone()) == expected, (
                    f"NO_PY mismatch for {sql}"
                )
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part2_dynamic_partial_fhir_points_keep_precision_uncertainty() -> None:
    cql = """library CQL16DynamicPartial version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Target: Interval[@2014-06-01, @2014-06-02]
define DynOverlapsDay:
  singleton from ([Observation] O return O.effective overlaps day of Target)
define DynOverlapsBeforeDay:
  singleton from ([Observation] O return O.effective overlaps before day of Target)
define DynOverlapsAfterDay:
  singleton from ([Observation] O return O.effective overlaps after day of Target)
"""
    population_sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(cql),
        output_columns={
            "overlaps_day": "DynOverlapsDay",
            "overlaps_before_day": "DynOverlapsBeforeDay",
            "overlaps_after_day": "DynOverlapsAfterDay",
        },
    )
    rows = [
        ("p1", "Patient", {"resourceType": "Patient", "id": "p1"}, "p1"),
        ("p2", "Patient", {"resourceType": "Patient", "id": "p2"}, "p2"),
        ("p3", "Patient", {"resourceType": "Patient", "id": "p3"}, "p3"),
        (
            "o1",
            "Observation",
            {
                "resourceType": "Observation",
                "id": "o1",
                "subject": {"reference": "Patient/p1"},
                "effectiveDateTime": "2014",
            },
            "p1",
        ),
        (
            "o2",
            "Observation",
            {
                "resourceType": "Observation",
                "id": "o2",
                "subject": {"reference": "Patient/p2"},
                "effectivePeriod": {"start": "2014-05-31", "end": "2014-06-01"},
            },
            "p2",
        ),
        (
            "o3",
            "Observation",
            {
                "resourceType": "Observation",
                "id": "o3",
                "subject": {"reference": "Patient/p3"},
                "effectivePeriod": {"start": "2014-06-02", "end": "2014-06-03"},
            },
            "p3",
        ),
    ]
    expected = [
        ("p1", None, None, None),
        ("p2", True, True, False),
        ("p3", True, False, True),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for con in (py, cpp, no_py):
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS resources (
                      id VARCHAR,
                      resourceType VARCHAR,
                      resource JSON,
                      patient_ref VARCHAR
                    )
                    """
                )
                con.execute("DELETE FROM resources")
                for resource_id, resource_type, resource, patient_ref in rows:
                    con.execute(
                        "INSERT INTO resources VALUES (?, ?, ?::JSON, ?)",
                        [resource_id, resource_type, json.dumps(resource), patient_ref],
                    )
                assert con.execute(population_sql).fetchall() == expected
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part2_mixed_precision_equality_uncertain_per_spec_cql16_historian() -> None:
    """CQL 1.5.3 §Equal (interval) + §Equal (Date/DateTime/Time).

    For Date, DateTime, or Time values, if one input has a value for a
    precision and the other does not, comparison stops and the result is
    null. For interval types, equality uses Start/End semantics, so
    mixed-precision temporal bounds make interval equality uncertain.

    Regression for CQL-16 HISTORIAN QA-001: `intervalEquals` and the
    translator-routed `!=` previously returned False/True (certain) for
    `Interval[@2014, @2014] = Interval[@2014-01-01, @2014-12-31]` instead
    of None (uncertain). `intervalEquivalent` and `!~` correctly returned
    False/True per Equivalent's always-true-or-false rule (uncertain maps
    to False, NOT False maps to True).
    """
    direct_cases = [
        # Year-prec vs day-prec Date interval equality → NULL (uncertain)
        (
            "SELECT intervalEquals(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014-01-01', '2014-12-31', true, true))",
            (None,),
        ),
        # Year-prec vs month-prec → NULL
        (
            "SELECT intervalEquals(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014-01', '2014-12', true, true))",
            (None,),
        ),
        # Same year-precision: certain True
        (
            "SELECT intervalEquals(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014', '2014', true, true))",
            (True,),
        ),
        # Different year: certain False
        (
            "SELECT intervalEquals(intervalFromBounds('2013', '2014', true, true), "
            "intervalFromBounds('2014', '2014', true, true))",
            (False,),
        ),
        # Same-precision Integer intervals still certain
        (
            "SELECT intervalEquals(intervalFromBounds('1', '5', true, true), "
            "intervalFromBounds('1', '5', true, true))",
            (True,),
        ),
        # Mixed-precision equivalent → False (always-true-or-false rule)
        (
            "SELECT intervalEquivalent(intervalFromBounds('2014', '2014', true, true), "
            "intervalFromBounds('2014-01-01', '2014-12-31', true, true))",
            (False,),
        ),
        # Spec example: null-high equivalent
        (
            "SELECT intervalEquivalent(intervalFromBounds('1', '__null__', true, true), "
            "intervalFromBounds('1', '__null__', true, true))",
            (True,),
        ),
        # Both intervals NULL → True (equivalent)
        (
            "SELECT intervalEquivalent(NULL, NULL)",
            (True,),
        ),
        # One NULL → False (not equivalent)
        (
            "SELECT intervalEquivalent(NULL, "
            "intervalFromBounds('1', '5', true, true))",
            (False,),
        ),
        # Semantic equality via Start/End: Interval[1, 6] = Interval(0, 6]
        (
            "SELECT intervalEquals(intervalFromBounds('1', '6', true, true), "
            "intervalFromBounds('0', '6', false, true))",
            (True,),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in direct_cases:
                assert py.execute(sql).fetchone() == expected, (
                    f"PY mismatch for {sql}"
                )
                assert cpp.execute(sql).fetchone() == expected, (
                    f"CPP mismatch for {sql}"
                )
                assert no_py.execute(sql).fetchone() == expected, (
                    f"NO_PY mismatch for {sql}"
                )
    finally:
        py.close()
        cpp.close()

    # End-to-end via translator: != and !~ for mixed-precision Date intervals
    cql = """library CQL16HistorianMixedPrecision version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MixedPrecisionEqual: Interval[@2014, @2014] = Interval[@2014-01-01, @2014-12-31]
define MixedPrecisionNotEqual: Interval[@2014, @2014] != Interval[@2014-01-01, @2014-12-31]
define MixedPrecisionEquivalent: Interval[@2014, @2014] ~ Interval[@2014-01-01, @2014-12-31]
define MixedPrecisionNotEquivalent: Interval[@2014, @2014] !~ Interval[@2014-01-01, @2014-12-31]
"""
    translated = translate_cql(cql)
    expected = {
        "MixedPrecisionEqual": (None,),
        "MixedPrecisionNotEqual": (None,),
        "MixedPrecisionEquivalent": (False,),
        "MixedPrecisionNotEquivalent": (True,),
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
                assert py_result == cpp_result == no_py_result, name
                assert py_result == expected[name], name
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part2_meets_precision_applied_symmetrically_cql16_explorer() -> None:
    """CQL-16 EXPLORER QA-001: meets <precision> of / meets before <precision> of /
    meets after <precision> of must apply precision truncation to BOTH operands.

    Per CQL 1.5.3 §Meets: "If precision is specified and the point type is a
    Date, DateTime, or Time type, comparisons used in the operation are
    performed at the specified precision." The translator previously truncated
    only the right operand (parser desugars ``day of X`` to ``day precision of
    X``), leaving the left operand at full DateTime precision and producing
    wrong answers when iv1's bounds were finer than the requested precision.
    """
    cql = """library CQL16ExplorerMeetsPrecision version '1.0.0'
using FHIR version '4.0.1'
context Patient
define MeetsDayAsymmetric: Interval[@2024-01-01T12:34, @2024-01-01T17:00] meets day of Interval[@2024-01-02T08:00, @2024-01-02T09:00]
define MeetsBeforeDayAsymmetric: Interval[@2024-01-01T12:34, @2024-01-01T17:00] meets before day of Interval[@2024-01-02T08:00, @2024-01-02T09:00]
define MeetsAfterDayAsymmetric: Interval[@2024-01-02T08:00, @2024-01-02T09:00] meets after day of Interval[@2024-01-01T12:34, @2024-01-01T17:00]
define MeetsHourExplicit: Interval[@T03:30, @T04:30] meets hour of Interval[@T05:00, @T06:00]
define MeetsDayControl: Interval[@2024-01-01, @2024-01-01] meets day of Interval[@2024-01-02, @2024-01-02]
define MeetsBeforeYear: Interval[@2014, @2014] meets before year of Interval[@2015, @2015]
define MeetsDayDisjoint: Interval[@2024-01-01T12:34, @2024-01-01T17:00] meets day of Interval[@2024-01-10T08:00, @2024-01-10T09:00]
define MeetsDayOverlap: Interval[@2024-01-01T12:34, @2024-01-02T17:00] meets day of Interval[@2024-01-02T08:00, @2024-01-02T09:00]
define MeetsYearVsDayUncertain: Interval[@2024, @2024] meets day of Interval[@2024-01-02T08:00, @2024-01-02T09:00]
define MeetsNoPrecision: Interval[1, 3] meets Interval[4, 6]
define MeetsBeforeNoPrecision: Interval[1, 3] meets before Interval[4, 6]
define MeetsAfterNoPrecision: Interval[4, 6] meets after Interval[1, 3]
"""
    translated = translate_cql(cql)
    expected = {
        "MeetsDayAsymmetric": (True,),
        "MeetsBeforeDayAsymmetric": (True,),
        "MeetsAfterDayAsymmetric": (True,),
        "MeetsHourExplicit": (True,),
        "MeetsDayControl": (True,),
        "MeetsBeforeYear": (True,),
        "MeetsDayDisjoint": (False,),
        "MeetsDayOverlap": (False,),
        "MeetsYearVsDayUncertain": (None,),
        "MeetsNoPrecision": (True,),
        "MeetsBeforeNoPrecision": (True,),
        "MeetsAfterNoPrecision": (True,),
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
                assert py_result == cpp_result == no_py_result, name
                assert py_result == expected[name], name
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
define MeetsClosedOverlap: Interval[1, 3] meets before Interval[3, 5]
define DateTimeMeets: Interval[DateTime(2012, 1, 5), DateTime(2012, 1, 25)] meets Interval[DateTime(2012, 1, 26), DateTime(2012, 1, 28)]
define MeetsAtHours: Interval[@T03, @T04] meets Interval[@T05, @T06]
define MeetsDateTimeAtHours: Interval[@2012-01-01T03, @2012-01-01T04] meets Interval[@2012-01-01T05, @2012-01-01T06]
define MeetsBefore: Interval[1, 3] meets before Interval[4, 6]
define DateTimeMeetsBefore: Interval[DateTime(2012, 1, 5), DateTime(2012, 1, 25)] meets before Interval[DateTime(2012, 1, 26), DateTime(2012, 1, 28)]
define MeetsAfter: Interval[4, 6] meets after Interval[1, 3]
define DateTimeMeetsAfter: Interval[DateTime(2012, 1, 26), DateTime(2012, 1, 28)] meets after Interval[DateTime(2012, 1, 5), DateTime(2012, 1, 25)]
define MeetsNullLow: Interval(null, 5] meets Interval(null, 15)
define MeetsAfterNullHigh: Interval(null, 5] meets after Interval[11, null)
define TimeProperContainsUncertain: Interval[@T12:00:00.001, @T21:59:59.999] properly includes @T12:00:00
define TimeProperInUncertain: @T12:00:00 properly included in Interval[@T12:00:00.001, @T21:59:59.999]
define TimeProperContainsPrecisionUncertain: Interval[@T12:00:00.001, @T21:59:59.999] properly includes millisecond of @T12:00:00
define TimeProperInPrecisionUncertain: @T12:00:00 properly included in millisecond of Interval[@T12:00:00.001, @T21:59:59.999]
define NotEqualCheck: Interval[1, 5] != Interval[1, 6]
define NotEquivalentCheck: Interval[1, 5] !~ Interval[1, 6]
define IntersectLowUnbounded: Interval[null as Integer, 5] intersect Interval[3, 7]
define IntersectHighUnbounded: Interval[3, null as Integer] intersect Interval[1, 5]
define IntersectHalfOpenEmpty: Interval[1, 5) intersect Interval[5, 7]
define OnAfterOpen: Interval(3, 6] on or after Interval[1, 4]
define OnBeforeOpen: Interval[1, 4) on or before Interval[3, 6]
define OnAfter: Interval[@2024-02-01, @2024-02-28] on or after day of Interval[@2024-01-01, @2024-01-31]
define OnBefore: Interval[@2024-01-01, @2024-01-31] on or before day of Interval[@2024-02-01, @2024-02-28]
define Overlaps: Interval[@2024-01-01, @2024-01-31] overlaps day of Interval[@2024-01-15, @2024-02-15]
define OverlapsBefore: Interval[@2024-01-01, @2024-01-31] overlaps before day of Interval[@2024-01-15, @2024-02-15]
define OverlapsAfter: Interval[@2024-01-15, @2024-02-15] overlaps after day of Interval[@2024-01-01, @2024-01-31]
define DateTimePointIncludedDay: @2014-06-01T12 included in day of Interval[@2014-06-01T00, @2014-06-01T01]
define PartialYearIncludedDayNull: Interval[@2014, @2014] included in day of Interval[@2014-01-01, @2014-12-31]
define PartialYearOverlapsDayNull: Interval[@2014, @2014] overlaps day of Interval[@2014-06-01, @2014-06-02]
define PartialYearOverlapsBeforeDayNull: Interval[@2014, @2014] overlaps before day of Interval[@2014-06-01, @2014-06-02]
define PartialYearOverlapsAfterDayNull: Interval[@2014-06-01, @2014-06-02] overlaps after day of Interval[@2014, @2014]
define OnAfterPartialYearNull: Interval[@2014, @2014] on or after Interval[@2014-06-01, @2014-06-02]
define OnBeforePartialYearNull: Interval[@2014, @2014] on or before Interval[@2014-06-01, @2014-06-02]
define QuantityOverlapIncompatibleNull: Interval[1 'g', 3 'g'] overlaps Interval[1 'cm', 2 'cm']
define QuantityOverlapsBeforeIncompatibleNull: Interval[1 'g', 3 'g'] overlaps before Interval[1 'cm', 2 'cm']
define QuantityOverlapsAfterIncompatibleNull: Interval[1 'cm', 2 'cm'] overlaps after Interval[1 'g', 3 'g']
"""
