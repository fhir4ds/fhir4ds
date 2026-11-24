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


# CQL 1.5.3 (§Time): "Although the milliseconds are specified with a separate
# component, seconds and milliseconds are combined and represented as a Decimal
# for the purposes of comparison ... When milliseconds are null, they are
# combined as .0 ... This is true of all comparison operations for time values
# ... or when comparison is performed as part of other operations such as
# interval meets and overlaps."
#
# AMUX-171 applies that rule to TIME interval boundaries
# (fhir4ds/cql/duckdb/udf/interval.py::_precision_aware_compare).  DateTime
# bounds are deliberately exempt: the official fixture
# CqlIntervalOperatorsTest.xml::DateTimeIncludedInNull pins interval-boundary
# second-vs-millisecond mismatch as UNCERTAIN, and fixtures outrank prose.
#
# The bundled C++ engine implements the §Time rule as of the AMUX-171
# rebuild (extensions/cql/src/cql/interval.cpp compare_interval_order_nullable
# / bound_equals_nullable), so the no-Python surface agrees with the Python
# authority and no stale map is needed.


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
        # Official fixture TestMeetsAfterNull pins this exact expression as
        # null: the open/unknown null boundaries (low of the left operand,
        # high of the right operand) make the comparison indeterminate.
        "MeetsAfterNullHigh": (None,),
        "TimeProperContainsUncertain": (False,),
        "TimeProperInUncertain": (False,),
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
            # Official fixture TestMeetsAfterNull: open/unknown null bounds
            # make meets-after indeterminate -> null (not false).
            (None,),
        ),
        (
            "SELECT intervalProperlyContains("
            "intervalFromBounds('T12:00:00.001', 'T21:59:59.999', true, true), 'T12:00:00')",
            # CQL 1.5.3 §Time: null milliseconds combine as .0, so the point is
            # 12:00:00.000 — before the closed start — hence FALSE (was NULL
            # before the combined-precision rule; cql-tests PR #184).
            (False,),
            # Rebuilt C++ engine implements the same §Time rule (AMUX-171).
            (False,),
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
            for case in cases:
                sql, expected = case[0], case[1]
                # Optional third element pins an engine-specific no-Python (C++
                # only) expectation where the bundled binary has not been
                # rebuilt with a newer rule.
                no_py_expected = case[2] if len(case) > 2 else expected
                assert py.execute(sql).fetchone() == expected
                assert cpp.execute(sql).fetchone() == expected
                assert no_py.execute(sql).fetchone() == no_py_expected
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
                # CQL-17 HISTORIAN (2nd launch) QA-004: Quantity bounds use
                # the canonical Quantity JSON shape (value/unit/code/system)
                # on every engine, matching Width/Size output.
                quantity_interval = json.loads(con.execute(quantity_interval_sql).fetchone()[0])
                assert quantity_interval["low"] == {
                    "value": 1000.0,
                    "unit": "mg",
                    "code": "mg",
                    "system": "http://unitsofmeasure.org",
                }
                assert quantity_interval["high"] == {
                    "value": 2.0,
                    "unit": "g",
                    "code": "g",
                    "system": "http://unitsofmeasure.org",
                }

                quantity_intersect = json.loads(con.execute(quantity_intersect_sql).fetchone()[0])
                assert quantity_intersect["low"] == {
                    "value": 1500.0,
                    "unit": "mg",
                    "code": "mg",
                    "system": "http://unitsofmeasure.org",
                }
                assert quantity_intersect["high"] == {
                    "value": 2500.0,
                    "unit": "mg",
                    "code": "mg",
                    "system": "http://unitsofmeasure.org",
                }
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
            {"low": {"value": 2.0, "unit": "g", "code": "g",
                     "system": "http://unitsofmeasure.org"},
             "high": {"value": 3.0, "unit": "g", "code": "g",
                      "system": "http://unitsofmeasure.org"},
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


def test_cql_interval_part2_null_bound_sentinels_and_in_keyword_cql16_skeptic_2026_08() -> None:
    """CQL-16 SKEPTIC (2026-08-22) regressions.

    QA-001: ``in`` between two intervals must lower to intervalIncludedIn
    (interval-interval Included In overload accepted by the CQL grammar and
    the reference InEvaluator); previously it fell into the point-in-interval
    BETWEEN lowering and raised a DuckDB BinderException.

    QA-003: closed null interval bounds sentinelize to the min/max of the
    point type (CQL 1.5 §9.14 Start / §9.15 End, reference Interval.start/
    .end getters), so Meets / On Or After / On Or Before return determined
    results instead of null. Successor of the maximum temporal sentinel is
    null (Appendix C overflow rule), so meets with a closed null high bound
    is false, and the temporal sentinel arithmetic must not raise.
    """
    cql = """library CQL16Skeptic2026_08 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define InIntervalTrue: Interval[2, 3] in Interval[1, 5]
define InIntervalFalse: Interval[2, 7] in Interval[1, 5]
define InIntervalPrecision: Interval[@2024-01-15, @2024-01-20] in day of Interval[@2024-01-01, @2024-01-31]
define InIntervalFromList: First({ Interval[2, 4], Interval[9, 10] }) in Interval[1, 5]
define MeetsNullHighFalse: Interval[1, null] meets Interval[6, 10]
define MeetsNullLowFalse: Interval[1, 5] meets Interval[null, 3]
define MeetsTemporalNullHighFalse: Interval[@2024-01-01, null] meets Interval[@2025-01-01, @2025-06-01]
define MeetsOpenNullHighNull: Interval[1, null) meets Interval[6, 10]
define OnOrAfterNullLowFalse: Interval[null, 5] on or after Interval[1, 3]
define OnOrAfterNullHighFalse: Interval[6, 10] on or after Interval[1, null]
define OnOrAfterTemporalNullHighFalse: Interval[@2025-01-01, @2025-06-01] on or after Interval[@2024-01-01, null]
define OnOrBeforeNullLowFalse: Interval[null, 3] on or before Interval[1, 5]
define OnOrBeforeUnboundedHighTrue: Interval[1, 5] on or before Interval[6, null]
"""
    translated = translate_cql(cql)
    expected = {
        "InIntervalTrue": (True,),
        "InIntervalFalse": (False,),
        "InIntervalPrecision": (True,),
        "InIntervalFromList": (True,),
        "MeetsNullHighFalse": (False,),
        "MeetsNullLowFalse": (False,),
        "MeetsTemporalNullHighFalse": (False,),
        "MeetsOpenNullHighNull": (None,),
        "OnOrAfterNullLowFalse": (False,),
        "OnOrAfterNullHighFalse": (False,),
        "OnOrAfterTemporalNullHighFalse": (False,),
        "OnOrBeforeNullLowFalse": (False,),
        "OnOrBeforeUnboundedHighTrue": (True,),
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
                assert py_result == cpp_result == no_py_result, (
                    name,
                    py_result,
                    cpp_result,
                    no_py_result,
                )
                assert py_result == expected[name], (name, py_result)
    finally:
        py.close()
        cpp.close()


def test_cql_point_in_interval_open_null_bound_is_unknown_fhir4_40() -> None:
    """FHIR4-40: point `in` an OPEN-null-bound interval is UNKNOWN, not FALSE.

    Official fixture
    ``CqlIntervalOperatorsTest.xml::TestIntegerInUnknownIntervalNull`` pins
    ``5 in Interval(null, null)`` as null; its sibling
    ``TestIntegerInMaxIntervalTrue`` pins ``5 in Interval[null, null]`` as
    true. CQL 1.5.3 §In (Interval) states the rule that separates them:

        "For open interval boundaries, exclusive comparison operators are
        used. For closed interval boundaries, if the interval boundary is
        null, the result of the boundary comparison is considered true."

    So a CLOSED null bound drops out of the conjunction (treated as true,
    i.e. the point-type extremum via §9.14/§9.15), while an OPEN null bound
    is an exclusive comparison against an unknown value -> the comparison is
    UNKNOWN and three-valued AND decides the rest:

        NULL AND TRUE  -> null   (e.g. 5 in Interval(null, 10])
        NULL AND FALSE -> false  (e.g. 500 in Interval(null, 10])

    ``_translate_in_op`` used to drop open-null bound comparisons altogether
    (returning the definite verdict of the other side) and to emit a literal
    FALSE when both bounds were open, so the fixture got false instead of
    null.

    The precision-qualified form (``5 in day of Interval(null, null)``) used
    to fall through to the ``intervalContainsPrecise`` UDF, which lacked the
    ``_open_null_bound_uncertain`` guard its sibling relationship predicates
    carry. FHIR4-42 closed that gap; see
    ``test_cql_interval_contains_open_null_bound_is_unknown_fhir4_42``.
    """
    cql = """library FHIR4_40 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define OpenBothNull: 5 in Interval(null, null)
define ClosedBothNull: 5 in Interval[null, null]
define NullPointClosedBothNull: null in Interval[null, null]
define OpenLowNull: 5 in Interval(null, 10]
define ClosedLowNull: 5 in Interval[null, 10]
define PointBelowOpenInterval: 500 in Interval(null, 10]
define OpenHighNull: 5 in Interval[0, null)
define ClosedHighNull: 5 in Interval[0, null]
define TrueAndOpenHighNull: 500 in Interval[0, null)
define OpenBothNullTemporal: @2024-06-15 in Interval(null, @2024-12-31]
define ClosedBothNullTemporal: @2024-06-15 in Interval[null, @2024-12-31]
define OrdinaryClosedInterval: 5 in Interval[1, 10]
define OrdinaryOpenInterval: 5 in Interval(1, 5]
"""
    translated = translate_cql(cql)
    expected = {
        # The fixture cell: open null bounds -> unknown.
        "OpenBothNull": (None,),
        # The sibling fixture cell: closed null bounds -> the maximum
        # interval, so a non-null point IS contained.
        "ClosedBothNull": (True,),
        # CQL §In (Interval): "If the first argument is null, the result is
        # null" — checked before the boundary rule.
        "NullPointClosedBothNull": (None,),
        # Open low: NULL AND (5 <= 10) -> unknown.
        "OpenLowNull": (None,),
        # Closed low: the boundary comparison is considered true.
        "ClosedLowNull": (True,),
        # 500 is outside on the determinate side: NULL AND FALSE -> false.
        "PointBelowOpenInterval": (False,),
        # Open high: (5 >= 0) AND NULL -> unknown.
        "OpenHighNull": (None,),
        "ClosedHighNull": (True,),
        # (500 >= 0) AND NULL -> unknown (not false: the open side is
        # unknown, so it cannot be decided).
        "TrueAndOpenHighNull": (None,),
        "OpenBothNullTemporal": (None,),
        "ClosedBothNullTemporal": (True,),
        # Unaffected controls.
        "OrdinaryClosedInterval": (True,),
        "OrdinaryOpenInterval": (True,),
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
                assert py_result == cpp_result == no_py_result, (
                    name,
                    py_result,
                    cpp_result,
                    no_py_result,
                )
                assert py_result == expected[name], (name, sql, py_result)
    finally:
        py.close()
        cpp.close()


def test_cql_interval_contains_open_null_bound_is_unknown_fhir4_42() -> None:
    """FHIR4-42: containment through an OPEN-null-bound interval is UNKNOWN.

    ``intervalContains`` / ``intervalContainsPrecise`` treated a null bound as
    unconditionally unbounded, so an OPEN null bound answered a definite
    true/false. Every sibling relationship predicate (``intervalOverlaps``,
    ``intervalIncludes``, ``intervalProperlyContains``, ``intervalMeets``,
    ``intervalStartsSame``, ...) already carried
    ``_open_null_bound_uncertain``, and CQL 1.5.3 §In (Interval) scopes the
    "a null boundary counts as true" escape hatch to CLOSED boundaries only:

        "For open interval boundaries, exclusive comparison operators are
        used. For closed interval boundaries, if the interval boundary is
        null, the result of the boundary comparison is considered true."

    A CLOSED null bound is the point-type extremum (§9.14/§9.15), so it stays
    determined (``5 in day of Interval[null, null]`` is still true). An OPEN
    null bound is an exclusive comparison against an unknown value, so the
    boundary comparison is NULL and three-valued AND decides:

        NULL AND TRUE  -> null   (5 in day of Interval(null, 10])
        NULL AND FALSE -> false  (500 in day of Interval(null, 10])

    DOCTRINE (one-sided FHIR Periods). ``collapse_intervals`` maps a Period
    with only ``end`` onto an OPEN null low ("the start is UNKNOWN": ``start
    of`` is null and Min/Max ignore it) and a Period with only ``start`` onto
    a CLOSED null high ("the period is ongoing": ``end of`` is the point-type
    maximum, so ``overlaps`` stays determined, CMS145). Only the OPEN half
    becomes UNKNOWN: an unknown start cannot be claimed to contain a point,
    while an ongoing period genuinely does extend past its start. That
    keeps the asymmetric-Period doctrine intact in both directions and makes
    containment agree with ``intervalOverlaps``/``intervalProperlyContains``,
    which already returned null for the same one-sided shape.

    DQM is the referee for the one-sided-Period family: qi-core-2025 47/47 and
    us-core-2025 73/73 are unchanged, and an instrumentation pass over both
    suites found ZERO containment calls whose container carried an open null
    bound in either corpus.
    """
    cql = """library FHIR4_42 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define OpenBothNullPrecise: 5 in day of Interval(null, null)
define OpenBothNullPlain: 5 in Interval(null, null)
define ClosedBothNullPrecise: 5 in day of Interval[null, null]
define ClosedBothNullPlain: 5 in Interval[null, null]
define OrdinaryClosed: 5 in day of Interval[1, 5]
define OrdinaryOpenBounded: 5 in day of Interval(1, 5]
define OpenLowNullPrecise: 5 in day of Interval(null, 10]
define PointOutsideOpenLowNull: 500 in day of Interval(null, 10]
define OpenHighNullPrecise: 5 in day of Interval[0, null)
define PointInsideOpenHighNull: 500 in day of Interval[0, null)
define ClosedLowNull: 5 in day of Interval[null, 10]
define ClosedHighNull: 5 in day of Interval[0, null]
define NullPointOpenBothNull: null in day of Interval(null, null)
define TemporalTypedNullOpenHigh: @2024-06-15 in day of Interval[null as Date, null as Date)
define TemporalClosedHighNull: @2024-06-15 in day of Interval[null as Date, null as Date]
define TemporalOpenBothBounded: @2024-06-15 in day of Interval(@2024-01-01, @2024-12-31)
"""
    translated = translate_cql(cql)
    expected = {
        # The headline cell: both bounds open + null -> unknown.
        "OpenBothNullPrecise": (None,),
        # FHIR4-40's cell, unchanged: closed null bounds are the maximum
        # interval, so a non-null point IS contained.
        "OpenBothNullPlain": (None,),
        "ClosedBothNullPrecise": (True,),
        "ClosedBothNullPlain": (True,),
        # Unaffected controls.
        "OrdinaryClosed": (True,),
        "OrdinaryOpenBounded": (True,),
        # NULL AND (5 <= 10) -> unknown.
        "OpenLowNullPrecise": (None,),
        # NULL AND FALSE -> false.
        "PointOutsideOpenLowNull": (False,),
        # (5 >= 0) AND NULL -> unknown.
        "OpenHighNullPrecise": (None,),
        # (500 >= 0) AND NULL -> unknown, not false.
        "PointInsideOpenHighNull": (None,),
        # Closed null bounds stay determined.
        "ClosedLowNull": (True,),
        "ClosedHighNull": (True,),
        # §In: a null point -> null, checked before the boundary rule.
        "NullPointOpenBothNull": (None,),
        # Temporal point types follow the same open/closed split.
        "TemporalTypedNullOpenHigh": (None,),
        "TemporalClosedHighNull": (True,),
        "TemporalOpenBothBounded": (True,),
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
                assert py_result == cpp_result, (name, sql, py_result, cpp_result)
                assert py_result == expected[name], (name, sql, py_result)
                assert no_py_result == expected[name], (name, sql, no_py_result)
    finally:
        py.close()
        cpp.close()




def _fh42_native_guard_current(con: duckdb.DuckDBPyConnection) -> bool:
    """True when the loaded cql extension implements the FHIR4-42 guard."""
    row = con.execute(
        "SELECT intervalContainsPrecise("
        "'{\"low\":null,\"high\":\"2024-06-01\",\"lowClosed\":false,"
        "\"highClosed\":true}', '2024-01-01', 'day')"
    ).fetchone()[0]
    return row is None


#: One-sided FHIR Period shapes, exactly as ``collapse_intervals`` renders them
#: from ``raw`` period JSON. ``end``-only keeps an OPEN null low (unknown
#: start); ``start``-only keeps a CLOSED null high (ongoing) - the asymmetric
#: root-AGENTS.md doctrine pinned by CMS645 (unknown start / Min-Max) and
#: CMS145 (ongoing high / overlaps).
_FHIR4_42_ONE_SIDED_PERIOD_CASES: dict[str, tuple[str, str, bool | None, bool | None]] = {
    # label: (collapsed interval JSON, point, contains, containsPrecise(day))
    "endOnlyOpenLowBefore": (
        '{"low":null,"high":"2024-06-01","lowClosed":false,"highClosed":true}',
        "2024-01-01",
        None,
        None,
    ),
    "endOnlyOpenLowAfter": (
        '{"low":null,"high":"2024-06-01","lowClosed":false,"highClosed":true}',
        "2024-12-01",
        False,
        False,
    ),
    "startOnlyClosedHighAfter": (
        '{"low":"2024-06-01","high":null,"lowClosed":true,"highClosed":true}',
        "2024-12-01",
        True,
        True,
    ),
    "startOnlyClosedHighBefore": (
        '{"low":"2024-06-01","high":null,"lowClosed":true,"highClosed":true}',
        "2024-01-01",
        False,
        False,
    ),
}

#: Stale no-Python values for the one-sided cases the guard changes.

def test_cql_interval_contains_one_sided_period_doctrine_fhir4_42() -> None:
    """FHIR4-42: one-sided FHIR Periods through containment (the doctrine pin).

    ``collapse_intervals`` is what turns real FHIR Periods into interval JSON,
    and it applies the asymmetric one-sided-Period doctrine: a missing ``end``
    is ONGOING (closed null high) while a missing ``start`` is UNKNOWN (open
    null low). Containment must honour that asymmetry rather than flattening
    both to "unbounded":

    * ``{"end": X}`` -> open null low -> unknown start -> containment UNKNOWN.
    * ``{"start": X}`` -> closed null high -> ongoing -> containment DEFINED.

    The second half is load-bearing (CMS145 active-beta-blocker intervals), so
    this pins that the guard does NOT leak into the closed-null shape.
    """
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for label, (iv, point, expected, expected_precise) in (
                _FHIR4_42_ONE_SIDED_PERIOD_CASES.items()
            ):
                for fn, prec, want in (
                    ("intervalContains", None, expected),
                    ("intervalContainsPrecise", "day", expected_precise),
                ):
                    call = (
                        f"{fn}('{iv}', '{point}')"
                        if prec is None
                        else f"{fn}('{iv}', '{point}', '{prec}')"
                    )
                    sql = f"SELECT {call}"
                    py_row = py.execute(sql).fetchone()
                    cpp_row = cpp.execute(sql).fetchone()
                    no_py_row = no_py.execute(sql).fetchone()
                    assert py_row == cpp_row == (want,), (label, fn, py_row, cpp_row, want)
                    assert no_py_row == (want,), (label, fn, no_py_row, want)

            # The doctrine is produced by collapse_intervals itself: prove the
            # two one-sided shapes it emits are the ones pinned above.
            end_only = py.execute(
                "SELECT collapse_intervals('[{\"end\":\"2024-06-01\"}]')"
            ).fetchone()[0]
            start_only = py.execute(
                "SELECT collapse_intervals('[{\"start\":\"2024-06-01\"}]')"
            ).fetchone()[0]
            assert json.loads(end_only)[0]["lowClosed"] is False, end_only
            assert json.loads(end_only)[0]["low"] is None, end_only
            assert json.loads(start_only)[0]["highClosed"] is True, start_only
            assert json.loads(start_only)[0]["high"] is None, start_only

            # includes-precise delegates to contains-precise, so it now agrees
            # with plain intervalIncludes (which already answered null for the
            # same open-null container). That internal inconsistency is part of
            # the fix; it is NOT an expansion of the guard's scope.
            other = '{"low":"2024-01-01","high":"2024-01-02","lowClosed":true,"highClosed":true}'
            end_only_iv = '{"low":null,"high":"2024-06-01","lowClosed":false,"highClosed":true}'
            includes_sql = f"SELECT intervalIncludes('{end_only_iv}', '{other}')"
            includes_precise_sql = (
                f"SELECT intervalIncludesPrecise('{end_only_iv}', '{other}', 'day')"
            )
            assert py.execute(includes_sql).fetchone() == (None,)
            assert py.execute(includes_precise_sql).fetchone() == (None,)
            assert cpp.execute(includes_precise_sql).fetchone() == (None,)
            assert no_py.execute(includes_precise_sql).fetchone() == (None,)
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part2_long_and_quantity_sentinels_cql16_historian_2026_08() -> None:
    """CQL-16 HISTORIAN (2026-08-22) regressions.

    QA-001: Long intervals with closed null bounds sentinel at the int64
    min/max of the Long point type (CQL 1.5 §9.14 Start / §9.15 End;
    reference Constants.MIN_LONG/MAX_LONG). Authored L-ness is erased at
    translation, so the magnitude of the peer bound (beyond int32) is the
    Long signal. Successor of Long max is null (Appendix C), so meets at the
    sentinel boundary is null-uncertain rather than a wrong determined true.

    QA-002: Quantity intervals with closed null bounds sentinel to
    Quantity(MIN_DECIMAL/MAX_DECIMAL, unit) per the reference Interval.start/
    .end getters, so On Or Before / On Or After / Meets return determined
    results instead of null.
    """
    cql = """library CQL16Historian2026_08 version '1.0.0'
using FHIR version '4.0.1'
context Patient
define LongEnd: end of Interval[5000000000L, null]
define LongStart: start of Interval[null, 5000000000L]
define LongMeetsFalse: Interval[5000000000L, null] meets Interval[2147483648L, 2147483649L]
define LongMeetsBeforeOverflowFalse: Interval[5000000000L, null] meets before Interval[9223372036854775807L, 9223372036854775807L]
define TemporalMeetsBeforeOverflowFalse: Interval[@2024-01-01, null] meets before Interval[@9999-12-31, @9999-12-31]
define LongMeetsMaxOverflowFalse: Interval[5000000000L, null] meets Interval[9223372036854775807L, 9223372036854775807L]
define LongOnOrBeforeFalse: Interval[5000000000L, null] on or before Interval[2147483648L, 2147483648L]
define LongOnOrBeforeTrue: Interval[null, 5000000000L] on or before Interval[6000000000L, 7000000000L]
define QtyOnOrBeforeFalse: Interval[1 'g', null] on or before Interval[2 'g', 3 'g']
define QtyOnOrAfterFalse: Interval[null, 5 'g'] on or after Interval[6 'g', 7 'g']
define QtyMeetsNullLowFalse: Interval[null, 4 'g'] meets Interval[5 'g', 6 'g']
define QtyOverlapsNullLowTrue: Interval[null, 5 'g'] overlaps Interval[1 'g', 2 'g']
define QtyIncludedInNullLowTrue: Interval[2 'g', 3 'g'] included in Interval[null, 5 'g']
"""
    translated = translate_cql(cql)
    expected = {
        "LongEnd": ("9223372036854775807",),
        "LongStart": ("-9223372036854775808",),
        "LongMeetsFalse": (False,),
        # Successor of the Long max sentinel overflows (Appendix C); the pinned
        # CQL-16 SKEPTIC convention (reference isMax guard) lowers to false.
        "LongMeetsBeforeOverflowFalse": (False,),
        "TemporalMeetsBeforeOverflowFalse": (False,),
        "LongMeetsMaxOverflowFalse": (False,),
        "LongOnOrBeforeFalse": (False,),
        "LongOnOrBeforeTrue": (True,),
        "QtyOnOrBeforeFalse": (False,),
        "QtyOnOrAfterFalse": (False,),
        "QtyMeetsNullLowFalse": (False,),
        "QtyOverlapsNullLowTrue": (True,),
        "QtyIncludedInNullLowTrue": (True,),
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
                assert py_result == cpp_result == no_py_result, (
                    name,
                    py_result,
                    cpp_result,
                    no_py_result,
                )
                assert py_result == expected[name], (name, py_result)
    finally:
        py.close()
        cpp.close()


def test_cql_interval_part2_native_effective_bounds_and_cross_numeric_parity() -> None:
    """CQL-16 EXPLORER regression coverage (2026-08-22).

    Two native-only defects fixed dual-engine:
    - §9.9 Intersect must use effective Start/End bounds (§9.14/§9.15):
      open discrete bounds step to successor/predecessor and the result
      bounds are closed (reference IntersectEvaluator).
    - §2 implicit numeric conversions: Integer and Decimal interval bounds
      are comparable across types; the native ``BoundValue::compare`` type
      gate previously returned incomparable (-2), yielding SQL NULL — and
      wrong deterministic FALSE for overlaps/included-in — in no-Python
      mode.
    """
    cases = [
        # Effective-bound intersect (open bounds participate via succ/pred).
        (
            "SELECT intervalIntersect(intervalFromBounds('1', '5', true, false), "
            "intervalFromBounds('4', '8', true, true))",
            ('{"low": "4", "high": "4", "lowClosed": true, "highClosed": true}',),
        ),
        (
            "SELECT intervalIntersect(intervalFromBounds('1', '5', true, false), "
            "intervalFromBounds('3', '7', false, true))",
            ('{"low": "4", "high": "4", "lowClosed": true, "highClosed": true}',),
        ),
        # Integer vs Decimal bounds across the part-2 family.
        (
            "SELECT intervalMeets(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('4.00000001', '6', true, true))",
            (False,),
        ),
        (
            "SELECT intervalOverlaps(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('2.5', '5', true, true))",
            (True,),
        ),
        (
            "SELECT intervalOnOrBefore(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('3.5', '6', true, true))",
            (True,),
        ),
        (
            "SELECT intervalIntersect(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('2.5', '5', true, true))",
            ('{"low": "2.5", "high": "3", "lowClosed": true, "highClosed": true}',),
        ),
        (
            "SELECT intervalIncludedIn(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('0.5', '5', true, true))",
            (True,),
        ),
        (
            "SELECT intervalEquivalent(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('1.0', '3.0', true, true))",
            (True,),
        ),
        (
            "SELECT intervalOverlapsBefore(intervalFromBounds('1', '3', true, true), "
            "intervalFromBounds('2.5', '5', true, true))",
            (True,),
        ),
        (
            "SELECT intervalOverlapsAfter(intervalFromBounds('2.5', '5', true, true), "
            "intervalFromBounds('1', '3', true, true))",
            (True,),
        ),
    ]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for sql, expected in cases:
                assert py.execute(sql).fetchone() == expected, sql
                assert cpp.execute(sql).fetchone() == expected, sql
                assert no_py.execute(sql).fetchone() == expected, sql
    finally:
        py.close()
        cpp.close()


def test_cql_interval_equivalent_is_two_valued_for_open_null_bounds_rev004() -> None:
    """CQL §9.7 equivalence is two-valued: `~` on intervals never returns NULL.

    An open null bound means UNBOUNDED, which is perfectly comparable —
    ``Interval[1, null)`` is equivalent to itself and not to ``Interval[1, 2]``.
    The Python UDF used to return None for any open-null operand (added by the
    895f3616d59 "open-null bounds are UNKNOWN" sweep), so `~`/`!~` produced NULL
    where the spec requires true/false. The C++ surface never had that guard,
    so this was also a dual-engine divergence (review REV-004).
    """
    cases = [
        # open LOW bound
        (
            "intervalEquivalent(intervalFromBounds(NULL,'5',false,true), "
            "intervalFromBounds(NULL,'5',false,true))",
            True,
        ),
        (
            "intervalEquivalent(intervalFromBounds(NULL,'5',false,true), "
            "intervalFromBounds(NULL,'6',false,true))",
            False,
        ),
        # open HIGH bound
        (
            "intervalEquivalent(intervalFromBounds('1',NULL,true,false), "
            "intervalFromBounds('1',NULL,true,false))",
            True,
        ),
        (
            "intervalEquivalent(intervalFromBounds('1',NULL,true,false), "
            "intervalFromBounds('1','2',true,true))",
            False,
        ),
        # CLOSED null bounds stay equivalent to each other
        (
            "intervalEquivalent(intervalFromBounds('1',NULL,true,true), "
            "intervalFromBounds('1',NULL,true,true))",
            True,
        ),
        # plain intervals unchanged
        (
            "intervalEquivalent(intervalFromBounds('1','2',true,true), "
            "intervalFromBounds('1','2',true,true))",
            True,
        ),
    ]
    for con_factory in (_python_only_connection, _cpp_connection):
        con = con_factory()
        try:
            for sql_fragment, expected in cases:
                row = con.execute(f"SELECT {sql_fragment}").fetchone()
                assert row[0] is expected, (
                    f"{con_factory.__name__}: {sql_fragment} -> {row[0]!r}, "
                    f"expected {expected!r} (equivalence must never be NULL)"
                )
        finally:
            con.close()


class TestExternalReviewB5IntervalSemantics:
    """Regression coverage for the 2026-11-13 external translator review,
    batch B5 (TRIAGE_cql_review_20261113.md): EXP1-007 (overlaps
    decomposition ignored low-closedness), EXP2-005 (ends timing phrases
    compared against raw interval JSON), REV-004 refined (interval
    equivalence treated open-null and closed-null bounds as equal)."""

    def _exec(self, expression: str):
        from fhir4ds.cql import translate_cql
        import duckdb
        from fhir4ds.cql.duckdb import register

        con = duckdb.connect()
        register(con)
        res = translate_cql(
            f"library L\ncontext Unfiltered\ndefine T: {expression}"
        )
        v = next(iter(res.values()))
        sql = v.to_sql() if hasattr(v, "to_sql") else str(v)
        return con.execute(f"SELECT ({sql})").fetchone()[0]

    def test_overlaps_respects_low_closedness(self):
        # EXP1-007: shared endpoint with an OPEN low bound on either side is
        # NOT an overlap (the shared point is excluded from that interval).
        assert self._exec(
            "Interval(@2020-01-05, @2020-01-10] overlaps Interval[@2020-01-01, @2020-01-05]"
        ) is False
        assert self._exec(
            "Interval[@2020-01-05, @2020-01-10] overlaps Interval[@2020-01-01, @2020-01-05]"
        ) is True
        assert self._exec(
            "Interval[@2020-01-01, @2020-01-05) overlaps Interval[@2020-01-05, @2020-01-10]"
        ) is False
        assert self._exec(
            "Interval(@2020-01-01, @2020-01-04] overlaps Interval[@2020-01-05, @2020-01-10]"
        ) is False

    def test_ends_timing_phrases_extract_interval_operand_bounds(self):
        # EXP2-005: an interval right operand must reduce to its bound — the
        # old form compared end(left) against the raw interval JSON text,
        # making '2099-12-31' <= '{"low":...' lexicographically true.
        assert self._exec(
            "Interval[@2025-01-01, @2099-12-31] ends on or before Interval[@2020-01-01, @2020-06-01]"
        ) is False
        # ends on or before B := end(A) <= start(B) → identical intervals False
        assert self._exec(
            "Interval[@2020-01-01, @2020-06-01] ends on or before Interval[@2020-01-01, @2020-06-01]"
        ) is False
        assert self._exec(
            "Interval[@2019-01-01, @2019-06-01] ends on or before Interval[@2020-01-01, @2020-06-01]"
        ) is True
        assert self._exec(
            "Interval[@2021-01-01, @2021-06-01] ends on or after Interval[@2020-01-01, @2020-06-01]"
        ) is True
        assert self._exec(
            "Interval[@2019-01-01, @2019-06-01] ends before Interval[@2020-01-01, @2020-06-01]"
        ) is True
        assert self._exec(
            "Interval[@2021-01-01, @2021-06-01] ends after Interval[@2020-01-01, @2020-06-01]"
        ) is True

    def test_interval_equivalence_null_bound_closedness_matters(self):
        # REV-004 refined: an OPEN null bound is UNKNOWN, a CLOSED null bound
        # is the point-type extremum — not equivalent. Same-closedness
        # null-null bounds remain equivalent (fixture-pinned True).
        assert self._exec("Interval[1, null] ~ Interval[1, null]") is True
        assert self._exec("Interval[1, null) ~ Interval[1, null)") is True
        assert self._exec("Interval[1, null) ~ Interval[1, null]") is False
        assert self._exec("Interval[1, null] !~ Interval[1, null)") is True
        assert self._exec("Interval(null, 5] ~ Interval[1, 5]") is False


class TestExternalReviewB13IntervalFollowUps:
    """B5-F1 / B5-F2 follow-ups from the external review campaign."""

    def _exec(self, expression: str):
        from fhir4ds.cql import translate_cql
        import duckdb
        from fhir4ds.cql.duckdb import register

        con = duckdb.connect()
        register(con)
        res = translate_cql(
            f"library L\ncontext Unfiltered\ndefine T: {expression}"
        )
        v = next(iter(res.values()))
        sql = v.to_sql() if hasattr(v, "to_sql") else str(v)
        return con.execute(f"SELECT ({sql})").fetchone()[0]

    def _sql_for(self, expression: str) -> str:
        from fhir4ds.cql import translate_cql

        res = translate_cql(
            f"library L\ncontext Unfiltered\ndefine T: {expression}"
        )
        v = next(iter(res.values()))
        return v.to_sql() if hasattr(v, "to_sql") else str(v)

    def test_decomposed_overlaps_open_null_high_is_uncertain(self):
        # B5-F1: a statically-null OPEN high bound means UNKNOWN, not
        # unbounded — overlaps must return null (uncertain) instead of a
        # fabricated definite True (CMS347 open-null-UNKNOWN doctrine).
        assert self._exec(
            "Interval[@2020-01-01, null) overlaps Interval[@2021-06-01, @2021-12-31]"
        ) is None
        # CLOSED null high is the point-type maximum: genuinely unbounded,
        # overlap is definite True.
        assert self._exec(
            "Interval[@2020-01-01, null] overlaps Interval[@2021-06-01, @2021-12-31]"
        ) is True
        # An open-null LOW does not make a definitely-disjoint pair uncertain:
        # the end comparison decides False (3VL: NULL AND False = False).
        assert self._exec(
            "Interval(null, @2019-01-01] overlaps Interval[@2021-06-01, @2021-12-31]"
        ) is False
        # Ordinary overlaps are unchanged.
        assert self._exec(
            "Interval[@2020-01-01, @2022-01-01] overlaps Interval[@2021-06-01, @2021-12-31]"
        ) is True
        assert self._exec(
            "Interval[@2020-01-01, @2020-02-01] overlaps Interval[@2021-06-01, @2021-12-31]"
        ) is False

    def test_interval_ops_recognize_as_interval_cast_right_operand(self):
        # B5-F2: interval-timing operators must extract the bound
        # (intervalStart/intervalEnd) from a right operand produced by an
        # inline `as Interval<T>` cast / First(cast) subquery instead of
        # comparing raw interval JSON lexicographically. Uses a static
        # interval list so the test needs no FHIR data.
        from fhir4ds.cql.parser import parse_cql as _parse
        from fhir4ds.cql.translator import CQLToSQLTranslator as _T

        cql = (
            "library L\ncontext Unfiltered\n"
            "define Src: {Interval[@2020-01-01, @2020-06-01], "
            "Interval[@2021-01-01, @2021-06-01]}\n"
            "define T: Interval[@2019-01-01, @2019-06-01] starts on or after "
            "First((Src X return X as Interval<DateTime>))"
        )
        lib = _parse(cql)
        con = duckdb.connect()
        register(con)
        sql = _T(con).translate_library_to_sql(lib)
        i = sql.find('"T" AS (')
        assert i >= 0
        seg = sql[i : i + 2000]
        assert "intervalStart(" in seg or "intervalEnd(" in seg, seg[:300]


def test_cql_interval_time_ms_null_combined_precision_cql_153_amux171() -> None:
    """CQL 1.5.3 §Time: null milliseconds are combined as ``.0``.

    Spec text (cql.hl7.org/09-b-cqlreference.html#time, from 1.5.3):
    "Although the milliseconds are specified with a separate component,
    seconds and milliseconds are combined and represented as a Decimal for the
    purposes of comparison, duration, and difference calculation. When
    milliseconds are null, they are combined as .0 ... This is true of all
    comparison operations for time values, whether explicit ... or implicit
    ... or when comparison is performed as part of other operations such as
    interval meets and overlaps."

    cql-tests PR #184 pins the consequence for interval-point containment:
    ``Interval[@T12:00:00.001, @T21:59:59.999] properly includes @T12:00:00``
    is FALSE (the point reads 12:00:00.000, before the closed start), where the
    pre-1.5.3 pin (``versionTo="1.5.2"``) said null.

    The referees that MUST NOT change are pinned here too: DateTime interval
    bounds keep the second-vs-millisecond uncertainty
    (CqlIntervalOperatorsTest.xml::DateTimeIncludedInNull), and a point whose
    milliseconds component is *extracted* from a null-ms Time is data-absent
    (null), so the precision-qualified fixtures stay null.
    """
    authority = {
        # cql-tests #184: the 1.5.3 pair.
        "properly includes (point before closed start)": (
            "SELECT intervalProperlyContains("
            "intervalFromBounds('T12:00:00.001', 'T21:59:59.999', true, true), "
            "'T12:00:00')",
            (False,),
        ),
        "properly includes (point == closed high)": (
            "SELECT intervalProperlyContains("
            "intervalFromBounds('T10:00:00.000', 'T12:00:00.000', true, true), "
            "'T12:00:00')",
            (False,),
        ),
        # Point equal to the CLOSED authored start is not *properly* contained
        # (official fixtures TimeProperContainsFalse / TimeProperInFalse).
        "properly includes (point == closed start)": (
            "SELECT intervalProperlyContains("
            "intervalFromBounds('T12:00:00.000', 'T21:59:59.999', true, true), "
            "'T12:00:00')",
            (False,),
        ),
        "properly includes (point strictly inside)": (
            "SELECT intervalProperlyContains("
            "intervalFromBounds('T12:00:00.000', 'T21:59:59.999', true, true), "
            "'T12:00:01')",
            (True,),
        ),
        # Interval equality/equivalence: combined decimal precision makes the
        # second-precision interval equal to the millisecond-precision one
        # (previously null / false).
        "time interval equals across ms precision": (
            "SELECT intervalEquals("
            "intervalFromBounds('T10:00:00', 'T11:00:00', true, true), "
            "intervalFromBounds('T10:00:00.000', 'T11:00:00.000', true, true))",
            (True,),
        ),
        "time interval equivalent across ms precision": (
            "SELECT intervalEquivalent("
            "intervalFromBounds('T10:00:00', 'T11:00:00', true, true), "
            "intervalFromBounds('T10:00:00.000', 'T11:00:00.000', true, true))",
            (True,),
        ),
        # REFEREES - unchanged by the Time rule.
        "DateTimeIncludedInNull referee": (
            "SELECT intervalIncludedIn("
            "intervalFromBounds('2017-09-01T00:00:00', '2017-09-01T00:00:00', true, true), "
            "intervalFromBounds('2017-09-01T00:00:00.000', '2017-12-30T23:59:59.999', true, true))",
            (None,),
        ),
        "millisecond-extracted Time point stays data-absent": (
            "SELECT intervalProperlyContains("
            "intervalFromBounds('T12:00:00.001', 'T21:59:59.999', true, true), "
            "CAST(NULL AS VARCHAR))",
            (None,),
        ),
        "DateTime contains precision keeps uncertainty": (
            "SELECT intervalContainsPrecise("
            "intervalFromBounds('2017-09-01T00:00:00.000', '2017-12-30T23:59:59.999', true, true), "
            "intervalFromBounds('2017-09-01T00:00:00', '2017-09-01T00:00:00', true, true), "
            "'millisecond')",
            (None,),
        ),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for label, (sql, expected) in authority.items():
            assert py.execute(sql).fetchone() == expected, label
            # intervalProperlyContains / intervalEquals / intervalEquivalent /
            # intervalContainsPrecise are all in _PYTHON_PREFERRED_CPP_CONFLICTS,
            # so a normal native-loaded connection runs the Python authority.
            assert cpp.execute(sql).fetchone() == expected, label
    finally:
        py.close()
        cpp.close()

    # End-to-end through the translator: the cql-tests #184 expressions.
    translated = translate_cql(
        """library TimeMs version '1.0.0'
using FHIR version '4.0.1'
context Patient
define ProperIncludesNoMs: Interval[@T12:00:00.001, @T21:59:59.999] properly includes @T12:00:00
define ProperIncludedInNoMs: @T12:00:00 properly included in Interval[@T12:00:00.001, @T21:59:59.999]
define ProperIncludesPrecisionNull: Interval[@T12:00:00.001, @T21:59:59.999] properly includes millisecond of @T12:00:00
define ProperIncludedInPrecisionNull: @T12:00:00 properly included in millisecond of Interval[@T12:00:00.001, @T21:59:59.999]
"""
    )
    end_to_end = {
        "ProperIncludesNoMs": (False,),
        "ProperIncludedInNoMs": (False,),
        # REFEREE: `millisecond of @T12:00:00` is data-absent -> the null-ms
        # precision-qualified fixtures TimeProperContainsPrecisionNull /
        # TimeProperInPrecisionNull stay null.
        "ProperIncludesPrecisionNull": (None,),
        "ProperIncludedInPrecisionNull": (None,),
    }
    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, expected in end_to_end.items():
            sql = f"SELECT {translated[name].to_sql()}"
            assert py.execute(sql).fetchone() == expected, name
            assert cpp.execute(sql).fetchone() == expected, name
    finally:
        py.close()
        cpp.close()
