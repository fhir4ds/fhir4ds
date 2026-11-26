"""FHIR4-71: the CQL age family is CRISP at second precision.

CQL §Types/Time makes seconds and milliseconds ONE combined decimal precision —
"when milliseconds are null, they are combined as .0" (AMUX-171, recorded in the
root AGENTS.md) — so a second-precision operand is EXACT at ``.000``, not an
unknown one-second window.  An age measured in seconds therefore has a single
definite value:

    CalculateAgeInSecondsAt(@2000-05-15T00:00:00Z, @2000-05-15T00:00:01Z)  // 1
    CalculateAgeInSecondsAt(@2000-05-15T00:00:00Z, @2000-05-15T01:00:00Z)  // 3600

Uncertainty intervals are reserved for operands genuinely COARSER than the
requested unit — a day-precision birthDate asked for seconds still cannot pin
the time of birth.

THE CARVE-OUT IS AGE-ONLY.  `_duration_between_with_uncertainty` keeps its
strict §22.21 "one component finer than the target" rule as the default because
the official fixtures pin generic duration/difference uncertainty intervals
(e.g. ``months between @2012-01-02 and @2012`` -> ``Interval[0, 10]``).  The age
call site opts in through ``treat_second_as_exact=True``; the matching C++
mirror is the ``treat_second_as_exact`` parameter of
``CqlDurationBetweenString`` (extensions/cql/src/cql_extension.py).  The last
test in this module is the boundary pin: the SAME operands stay an interval for
``duration in seconds between`` while the age is crisp.
"""

from __future__ import annotations

import json

import duckdb

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements
from fhir4ds.cql.translator import translate_cql

from .wasm_runtime_helpers import no_python_connection

PATIENT_DAY_BIRTH = json.dumps({"resourceType": "Patient", "birthDate": "2000-05-15"})
PATIENT_BAD_BIRTH = json.dumps({"resourceType": "Patient", "birthDate": "not-a-date"})

#: The day-precision birthDate uncertainty interval for
#: ``...At(@2000-05-15, @2000-05-15T00:00:01Z)``: the birth could be anywhere in
#: the day, so the age in seconds spans [-86398, 1].
DAY_BIRTH_SECONDS_INTERVAL = '{"start":-86398,"end":1,"lowClosed":true,"highClosed":true}'


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


#: ``(label, function, args, expected)`` — ``expected`` is the FHIR4-71
#: authoritative result of the Python UDFs.
_AGE_CASES: list[tuple[str, str, list[str | None], str | None]] = [
    # ---- second precision is EXACT (.000): the age is CRISP --------------
    ("SecondsOneSecond", "CalculateAgeInSecondsAt",
     ["2000-05-15T00:00:00Z", "2000-05-15T00:00:01Z"], "1"),
    ("SecondsOneHour", "CalculateAgeInSecondsAt",
     ["2000-05-15T00:00:00Z", "2000-05-15T01:00:00Z"], "3600"),
    ("SecondsZeroDelta", "CalculateAgeInSecondsAt",
     ["2000-05-15T00:00:00Z", "2000-05-15T00:00:00Z"], "0"),
    # Milliseconds are the SAME combined rung, so millisecond operands stay
    # crisp and the year-fraction is reported at second granularity.
    ("SecondsMillisecondOperands", "CalculateAgeInSecondsAt",
     ["2000-05-15T00:00:00.000Z", "2000-05-15T00:00:01.250Z"], "1"),
    ("SecondsMillisecondOperands2", "CalculateAgeInSecondsAt",
     ["2000-05-15T00:00:00.500Z", "2000-05-15T00:00:02.000Z"], "1"),
    # A definitive negative age is clinically invalid and stays NULL (it is
    # NOT turned into an interval by the combined-precision rule).
    ("SecondsNegativeDelta", "CalculateAgeInSecondsAt",
     ["2000-05-15T00:00:01Z", "2000-05-15T00:00:00Z"], None),
    # ---- genuinely COARSER operands keep their uncertainty --------------
    ("SecondsDayPrecisionBirthDate", "CalculateAgeInSecondsAt",
     ["2000-05-15", "2000-05-15T00:00:01Z"], DAY_BIRTH_SECONDS_INTERVAL),
    ("AgeInSecondsAtDayPrecisionBirthDate", "AgeInSecondsAt",
     [PATIENT_DAY_BIRTH, "2000-05-15T00:00:01Z"], DAY_BIRTH_SECONDS_INTERVAL),
    ("SecondsHourPrecisionOperand", "CalculateAgeInSecondsAt",
     ["2000-05-15T00", "2000-05-15T01:00:00Z"],
     '{"start":0,"end":3600,"lowClosed":true,"highClosed":true}'),
    # ---- hour/minute targets are UNCHANGED (already crisp on the data) --
    ("HoursSecondPrecisionOperands", "CalculateAgeInHoursAt",
     ["2000-05-15T00:00:00Z", "2000-05-15T01:00:00Z"], "1"),
    ("MinutesSecondPrecisionOperands", "CalculateAgeInMinutesAt",
     ["2000-05-15T00:00:00Z", "2000-05-15T00:01:00Z"], "1"),
    # ... and still uncertain when the operand is exactly at the target unit.
    ("HoursHourPrecisionOperand", "CalculateAgeInHoursAt",
     ["2000-05-15T00", "2000-05-15T01:00:00Z"],
     '{"start":0,"end":1,"lowClosed":true,"highClosed":true}'),
    ("MinutesMinutePrecisionOperand", "CalculateAgeInMinutesAt",
     ["2000-05-15T00:00", "2000-05-15T00:01:00Z"],
     '{"start":0,"end":1,"lowClosed":true,"highClosed":true}'),
    # ---- calendar targets are untouched ---------------------------------
    ("YearsDayPrecisionDates", "CalculateAgeInYearsAt",
     ["2000-05-15", "2026-05-15"], "26"),
    # ---- null / garbage inputs ------------------------------------------
    ("NullBirthDate", "CalculateAgeInSecondsAt", [None, "2000-05-15T00:00:01Z"], None),
    ("NullAsOf", "CalculateAgeInSecondsAt", ["2000-05-15T00:00:00Z", None], None),
    ("GarbageBirthDate", "CalculateAgeInSecondsAt",
     ["not-a-date", "2000-05-15T00:00:01Z"], None),
    ("GarbageAsOf", "CalculateAgeInSecondsAt",
     ["2000-05-15T00:00:00Z", "garbage"], None),
    ("GarbagePatientBirthDate", "AgeInSecondsAt",
     [PATIENT_BAD_BIRTH, "2000-05-15T00:00:01Z"], None),
]

#: FHIR4-71 rebuild window. The bundled ``cql.duckdb_extension`` predates the
#: ``treat_second_as_exact`` C++ mirror, so the C++-served age surface keeps the
#: pre-fix uncertainty interval until the bundles are rebuilt
#: (``python3 scripts/build_extension_bundles.py --build --abi <slot>``).
#: ``_native_age_carve_out_is_current`` probes the LOADED binary, so these
#: expectations flip automatically once the rebuilt extension ships — delete the
#: map and its branch at that point.
_NATIVE_SECOND_PRECISION_STALE: dict[str, str | None] = {
    "SecondsOneSecond": '{"start":0,"end":1,"lowClosed":true,"highClosed":true}',
    "SecondsOneHour": '{"start":3599,"end":3600,"lowClosed":true,"highClosed":true}',
    # Sum over two crisp second-precision ages (see the consumer test).
    "AgeSum": '{"start":1,"end":3,"lowClosed":true,"highClosed":true}',
}


def _native_age_carve_out_is_current(con: duckdb.DuckDBPyConnection) -> bool:
    """True when the loaded cql extension implements the FHIR4-71 age carve-out."""
    row = con.execute(
        "SELECT CalculateAgeInSecondsAt('2000-05-15T00:00:00Z', '2000-05-15T00:00:01Z')"
    ).fetchone()[0]
    return row == "1"


def _native_expected(native_current: bool, label: str, expected: object) -> object:
    if native_current:
        return expected
    return _NATIVE_SECOND_PRECISION_STALE.get(label, expected)


def test_cql_age_second_precision_python_authority_is_crisp() -> None:
    """The Python UDFs (the desktop conformance authority) answer crisply."""
    con = _python_only_connection()
    try:
        for label, function, args, expected in _AGE_CASES:
            row = con.execute(f"SELECT {function}(?, ?)", args).fetchone()
            assert row == (expected,), f"{label}: {row!r} != {(expected,)!r}"
    finally:
        con.close()


def test_cql_age_second_precision_native_and_no_python_parity() -> None:
    """Native-loaded and bundled-C++-only engines agree with the authority.

    The two ``SecondsOneSecond`` / ``SecondsOneHour`` cells are PENDING THE
    EXTENSION REBUILD (see ``_NATIVE_SECOND_PRECISION_STALE``); every other cell
    is engine-stable and asserted directly.
    """
    cpp = _cpp_connection()
    try:
        native_current = _native_age_carve_out_is_current(cpp)
        for label, function, args, expected in _AGE_CASES:
            row = cpp.execute(f"SELECT {function}(?, ?)", args).fetchone()
            assert row == (_native_expected(native_current, label, expected),), label
    finally:
        cpp.close()

    with no_python_connection() as no_py:
        native_current = _native_age_carve_out_is_current(no_py)
        for label, function, args, expected in _AGE_CASES:
            row = no_py.execute(f"SELECT {function}(?, ?)", args).fetchone()
            assert row == (_native_expected(native_current, label, expected),), label


def test_cql_age_second_precision_translated_sql_end_to_end() -> None:
    """The carve-out survives translation: the age define is crisp end to end."""
    cql = """library FHIR471AgeSecondPrecision version '1.0.0'
using FHIR version '4.0.1'
context Patient
define SecondsOneSecond: CalculateAgeInSecondsAt(@2000-05-15T00:00:00Z, @2000-05-15T00:00:01Z)
define SecondsOneHour: CalculateAgeInSecondsAt(@2000-05-15T00:00:00Z, @2000-05-15T01:00:00Z)
define SecondsDayPrecisionBirthDate: CalculateAgeInSecondsAt(@2000-05-15, @2000-05-15T00:00:01Z)
"""
    translated = {name: expr.to_sql() for name, expr in translate_cql(cql).items()}
    expected = {
        "SecondsOneSecond": "1",
        "SecondsOneHour": "3600",
        "SecondsDayPrecisionBirthDate": DAY_BIRTH_SECONDS_INTERVAL,
    }
    # The age lowering is a direct UDF call, so the operand literals reach the
    # engine unchanged (no precision-bearing SQL rewriting).
    assert "CalculateAgeInSecondsAt(" in translated["SecondsOneSecond"]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, sql in translated.items():
            row = py.execute(f"SELECT {sql}").fetchone()
            assert row == (expected[name],), f"python {name}: {row!r}"
        native_current = _native_age_carve_out_is_current(cpp)
        for name, sql in translated.items():
            row = cpp.execute(f"SELECT {sql}").fetchone()
            assert row == (_native_expected(native_current, name, expected[name]),), name
        with no_python_connection() as no_py:
            native_current = _native_age_carve_out_is_current(no_py)
            for name, sql in translated.items():
                row = no_py.execute(f"SELECT {sql}").fetchone()
                assert row == (_native_expected(native_current, name, expected[name]),), name
    finally:
        py.close()
        cpp.close()


def test_cql_age_second_precision_feeds_uncertainty_consumers() -> None:
    """A crisp age still flows through the §22.21 uncertainty consumers.

    CQL-21 made the age family return VARCHAR (an integer string OR interval
    JSON), so the consumers that accept either shape — ``cqlUncertainCompare``
    for ``age in Interval[..]`` and ``cqlUncertainListSum`` for aggregates — must
    keep working when the value is now a crisp integer.
    """
    cql = """library FHIR471AgeConsumers version '1.0.0'
using FHIR version '4.0.1'
context Patient
define AgeInInterval: CalculateAgeInSecondsAt(@2000-05-15T00:00:00Z, @2000-05-15T00:00:01Z) in Interval[0, 2]
define AgeSum: Sum({CalculateAgeInSecondsAt(@2000-05-15T00:00:00Z, @2000-05-15T00:00:01Z), CalculateAgeInSecondsAt(@2000-05-15T00:00:00Z, @2000-05-15T00:00:02Z)})
"""
    translated = {name: expr.to_sql() for name, expr in translate_cql(cql).items()}
    expected: dict[str, object] = {"AgeInInterval": True, "AgeSum": "3"}
    # Both consumers really are the §22.21 uncertainty-tolerant helpers.
    assert "cqlUncertainCompare(" in translated["AgeInInterval"]
    assert "cqlUncertainListSum(" in translated["AgeSum"]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for name, sql in translated.items():
            row = py.execute(f"SELECT {sql}").fetchone()
            assert row == (expected[name],), f"python {name}: {row!r}"
        native_current = _native_age_carve_out_is_current(cpp)
        for name, sql in translated.items():
            row = cpp.execute(f"SELECT {sql}").fetchone()
            assert row == (_native_expected(native_current, name, expected[name]),), name
        with no_python_connection() as no_py:
            native_current = _native_age_carve_out_is_current(no_py)
            for name, sql in translated.items():
                row = no_py.execute(f"SELECT {sql}").fetchone()
                assert row == (_native_expected(native_current, name, expected[name]),), name
    finally:
        py.close()
        cpp.close()


def test_cql_duration_between_seconds_unchanged_by_age_carve_out() -> None:
    """The carve-out boundary: generic duration/difference keep §22.21 exactly.

    Same operands as ``SecondsOneSecond`` above. The age is crisp because it
    opted in (``treat_second_as_exact=True``); ``duration in seconds between``
    and the ``cqlDurationBetween`` UDF keep the strict "one component finer than
    the target" rule, which the official fixtures pin (``months between
    @2012-01-02 and @2012`` -> ``Interval[0, 10]``). ``difference in seconds``
    counts CROSSED boundaries, so it is crisp by its own §8.7 rule.
    """
    duration_seconds_interval = '{"start":0,"end":1,"lowClosed":true,"highClosed":true}'
    months_spec_example = '{"start":0,"end":10,"lowClosed":true,"highClosed":true}'

    direct = {
        "SELECT cqlDurationBetween('2000-05-15T00:00:00Z', '2000-05-15T00:00:01Z', 'second')":
            duration_seconds_interval,
        "SELECT cqlDurationBetween('2012-01-02', '2012', 'month')": months_spec_example,
        "SELECT cqlDifferenceBetween('2000-05-15T00:00:00Z', '2000-05-15T00:00:01Z', 'second')":
            "1",
    }
    library = """library FHIR471DurationBoundary version '1.0.0'
using FHIR version '4.0.1'
context Patient
define DurationSeconds: duration in seconds between @2000-05-15T00:00:00Z and @2000-05-15T00:00:01Z
define DifferenceSeconds: difference in seconds between @2000-05-15T00:00:00Z and @2000-05-15T00:00:01Z
define MonthsSpecExample: duration in months between @2012-01-02 and @2012
"""
    translated = {name: expr.to_sql() for name, expr in translate_cql(library).items()}
    translated_expected = {
        "DurationSeconds": duration_seconds_interval,
        "DifferenceSeconds": "1",
        "MonthsSpecExample": months_spec_example,
    }
    # The generic duration lowering really is the shared UDF — i.e. the age
    # carve-out cannot have leaked into it by accident.
    assert "cqlDurationBetween(" in translated["DurationSeconds"]
    assert "cqlDurationBetween(" in translated["MonthsSpecExample"]

    py = _python_only_connection()
    cpp = _cpp_connection()
    try:
        for statement, expected in direct.items():
            assert py.execute(statement).fetchone() == (expected,), statement
            assert cpp.execute(statement).fetchone() == (expected,), statement
        for name, sql in translated.items():
            row = py.execute(f"SELECT {sql}").fetchone()
            assert row == (translated_expected[name],), f"python {name}: {row!r}"
            row = cpp.execute(f"SELECT {sql}").fetchone()
            assert row == (translated_expected[name],), f"cpp {name}: {row!r}"
        with no_python_connection() as no_py:
            for statement, expected in direct.items():
                assert no_py.execute(statement).fetchone() == (expected,), statement
            for name, sql in translated.items():
                row = no_py.execute(f"SELECT {sql}").fetchone()
                assert row == (translated_expected[name],), f"no-python {name}: {row!r}"
    finally:
        py.close()
        cpp.close()
