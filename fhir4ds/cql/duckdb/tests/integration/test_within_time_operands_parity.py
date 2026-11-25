"""CQL ``within N unit of`` over TIME operands (FHIR4-50).

THE DEFECT
==========
The whole ``within ... of`` family lowered its operands to
``CAST(<operand> AS TIMESTAMP)`` (``_temporal_target_type`` always returns
``TIMESTAMP``; ``_normalize_temporal_for_compare`` /
``_cast_for_interval_arithmetic`` re-assert it).  A CQL Time value is a
``T``-prefixed clock string (``@T10:00`` -> ``'T10:00'``), so DuckDB rejects it
at bind time::

    ConversionException: invalid timestamp field format: "T12:00"

That reproduced for the plain form and for the FHIR4-46 ``properly`` variant
(which is why FHIR4-46 kept it as a strict xfail rather than fixing it there).

REFERENCE SEMANTICS (authority for the lowering)
================================================
cqframework/clinical_quality_language, ``cql-to-elm``
``Cql2ElmVisitor.visitWithinIntervalOperatorPhrase`` (main branch,
cql-to-elm/src/commonMain/kotlin/org/cqframework/cql/cql2elm/Cql2ElmVisitor.kt,
``visitWithinIntervalOperatorPhrase``) lowers the phrase to::

    In(left, Interval(Subtract(right, quantity), Add(right, quantity)))

with the constructed bounds CLOSED for the plain form and OPEN for the
``properly`` form (``createInterval(lowerBound, !isProper, upperBound,
!isProper)``).  It is not special-cased for Time, so the reference inherits
the engine's Time rules:

* ``AddEvaluator`` / ``SubtractEvaluator`` handle ``(BaseTemporal, Quantity)``
  and build a Time from ``(left as Time).time.plus(value, unit)`` — a
  ``java.time.LocalTime`` add, i.e. the result WRAPS modulo 24 hours.
  Consequence: ``@T00:15 - 3 hours`` is ``T21:15``, not an error and not a
  previous-day instant.
* ``InEvaluator.intervalIn`` for a temporal point compares with
  ``SameAs`` / ``Before`` / ``After`` (short-circuit) and then
  ``SameOrAfter(start) and SameOrBefore(end)``.  It does NOT wrap the interval:
  a wrapped bound pair whose low is after its high (``[T23:15, T01:15]``)
  therefore answers FALSE for a point after the high bound
  (``@T23:30 within 1 hour of @T00:15`` -> FALSE), and a point that sits
  between a wrapped high bound and the low bound
  (``@T21:00 within 3 hours of @T23:00`` -> bounds ``[T20:00, T02:00]``)
  likewise answers FALSE.

This engine already owns exactly those primitives:

* ``dateAddQuantity`` / ``dateSubtractQuantity`` are Time-aware and wrap
  modulo midnight (CQL-13 doctrine), and
* ``cqlSameOrAfter`` / ``cqlSameOrBefore`` / ``cqlAfter`` / ``cqlBefore`` are
  the precision-aware temporal comparisons (AMUX-171: Time compares with the
  combined seconds/milliseconds rule, and Time values are never routed through
  DateTime timezone normalization because the CQL Time model has no timezone).

So the Time path is a composition of existing helpers — no new UDF, no new
macro, no native rebuild:

    |A - B| <= Q  (plain)  ->  cqlSameOrAfter(A, B - Q) and cqlSameOrBefore(A, B + Q)
    |A - B| <  Q  (proper) ->  cqlAfter(A, B - Q)        and cqlBefore(A, B + Q)

KNOWN BOUNDARY (documented, pinned below): a DAY-LEVEL unit on Time operands
(``within 3 days of``) stays NULL.  CQL 1.5 §8.1/§8.15: "For Time values, the
quantity unit must be one of: hours, minutes, seconds, or milliseconds", so
``Time - 3 days`` is invalid and the offset bounds are unknown; the reference
inherits ``LocalTime.plus(3, DAYS)``, which is a silent no-op (an artifact of
the Java type, not spec semantics).  In a population WHERE clause NULL is
already read as not-in-population, so the observable measure behaviour agrees.
"""

from __future__ import annotations

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.translator import translate_cql

from .wasm_runtime_helpers import assert_no_python_result, no_python_connection


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def _translate_defines(defines: dict[str, str]) -> dict[str, str]:
    lines = ["library FHIR4_50 version '1.0.0'", "using FHIR version '4.0.1'"]
    for name, expression in defines.items():
        lines.append(f"define {name}: {expression}")
    translated = translate_cql("\n".join(lines))
    return {name: translated[name].to_sql() for name in defines}


# ---------------------------------------------------------------------------
# Lowering: the Time path must not touch TIMESTAMP
# ---------------------------------------------------------------------------


def test_cql_within_time_operands_lower_without_timestamp_casts() -> None:
    """Red-first structural pin: Time operands never reach CAST(... AS TIMESTAMP).

    Before FHIR4-50 this same expression emitted
    ``CAST('T12:00' AS TIMESTAMP) - INTERVAL '3 hour' <= CAST('T10:00' AS
    TIMESTAMP) ...`` and raised ConversionException at execution.
    """
    sql = _translate_defines(
        {
            "PlainTime": "@T10:00 within 3 hours of @T12:00",
            "ProperTime": "@T10:00 properly within 3 hours of @T12:00",
            "StartsTime": "Interval[@T08:00, @T10:00] starts within 3 hours of @T12:00",
            "EndsTime": "Interval[@T10:00, @T12:00] ends properly within 2 hours of @T14:00",
        }
    )

    for name, statement in sql.items():
        assert "AS TIMESTAMP" not in statement, (name, statement)
        assert "INTERVAL" not in statement, (name, statement)

    # Plain form: closed offset bounds -> same-or-after / same-or-before.
    assert "dateSubtractQuantity" in sql["PlainTime"], sql["PlainTime"]
    assert "dateAddQuantity" in sql["PlainTime"], sql["PlainTime"]
    assert "cqlSameOrAfter" in sql["PlainTime"], sql["PlainTime"]
    assert "cqlSameOrBefore" in sql["PlainTime"], sql["PlainTime"]

    # Proper form: OPEN offset bounds -> strict before/after.
    assert "cqlAfter" in sql["ProperTime"], sql["ProperTime"]
    assert "cqlBefore" in sql["ProperTime"], sql["ProperTime"]
    assert "cqlSameOrAfter" not in sql["ProperTime"], sql["ProperTime"]
    assert "cqlSameOrBefore" not in sql["ProperTime"], sql["ProperTime"]

    # starts/ends extract the boundary first, then take the Time path.
    assert "intervalStart" in sql["StartsTime"], sql["StartsTime"]
    assert "dateSubtractQuantity" in sql["StartsTime"], sql["StartsTime"]
    assert "intervalEnd" in sql["EndsTime"], sql["EndsTime"]
    assert "cqlBefore" in sql["EndsTime"], sql["EndsTime"]


def test_cql_within_time_operands_are_detected_through_defines_and_constructors() -> None:
    """Time detection must survive aliases, ``as Time``, ``Time(...)``, ``ToTime``."""
    defines = {
        "T1": "@T10:00",
        "I1": "Interval[@T08:00, @T10:00]",
        "ViaDefine": "T1 within 3 hours of @T12:00",
        "ViaIntervalDefine": "I1 starts within 3 hours of @T12:00",
        "ViaCast": "(@T10:00 as Time) within 3 hours of @T12:00",
        "ViaConstructor": "Time(10, 0, 0) within 3 hours of @T12:00",
        "ViaToTime": "ToTime('10:00') within 3 hours of @T12:00",
    }
    sql = _translate_defines(defines)
    for name in (
        "ViaDefine",
        "ViaIntervalDefine",
        "ViaCast",
        "ViaConstructor",
        "ViaToTime",
    ):
        assert "AS TIMESTAMP" not in sql[name], (name, sql[name])
        assert "cqlSameOrAfter" in sql[name], (name, sql[name])


# ---------------------------------------------------------------------------
# The Date / DateTime path must be BYTE-IDENTICAL (golden SQL)
# ---------------------------------------------------------------------------

#: Captured from the pre-FHIR4-50 tree (HEAD 774c997a519). These statements are
#: also what DQM measures execute: CMS128 uses
#: ``date from start of ... within 60 days of ...``.
_GOLDEN_DATE_DATETIME_SQL = {
    "G1": (
        "@2014-01-01 within 3 days of @2014-01-03",
        "CAST('2014-01-03' AS TIMESTAMP) - INTERVAL '3 day' <= "
        "CAST('2014-01-01' AS TIMESTAMP) AND CAST('2014-01-01' AS TIMESTAMP) <= "
        "CAST('2014-01-03' AS TIMESTAMP) + INTERVAL '3 day'",
    ),
    "G2": (
        "@2014-01-01T10:00 within 3 hours of @2014-01-01T12:00",
        "CAST('2014-01-01T12:00' AS TIMESTAMP) - INTERVAL '3 hour' <= "
        "CAST('2014-01-01T10:00' AS TIMESTAMP) AND "
        "CAST('2014-01-01T10:00' AS TIMESTAMP) <= CAST('2014-01-01T12:00' AS TIMESTAMP) + "
        "INTERVAL '3 hour'",
    ),
    "G3": (
        "Interval[@2014-01-01, @2014-01-05] starts within 3 days of @2014-01-03",
        "CAST('2014-01-03' AS TIMESTAMP) - INTERVAL '3 day' <= "
        "CAST(intervalStart(intervalFromBounds('2014-01-01', '2014-01-05', TRUE, TRUE)) "
        "AS TIMESTAMP) AND CAST(intervalStart(intervalFromBounds('2014-01-01', "
        "'2014-01-05', TRUE, TRUE)) AS TIMESTAMP) <= CAST('2014-01-03' AS TIMESTAMP) + "
        "INTERVAL '3 day'",
    ),
    "G4": (
        "@2014-01-01 properly within 2 days of @2014-01-03",
        "CAST('2014-01-03' AS TIMESTAMP) - INTERVAL '2 day' < "
        "CAST('2014-01-01' AS TIMESTAMP) AND CAST('2014-01-01' AS TIMESTAMP) < "
        "CAST('2014-01-03' AS TIMESTAMP) + INTERVAL '2 day'",
    ),
    "G5": (
        "date from @2014-01-01T10:00 within 60 days of @2014-01-03",
        "CAST('2014-01-03' AS TIMESTAMP) - INTERVAL '60 day' <= "
        "CAST('2014-01-01' AS TIMESTAMP) AND CAST('2014-01-01' AS TIMESTAMP) <= "
        "CAST('2014-01-03' AS TIMESTAMP) + INTERVAL '60 day'",
    ),
    "G6": (
        "@2012 within 3 days of @2012-01-03",
        "CAST('2012-01-03' AS TIMESTAMP) - INTERVAL '3 day' <= CAST('2012' AS TIMESTAMP) "
        "AND CAST('2012' AS TIMESTAMP) <= CAST('2012-01-03' AS TIMESTAMP) + "
        "INTERVAL '3 day'",
    ),
}


def test_cql_within_date_datetime_sql_is_byte_identical_to_pre_fix_lowering() -> None:
    """The Time path must be additive: Date/DateTime SQL is unchanged verbatim."""
    sql = _translate_defines({name: expr for name, (expr, _) in _GOLDEN_DATE_DATETIME_SQL.items()})
    for name, (_expression, expected) in _GOLDEN_DATE_DATETIME_SQL.items():
        assert sql[name] == expected, (name, sql[name])


# ---------------------------------------------------------------------------
# Semantics matrix: py-fallback == native-loaded == no-Python
# ---------------------------------------------------------------------------

#: define name -> (expression, expected row)
_WITHIN_TIME_CASES: dict[str, tuple[str, tuple]] = {
    # --- point / point, plain (CLOSED offsets) --------------------------
    "WithinTimeTrue": ("@T10:00 within 3 hours of @T12:00", (True,)),
    "WithinTimeSymmetric": ("@T14:00 within 3 hours of @T12:00", (True,)),
    "WithinTimeContactLow": ("@T09:00 within 3 hours of @T12:00", (True,)),
    "WithinTimeContactHigh": ("@T15:00 within 3 hours of @T12:00", (True,)),
    "WithinTimeJustOutsideLow": ("@T08:59 within 3 hours of @T12:00", (False,)),
    "WithinTimeJustOutsideHigh": ("@T15:01 within 3 hours of @T12:00", (False,)),
    # --- point / point, proper (OPEN offsets): contact is FALSE ---------
    "ProperWithinTimeTrue": ("@T10:00 properly within 3 hours of @T12:00", (True,)),
    "ProperWithinTimeContactLow": ("@T09:00 properly within 3 hours of @T12:00", (False,)),
    "ProperWithinTimeContactHigh": ("@T15:00 properly within 3 hours of @T12:00", (False,)),
    "ProperWithinTimeJustOutside": ("@T08:00:01 properly within 3 hours of @T12:00", (False,)),
    # Precision uncertainty is preserved: the bound is minute-precision
    # ('T09:00') and the point adds seconds, so "strictly after the low bound"
    # is not decidable at the shared precision -> UNKNOWN (CQL §After with
    # differing precisions), not a fabricated FALSE.
    "ProperWithinTimePrecisionUncertain": (
        "@T09:00:01 properly within 3 hours of @T12:00",
        (None,),
    ),
    # --- sub-day units at their own precision --------------------------
    "WithinTimeMinutesContact": ("@T11:30 within 30 minutes of @T12:00", (True,)),
    "WithinTimeMinutesOutside": ("@T11:29 within 30 minutes of @T12:00", (False,)),
    # Second/millisecond windows need SECOND-precision anchors: CQL §8.1/§8.15
    # perform arithmetic at the input precision, so a 30-second offset on a
    # minute-precision Time is 0 minutes (both engines, and the reference
    # engine's truncateValueToTargetPrecision, agree).
    "WithinTimeSecondsContact": ("@T11:59:30 within 30 seconds of @T12:00:00", (True,)),
    "WithinTimeSecondsOutside": ("@T11:59:29 within 30 seconds of @T12:00:00", (False,)),
    "WithinTimeMillisContact": (
        "@T11:59:59.500 within 500 milliseconds of @T12:00:00.000",
        (True,),
    ),
    "WithinTimeMillisOutside": (
        "@T11:59:59.499 within 500 milliseconds of @T12:00:00.000",
        (False,),
    ),
    # Precision truncation pin: a sub-precision offset is a no-op, so the
    # closed window collapses to the anchor itself.
    "WithinTimeSubPrecisionOffset": ("@T11:59:30 within 30 seconds of @T12:00", (False,)),
    "WithinTimeSubPrecisionOffsetAtAnchor": ("@T12:00 within 30 seconds of @T12:00", (True,)),
    "WithinTimeZeroOffsetContact": ("@T12:00 within 0 seconds of @T12:00", (True,)),
    "ProperWithinTimeZeroOffset": ("@T12:00 properly within 0 seconds of @T12:00", (False,)),
    # --- midnight: Time arithmetic WRAPS, the interval does NOT --------
    # Reference: Interval(T00:15 - 1h, T00:15 + 1h) = [T23:15, T01:15]; the
    # point is after the (wrapped) high bound -> FALSE.
    "WithinTimeMidnightWrapOut": ("@T23:30 within 1 hour of @T00:15", (False,)),
    "WithinTimeMidnightInside": ("@T00:30 within 1 hour of @T01:00", (True,)),
    # Reference: [T20:00, T02:00] high bound wraps, point is after it -> FALSE.
    "WithinTimeUnderflowNoWrapAround": ("@T21:00 within 3 hours of @T23:00", (False,)),
    "WithinTimeWrappedBoundStillMatches": ("@T23:30 within 3 hours of @T01:00", (False,)),
    # --- starts / ends: boundary extraction keeps the offsets ----------
    "StartsWithinTimeTrue": (
        "Interval[@T10:00, @T12:00] starts within 3 hours of @T12:00",
        (True,),
    ),
    "StartsWithinTimeContact": (
        "Interval[@T09:00, @T12:00] starts within 3 hours of @T12:00",
        (True,),
    ),
    "StartsProperlyWithinTimeContact": (
        "Interval[@T09:00, @T12:00] starts properly within 3 hours of @T12:00",
        (False,),
    ),
    "EndsWithinTimeTrue": (
        "Interval[@T10:00, @T12:00] ends within 3 hours of @T14:00",
        (True,),
    ),
    "EndsWithinTimeContact": (
        "Interval[@T10:00, @T11:00] ends within 1 hour of @T12:00",
        (True,),
    ),
    "EndsProperlyWithinTimeContact": (
        "Interval[@T10:00, @T11:00] ends properly within 1 hour of @T12:00",
        (False,),
    ),
    # --- Time reached through declares / casts / constructors ----------
    # NOTE: Time-typed declares are covered structurally by
    # test_cql_within_time_operands_are_detected_through_defines_and_constructors;
    # this matrix keeps every expression self-contained so each row can be
    # executed standalone on all three engines.
    # --- null operands keep propagating ---------------------------------
    "WithinTimeNullLeft": ("(null as Time) within 3 hours of @T12:00", (None,)),
    "WithinTimeNullRight": ("@T10:00 within 3 hours of (null as Time)", (None,)),
    "ProperWithinTimeNullRight": ("@T10:00 properly within 3 hours of (null as Time)", (None,)),
    # --- type boundaries -------------------------------------------------
    # CQL 1.5 §8.1/§8.15: only hours/minutes/seconds/milliseconds are valid
    # quantity units for Time, so the offset bounds are unknown -> NULL.
    "WithinTimeDayLevelUnit": ("@T10:00 within 3 days of @T12:00", (None,)),
    # Comparison signatures are same-type; a Time vs DateTime pair is
    # undefined and must be UNKNOWN, never a fabricated boolean.
    "WithinTimeVsDateTime": ("@T10:00 within 3 hours of @2014-01-01T12:00", (None,)),
}


def test_cql_within_time_operands_semantics_match_python_and_cpp_engines() -> None:
    """py-fallback == native-loaded == no-Python, and the values are absolute."""
    defines = {name: expression for name, (expression, _) in _WITHIN_TIME_CASES.items()}
    translated = _translate_defines(defines)

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        with no_python_connection() as no_py:
            for name, (_expression, expected) in _WITHIN_TIME_CASES.items():
                statement = f"SELECT {translated[name]}"
                py_result = py.execute(statement).fetchone()
                cpp_result = cpp.execute(statement).fetchone()
                assert cpp_result == py_result, f"{name}: cpp={cpp_result} py={py_result}"
                assert_no_python_result(no_py, statement, py_result, label=name)
                assert py_result == expected, f"{name}: {py_result} != {expected}"
    finally:
        py.close()
        cpp.close()


def test_cql_within_time_operands_survive_defines_and_casts_at_runtime() -> None:
    """The statically-detected Time shapes evaluate (not just translate).

    ``I1``/``starts within`` needs the population CTE environment (a define
    reference lowers to a patient-correlated subquery), so that shape is
    covered structurally above and end-to-end by the population test below.
    """
    defines = {
        "T1": "@T10:00",
        "ViaDefine": "T1 within 3 hours of @T12:00",
        "ViaCast": "(@T10:00 as Time) within 3 hours of @T12:00",
        "ViaConstructor": "Time(10, 0, 0) within 3 hours of @T12:00",
        "ViaToTime": "ToTime('10:00') within 3 hours of @T12:00",
    }
    translated = _translate_defines(defines)
    expected = {
        "ViaDefine": (True,),
        "ViaCast": (True,),
        "ViaConstructor": (True,),
        "ViaToTime": (True,),
    }

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, want in expected.items():
            statement = f"SELECT {translated[name]}"
            py_result = py.execute(statement).fetchone()
            cpp_result = cpp.execute(statement).fetchone()
            assert py_result == want, (name, py_result)
            assert cpp_result == py_result, (name, cpp_result, py_result)
    finally:
        py.close()
        cpp.close()


# ---------------------------------------------------------------------------
# Population (WHERE-clause) context — the realistic dynamic-FHIR shape
# ---------------------------------------------------------------------------

_POPULATION_RESOURCES_SQL = """
CREATE TABLE resources (id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR);
INSERT INTO resources VALUES
 ('p1','Patient','{"resourceType":"Patient","id":"p1"}','p1'),
 ('p2','Patient','{"resourceType":"Patient","id":"p2"}','p2'),
 ('o1','Observation','{"resourceType":"Observation","id":"o1","valueTime":"10:00:00"}','p1'),
 ('o2','Observation','{"resourceType":"Observation","id":"o2","valueTime":"16:00:00"}','p2');
"""

_POPULATION_LIBRARY = """
library Fhir4_50Pop version '1.0.0'
using FHIR version '4.0.1'
context Patient
define Obs: [Observation]
define PlainTime: exists (Obs O where O.valueTime within 3 hours of @T12:00)
define ProperTime: exists (Obs O where O.valueTime properly within 3 hours of @T12:00)
define ContactTime: exists (Obs O where O.valueTime within 5 hours of @T12:00)
"""


def test_cql_within_time_operands_work_in_population_where_clauses() -> None:
    """A dynamically-typed FHIR `time` element must resolve, not raise.

    ``O.valueTime`` lowers to a VARCHAR extraction (FHIR time is 'HH:MM:SS'),
    so the static Time signal comes from the ``@T12:00`` anchor. p1 is 2 hours
    away (plain TRUE, proper TRUE); p2 is 4 hours away (FALSE at 3 hours,
    TRUE at 5 hours).
    """
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator.translator import CQLToSQLTranslator

    sql = CQLToSQLTranslator().translate_library_to_population_sql(
        parse_cql(_POPULATION_LIBRARY),
        output_columns={
            "PlainTime": "PlainTime",
            "ProperTime": "ProperTime",
            "ContactTime": "ContactTime",
        },
    )
    expected = [
        ("p1", True, True, True),
        ("p2", False, False, True),
    ]
    assert "AS TIMESTAMP" not in sql, sql

    for connection in (_python_only_connection(), _cpp_connection()):
        try:
            connection.execute(_POPULATION_RESOURCES_SQL)
            rows = connection.execute(f"SELECT * FROM ({sql}) ORDER BY patient_id").fetchall()
        finally:
            connection.close()
        assert rows == expected, rows


# ---------------------------------------------------------------------------
# Nothing else moved: Date/DateTime semantics still hold
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("@2014-01-01 within 3 days of @2014-01-03", True),
        ("@2014-01-01 within 1 day of @2014-01-03", False),
        ("@2014-01-01 properly within 3 days of @2014-01-03", True),
        ("@2014-01-01 properly within 2 days of @2014-01-03", False),
        ("@2014-01-01T10:00 within 2 hours of @2014-01-01T12:00", True),
        ("@2014-01-01T10:00 properly within 2 hours of @2014-01-01T12:00", False),
        ("(null as Date) within 3 days of @2014-01-03", None),
    ],
)
def test_cql_within_date_datetime_behaviour_is_unchanged_by_the_time_path(
    expression: str, expected: bool | None
) -> None:
    sql = _translate_defines({"Control": expression})["Control"]
    py = _python_only_connection()
    try:
        assert py.execute(f"SELECT {sql}").fetchone() == (expected,), expression
    finally:
        py.close()


def test_cql_bare_interval_within_is_left_on_its_historical_lowering() -> None:
    """``Interval within Q of point`` is NOT a CQL signature — do not "fix" it here.

    ``In``/``ProperIn`` take a POINT as the first argument; the interval forms of
    the phrase are ``starts within`` / ``ends within``, which reduce the interval
    to a boundary first. A bare interval operand therefore keeps its historical
    lowering (``CAST(<interval JSON> AS TIMESTAMP)``), and FHIR4-50's Time path
    must stay out of it so both engines keep behaving identically. This pin is
    the tripwire: if the Time path ever swallows this shape the two engines
    diverge (the Python comparison answers NULL for a malformed operand where
    the native one answers FALSE).
    """
    sql = _translate_defines(
        {"BareInterval": "Interval[@T08:00, @T10:00] within 3 hours of @T12:00"}
    )["BareInterval"]
    assert "AS TIMESTAMP" in sql, sql
    assert "cqlSameOrAfter" not in sql, sql

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for connection in (py, cpp):
            with pytest.raises(duckdb.ConversionException):
                connection.execute(f"SELECT {sql}").fetchone()
    finally:
        py.close()
        cpp.close()
