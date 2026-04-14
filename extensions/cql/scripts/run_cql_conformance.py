#!/usr/bin/env python3
"""
CQL C++ Extension Conformance Test Runner

Translates the Python CQL UDF test suite (duckdb-cql-py/tests/) into SQL queries
and runs them against the C++ extension to verify behavioral parity.

Usage:
    # With C++ extension:
    python scripts/run_cql_conformance.py --extension build/release/extension/cql/cql.duckdb_extension

    # With Python UDFs (reference baseline):
    python scripts/run_cql_conformance.py --python

    # Filter by module:
    python scripts/run_cql_conformance.py --extension ... --module age

    # Verbose output (show failures):
    python scripts/run_cql_conformance.py --extension ... -v
"""

import argparse
import json
import math
import os
import sys
import traceback
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import duckdb

# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self, name: str, module: str, passed: bool, expected: Any = None,
                 actual: Any = None, error: str = ""):
        self.name = name
        self.module = module
        self.passed = passed
        self.expected = expected
        self.actual = actual
        self.error = error

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        if not self.passed:
            return f"[{status}] {self.module}/{self.name}: expected={self.expected}, actual={self.actual} {self.error}"
        return f"[{status}] {self.module}/{self.name}"


class ConformanceRunner:
    def __init__(self, con: duckdb.DuckDBPyConnection, verbose: bool = False):
        self.con = con
        self.verbose = verbose
        self.results: List[TestResult] = []

    def query_scalar(self, sql: str, params: list = None) -> Any:
        """Execute a query and return the scalar result."""
        try:
            if params:
                result = self.con.execute(sql, params).fetchone()
            else:
                result = self.con.execute(sql).fetchone()
            return result[0] if result else None
        except Exception as e:
            return ("ERROR", str(e))

    def assert_eq(self, name: str, module: str, sql: str, expected: Any,
                  params: list = None, approx: bool = False, tol: float = 0.01):
        """Assert that a SQL query returns the expected value."""
        actual = self.query_scalar(sql, params)

        if isinstance(actual, tuple) and len(actual) == 2 and actual[0] == "ERROR":
            self.results.append(TestResult(name, module, False, expected, actual[1], "SQL error"))
            return

        passed = False
        if expected is None:
            passed = actual is None
        elif approx and expected is not None and actual is not None:
            try:
                passed = math.isclose(float(actual), float(expected), rel_tol=tol)
            except (TypeError, ValueError):
                passed = False
        elif isinstance(expected, bool):
            passed = actual == expected
        elif isinstance(expected, (int, float)) and actual is not None:
            try:
                passed = float(actual) == float(expected)
            except (TypeError, ValueError):
                passed = actual == expected
        else:
            passed = actual == expected

        self.results.append(TestResult(name, module, passed, expected, actual))

    def assert_gte(self, name: str, module: str, sql: str, min_val: Any, params: list = None):
        """Assert that a SQL query returns a value >= min_val."""
        actual = self.query_scalar(sql, params)
        if isinstance(actual, tuple) and len(actual) == 2 and actual[0] == "ERROR":
            self.results.append(TestResult(name, module, False, f">={min_val}", actual[1], "SQL error"))
            return
        passed = actual is not None and actual >= min_val
        self.results.append(TestResult(name, module, passed, f">={min_val}", actual))

    def assert_not_none(self, name: str, module: str, sql: str, params: list = None):
        """Assert that a SQL query returns a non-NULL value."""
        actual = self.query_scalar(sql, params)
        if isinstance(actual, tuple) and len(actual) == 2 and actual[0] == "ERROR":
            self.results.append(TestResult(name, module, False, "not None", actual[1], "SQL error"))
            return
        passed = actual is not None
        self.results.append(TestResult(name, module, passed, "not None", actual))

    def assert_contains(self, name: str, module: str, sql: str, substring: str, params: list = None):
        """Assert that a SQL query result contains a substring."""
        actual = self.query_scalar(sql, params)
        if isinstance(actual, tuple) and len(actual) == 2 and actual[0] == "ERROR":
            self.results.append(TestResult(name, module, False, f"contains '{substring}'", actual[1], "SQL error"))
            return
        passed = actual is not None and substring in str(actual)
        self.results.append(TestResult(name, module, passed, f"contains '{substring}'", actual))

    def assert_json_field(self, name: str, module: str, sql: str, field: str,
                          expected: Any, params: list = None, approx: bool = False, tol: float = 0.01):
        """Assert that a SQL query returns JSON and a specific field has the expected value."""
        actual_raw = self.query_scalar(sql, params)
        if isinstance(actual_raw, tuple) and len(actual_raw) == 2 and actual_raw[0] == "ERROR":
            self.results.append(TestResult(name, module, False, expected, actual_raw[1], "SQL error"))
            return
        if actual_raw is None:
            self.results.append(TestResult(name, module, expected is None, expected, None))
            return
        try:
            parsed = json.loads(actual_raw)
            actual = parsed.get(field)
            if approx and expected is not None and actual is not None:
                passed = math.isclose(float(actual), float(expected), rel_tol=tol)
            elif isinstance(expected, (int, float)) and actual is not None:
                passed = float(actual) == float(expected)
            else:
                passed = actual == expected
            self.results.append(TestResult(name, module, passed, expected, actual))
        except (json.JSONDecodeError, TypeError) as e:
            self.results.append(TestResult(name, module, False, expected, actual_raw, f"JSON parse: {e}"))

    def assert_in_set(self, name: str, module: str, sql: str, valid_set: set, params: list = None):
        """Assert that result is in a set of valid values."""
        actual = self.query_scalar(sql, params)
        if isinstance(actual, tuple) and len(actual) == 2 and actual[0] == "ERROR":
            self.results.append(TestResult(name, module, False, f"in {valid_set}", actual[1], "SQL error"))
            return
        passed = actual in valid_set
        self.results.append(TestResult(name, module, passed, f"in {valid_set}", actual))

    def report(self) -> dict:
        """Print summary and return stats."""
        modules: Dict[str, Dict[str, int]] = {}
        for r in self.results:
            if r.module not in modules:
                modules[r.module] = {"pass": 0, "fail": 0}
            if r.passed:
                modules[r.module]["pass"] += 1
            else:
                modules[r.module]["fail"] += 1

        total_pass = sum(m["pass"] for m in modules.values())
        total_fail = sum(m["fail"] for m in modules.values())
        total = total_pass + total_fail

        print("\n" + "=" * 70)
        print("CQL C++ EXTENSION CONFORMANCE REPORT")
        print("=" * 70)
        print(f"{'Module':<25} {'Pass':>6} {'Fail':>6} {'Total':>6} {'Rate':>8}")
        print("-" * 70)
        for mod in sorted(modules.keys()):
            m = modules[mod]
            t = m["pass"] + m["fail"]
            rate = f"{100 * m['pass'] / t:.1f}%" if t > 0 else "N/A"
            print(f"{mod:<25} {m['pass']:>6} {m['fail']:>6} {t:>6} {rate:>8}")
        print("-" * 70)
        rate = f"{100 * total_pass / total:.1f}%" if total > 0 else "N/A"
        print(f"{'TOTAL':<25} {total_pass:>6} {total_fail:>6} {total:>6} {rate:>8}")
        print("=" * 70)

        if self.verbose:
            failures = [r for r in self.results if not r.passed]
            if failures:
                print(f"\n--- FAILURES ({len(failures)}) ---")
                for r in failures:
                    print(f"  {r}")

        return {"total": total, "pass": total_pass, "fail": total_fail, "modules": modules}


# ---------------------------------------------------------------------------
# Test modules
# ---------------------------------------------------------------------------

PATIENT = '{"resourceType": "Patient", "birthDate": "1990-05-15"}'
PATIENT_NO_BD = '{"resourceType": "Patient", "name": [{"family": "Doe"}]}'
INVALID_JSON = '{"resourceType": "Patient", "birthDate": "invalid'


def test_age(r: ConformanceRunner):
    """Age UDF tests (33 tests from test_age_udfs.py)."""
    M = "age"
    p = PATIENT

    # ageInYears
    r.assert_gte("ageInYears_valid", M, "SELECT AgeInYears(?)", 34, [p])
    r.assert_eq("ageInYears_null", M, "SELECT AgeInYears(NULL)", None)
    r.assert_eq("ageInYears_missing_bd", M, "SELECT AgeInYears(?)", None, [PATIENT_NO_BD])
    r.assert_eq("ageInYears_invalid_json", M, "SELECT AgeInYears(?)", None, [INVALID_JSON])
    r.assert_eq("ageInYears_empty", M, "SELECT AgeInYears('')", None)

    # ageInMonths
    r.assert_gte("ageInMonths_valid", M, "SELECT AgeInMonths(?)", 400, [p])
    r.assert_eq("ageInMonths_null", M, "SELECT AgeInMonths(NULL)", None)
    r.assert_eq("ageInMonths_missing_bd", M, "SELECT AgeInMonths(?)", None, [PATIENT_NO_BD])

    # ageInDays
    r.assert_gte("ageInDays_valid", M, "SELECT AgeInDays(?)", 12000, [p])
    r.assert_eq("ageInDays_null", M, "SELECT AgeInDays(NULL)", None)

    # ageInHours
    r.assert_gte("ageInHours_valid", M, "SELECT AgeInHours(?)", 300000, [p])
    r.assert_eq("ageInHours_null", M, "SELECT AgeInHours(NULL)", None)

    # ageInMinutes
    r.assert_gte("ageInMinutes_valid", M, "SELECT AgeInMinutes(?)", 18000000, [p])
    r.assert_eq("ageInMinutes_null", M, "SELECT AgeInMinutes(NULL)", None)

    # ageInSeconds
    r.assert_gte("ageInSeconds_valid", M, "SELECT AgeInSeconds(?)", 1000000000, [p])
    r.assert_eq("ageInSeconds_null", M, "SELECT AgeInSeconds(NULL)", None)

    # ageInYearsAt
    r.assert_eq("ageInYearsAt_valid", M, "SELECT AgeInYearsAt(?, '2020-05-15')", 30, [p])
    r.assert_eq("ageInYearsAt_before_bd", M, "SELECT AgeInYearsAt(?, '2020-05-14')", 29, [p])
    r.assert_eq("ageInYearsAt_after_bd", M, "SELECT AgeInYearsAt(?, '2020-05-16')", 30, [p])
    r.assert_eq("ageInYearsAt_null_resource", M, "SELECT AgeInYearsAt(NULL, '2020-01-01')", None)
    r.assert_eq("ageInYearsAt_null_date", M, "SELECT AgeInYearsAt(?, NULL)", None, [p])
    r.assert_eq("ageInYearsAt_invalid_date", M, "SELECT AgeInYearsAt(?, 'not-a-date')", None, [p])
    r.assert_eq("ageInYearsAt_datetime_fmt", M, "SELECT AgeInYearsAt(?, '2020-05-15T10:30:00Z')", 30, [p])

    # ageInMonthsAt
    r.assert_eq("ageInMonthsAt_valid", M, "SELECT AgeInMonthsAt(?, '2020-05-15')", 360, [p])
    r.assert_eq("ageInMonthsAt_before_bd", M, "SELECT AgeInMonthsAt(?, '2020-05-14')", 359, [p])
    r.assert_eq("ageInMonthsAt_null_resource", M, "SELECT AgeInMonthsAt(NULL, '2020-01-01')", None)

    # ageInDaysAt
    r.assert_eq("ageInDaysAt_5days", M, "SELECT AgeInDaysAt(?, '1990-05-20')", 5, [p])
    r.assert_eq("ageInDaysAt_1year", M, "SELECT AgeInDaysAt(?, '1991-05-15')", 365, [p])
    r.assert_eq("ageInDaysAt_null_resource", M, "SELECT AgeInDaysAt(NULL, '2020-01-01')", None)
    r.assert_eq("ageInDaysAt_before_birth", M, "SELECT AgeInDaysAt(?, '1990-05-10')", 0, [p])

    # Registration tests (all functions callable)
    r.assert_not_none("reg_ageInYears", M, "SELECT AgeInYears(?)", [p])
    r.assert_not_none("reg_ageInMonths", M, "SELECT AgeInMonths(?)", [p])
    r.assert_not_none("reg_ageInDays", M, "SELECT AgeInDays(?)", [p])


def test_datetime(r: ConformanceRunner):
    """DateTime UDF tests (51 tests from test_datetime_udfs.py).

    Python differenceInYears/Months use BOUNDARY CROSSING semantics:
      differenceInYears("2020-06-15", "2025-01-01") = 5 (e.year - s.year)
      differenceInMonths("2020-01-15", "2020-02-10") = 1 ((e.year-s.year)*12 + e.month-s.month)
    Python differenceInDays uses actual day difference: (e - s).days
    """
    M = "datetime"

    # differenceInYears (boundary crossings: e.year - s.year)
    r.assert_eq("years_exact", M, "SELECT differenceInYears('2020-01-01', '2025-01-01')", 5)
    r.assert_eq("years_partial", M, "SELECT differenceInYears('2020-06-15', '2025-01-01')", 5)
    r.assert_eq("years_same", M, "SELECT differenceInYears('2020-01-01', '2020-01-01')", 0)
    r.assert_eq("years_negative", M, "SELECT differenceInYears('2025-01-01', '2020-01-01')", -5)
    r.assert_eq("years_null_start", M, "SELECT differenceInYears(NULL, '2020-01-01')", None)
    r.assert_eq("years_null_end", M, "SELECT differenceInYears('2020-01-01', NULL)", None)
    r.assert_eq("years_both_null", M, "SELECT differenceInYears(NULL, NULL)", None)
    r.assert_eq("years_invalid", M, "SELECT differenceInYears('not-a-date', '2020-01-01')", None)

    # differenceInMonths (boundary crossings: (e.year-s.year)*12 + e.month-s.month)
    r.assert_eq("months_exact", M, "SELECT differenceInMonths('2020-01-01', '2020-06-01')", 5)
    r.assert_eq("months_across_years", M, "SELECT differenceInMonths('2020-06-01', '2022-03-01')", 21)
    r.assert_eq("months_partial", M, "SELECT differenceInMonths('2020-01-15', '2020-02-10')", 1)
    r.assert_eq("months_same", M, "SELECT differenceInMonths('2020-01-01', '2020-01-01')", 0)
    r.assert_eq("months_null_start", M, "SELECT differenceInMonths(NULL, '2020-01-01')", None)
    r.assert_eq("months_null_end", M, "SELECT differenceInMonths('2020-01-01', NULL)", None)

    # weeksBetween
    r.assert_eq("weeks_exact", M, "SELECT weeksBetween('2020-01-01', '2020-01-22')", 3)
    r.assert_eq("weeks_partial", M, "SELECT weeksBetween('2020-01-01', '2020-01-10')", 1)
    r.assert_eq("weeks_same", M, "SELECT weeksBetween('2020-01-01', '2020-01-01')", 0)
    r.assert_eq("weeks_null_start", M, "SELECT weeksBetween(NULL, '2020-01-01')", None)
    r.assert_eq("weeks_null_end", M, "SELECT weeksBetween('2020-01-01', NULL)", None)

    # differenceInDays (actual day difference: (e - s).days)
    r.assert_eq("days_positive", M, "SELECT differenceInDays('2020-01-01', '2020-01-11')", 10)
    r.assert_eq("days_negative", M, "SELECT differenceInDays('2020-01-11', '2020-01-01')", -10)
    r.assert_eq("days_same", M, "SELECT differenceInDays('2020-01-01', '2020-01-01')", 0)
    r.assert_eq("days_null_start", M, "SELECT differenceInDays(NULL, '2020-01-01')", None)
    r.assert_eq("days_null_end", M, "SELECT differenceInDays('2020-01-01', NULL)", None)
    r.assert_eq("days_invalid", M, "SELECT differenceInDays('invalid', '2020-01-01')", None)

    # differenceInHours (truncated: total_seconds // 3600)
    r.assert_eq("hours_positive", M, "SELECT differenceInHours('2020-01-01T00:00:00Z', '2020-01-01T10:00:00Z')", 10)
    r.assert_eq("hours_24", M, "SELECT differenceInHours('2020-01-01T00:00:00Z', '2020-01-02T00:00:00Z')", 24)
    r.assert_eq("hours_partial", M, "SELECT differenceInHours('2020-01-01T00:00:00Z', '2020-01-01T05:30:00Z')", 5)
    r.assert_eq("hours_null_start", M, "SELECT differenceInHours(NULL, '2020-01-01T00:00:00Z')", None)
    r.assert_eq("hours_null_end", M, "SELECT differenceInHours('2020-01-01T00:00:00Z', NULL)", None)
    r.assert_eq("hours_invalid", M, "SELECT differenceInHours('not-datetime', '2020-01-01T00:00:00Z')", None)

    # differenceInMinutes (truncated: total_seconds // 60)
    r.assert_eq("minutes_positive", M, "SELECT differenceInMinutes('2020-01-01T00:00:00Z', '2020-01-01T01:30:00Z')", 90)
    r.assert_eq("minutes_one_hour", M, "SELECT differenceInMinutes('2020-01-01T00:00:00Z', '2020-01-01T01:00:00Z')", 60)
    r.assert_eq("minutes_partial", M, "SELECT differenceInMinutes('2020-01-01T00:00:00Z', '2020-01-01T00:05:30Z')", 5)
    r.assert_eq("minutes_null_start", M, "SELECT differenceInMinutes(NULL, '2020-01-01T00:00:00Z')", None)
    r.assert_eq("minutes_null_end", M, "SELECT differenceInMinutes('2020-01-01T00:00:00Z', NULL)", None)

    # differenceInSeconds
    r.assert_eq("seconds_positive", M, "SELECT differenceInSeconds('2020-01-01T00:00:00Z', '2020-01-01T00:01:30Z')", 90)
    r.assert_eq("seconds_one_min", M, "SELECT differenceInSeconds('2020-01-01T00:00:00Z', '2020-01-01T00:01:00Z')", 60)
    r.assert_eq("seconds_null_start", M, "SELECT differenceInSeconds(NULL, '2020-01-01T00:00:00Z')", None)
    r.assert_eq("seconds_null_end", M, "SELECT differenceInSeconds('2020-01-01T00:00:00Z', NULL)", None)

    # millisecondsBetween
    r.assert_eq("ms_one_sec", M, "SELECT millisecondsBetween('2020-01-01T00:00:00Z', '2020-01-01T00:00:01Z')", 1000)
    r.assert_eq("ms_partial", M, "SELECT millisecondsBetween('2020-01-01T00:00:00Z', '2020-01-01T00:00:00.500Z')", 500)
    r.assert_eq("ms_null_start", M, "SELECT millisecondsBetween(NULL, '2020-01-01T00:00:00Z')", None)
    r.assert_eq("ms_null_end", M, "SELECT millisecondsBetween('2020-01-01T00:00:00Z', NULL)", None)

    # dateTimeSameAs / SameOrBefore / SameOrAfter (C++ takes 3 args: dt1, dt2, precision)
    r.assert_eq("sameAs_true", M, "SELECT dateTimeSameAs('2020-01-01', '2020-01-01', 'day')", True)
    r.assert_eq("sameAs_false", M, "SELECT dateTimeSameAs('2020-01-01', '2020-01-02', 'day')", False)
    r.assert_eq("sameOrBefore_eq", M, "SELECT dateTimeSameOrBefore('2020-01-01', '2020-01-01', 'day')", True)
    r.assert_eq("sameOrBefore_before", M, "SELECT dateTimeSameOrBefore('2020-01-01', '2020-01-02', 'day')", True)
    r.assert_eq("sameOrBefore_after", M, "SELECT dateTimeSameOrBefore('2020-01-02', '2020-01-01', 'day')", False)
    r.assert_eq("sameOrAfter_eq", M, "SELECT dateTimeSameOrAfter('2020-01-01', '2020-01-01', 'day')", True)
    r.assert_eq("sameOrAfter_after", M, "SELECT dateTimeSameOrAfter('2020-01-02', '2020-01-01', 'day')", True)
    r.assert_eq("sameOrAfter_before", M, "SELECT dateTimeSameOrAfter('2020-01-01', '2020-01-02', 'day')", False)

    # Edge cases
    r.assert_eq("tz_positive", M, "SELECT differenceInHours('2020-01-01T00:00:00+00:00', '2020-01-01T05:00:00+00:00')", 5)
    r.assert_eq("z_suffix", M, "SELECT differenceInHours('2020-01-01T00:00:00Z', '2020-01-01T05:00:00Z')", 5)
    r.assert_eq("date_trunc", M, "SELECT differenceInDays('2020-01-01T10:00:00Z', '2020-01-11T10:00:00Z')", 10)
    r.assert_eq("empty_start", M, "SELECT differenceInYears('', '2020-01-01')", None)
    r.assert_eq("empty_end", M, "SELECT differenceInYears('2020-01-01', '')", None)


def test_interval(r: ConformanceRunner):
    """Interval UDF tests (51 tests from test_interval_udfs.py)."""
    M = "interval"

    closed = '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    open_iv = '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": false, "highClosed": false}'
    left_closed = '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": false}'
    dt_interval = '{"low": "2024-01-01T00:00:00Z", "high": "2024-01-01T23:59:59Z", "lowClosed": true, "highClosed": true}'

    # intervalStart
    r.assert_eq("start_closed", M, "SELECT intervalStart(?)", "2024-01-01", [closed])
    r.assert_contains("start_datetime", M, "SELECT intervalStart(?)", "2024-01-01", [dt_interval])
    r.assert_eq("start_null", M, "SELECT intervalStart(NULL)", None)
    r.assert_eq("start_empty", M, "SELECT intervalStart('')", None)
    r.assert_eq("start_invalid", M, "SELECT intervalStart(?)", None, ["not json"])

    # intervalEnd
    r.assert_eq("end_closed", M, "SELECT intervalEnd(?)", "2024-12-31", [closed])
    r.assert_contains("end_datetime", M, "SELECT intervalEnd(?)", "2024-01-01", [dt_interval])
    r.assert_eq("end_null", M, "SELECT intervalEnd(NULL)", None)
    r.assert_eq("end_empty", M, "SELECT intervalEnd('')", None)

    # intervalWidth
    r.assert_eq("width_year", M, "SELECT intervalWidth(?)", 365, [closed])
    month_iv = '{"low": "2024-01-01", "high": "2024-01-31", "lowClosed": true, "highClosed": true}'
    r.assert_eq("width_month", M, "SELECT intervalWidth(?)", 30, [month_iv])
    single_day = '{"low": "2024-01-01", "high": "2024-01-01", "lowClosed": true, "highClosed": true}'
    r.assert_eq("width_single_day", M, "SELECT intervalWidth(?)", 0, [single_day])
    r.assert_eq("width_null", M, "SELECT intervalWidth(NULL)", None)
    missing_bounds = '{"low": null, "high": "2024-01-31"}'
    r.assert_eq("width_missing_bounds", M, "SELECT intervalWidth(?)", None, [missing_bounds])

    # intervalContains
    r.assert_eq("contains_middle", M, "SELECT intervalContains(?, '2024-06-15')", True, [closed])
    r.assert_eq("contains_start_closed", M, "SELECT intervalContains(?, '2024-01-01')", True, [closed])
    r.assert_eq("contains_end_closed", M, "SELECT intervalContains(?, '2024-12-31')", True, [closed])
    r.assert_eq("contains_start_open", M, "SELECT intervalContains(?, '2024-01-01')", False, [open_iv])
    r.assert_eq("contains_end_open", M, "SELECT intervalContains(?, '2024-12-31')", False, [open_iv])
    r.assert_eq("contains_before", M, "SELECT intervalContains(?, '2023-12-31')", False, [closed])
    r.assert_eq("contains_after", M, "SELECT intervalContains(?, '2025-01-01')", False, [closed])
    r.assert_eq("contains_null_iv", M, "SELECT intervalContains(NULL, '2024-06-15')", False)
    r.assert_eq("contains_null_point", M, "SELECT intervalContains(?, NULL)", False, [closed])
    r.assert_eq("contains_both_null", M, "SELECT intervalContains(NULL, NULL)", False)

    # intervalProperlyContains
    r.assert_eq("properly_middle", M, "SELECT intervalProperlyContains(?, '2024-06-15')", True, [closed])
    r.assert_eq("properly_start", M, "SELECT intervalProperlyContains(?, '2024-01-01')", False, [closed])
    r.assert_eq("properly_end", M, "SELECT intervalProperlyContains(?, '2024-12-31')", False, [closed])
    r.assert_eq("properly_null", M, "SELECT intervalProperlyContains(NULL, '2024-06-15')", False)

    # intervalOverlaps
    iv_a = '{"low": "2024-01-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    iv_b = '{"low": "2024-06-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    iv_big = '{"low": "2024-01-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    iv_small = '{"low": "2024-03-01", "high": "2024-06-30", "lowClosed": true, "highClosed": true}'
    iv_non_overlap = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    iv_early = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'

    r.assert_eq("overlaps_partial", M, "SELECT intervalOverlaps(?, ?)", True, [iv_a, iv_b])
    r.assert_eq("overlaps_contained", M, "SELECT intervalOverlaps(?, ?)", True, [iv_big, iv_small])
    r.assert_eq("overlaps_not", M, "SELECT intervalOverlaps(?, ?)", False, [iv_early, iv_non_overlap])
    r.assert_eq("overlaps_identical", M, "SELECT intervalOverlaps(?, ?)", True, [closed, closed])
    r.assert_eq("overlaps_null_first", M, "SELECT intervalOverlaps(NULL, ?)", False, [iv_b])
    r.assert_eq("overlaps_null_second", M, "SELECT intervalOverlaps(?, NULL)", False, [closed])

    # intervalBefore
    r.assert_eq("before_true", M, "SELECT intervalBefore(?, ?)", True, [iv_early, iv_non_overlap])
    r.assert_eq("before_false_overlap", M, "SELECT intervalBefore(?, ?)", False, [iv_a, iv_b])
    r.assert_eq("before_false_after", M, "SELECT intervalBefore(?, ?)", False, [iv_b, iv_early])
    r.assert_eq("before_null", M, "SELECT intervalBefore(NULL, ?)", False, [iv_b])

    # intervalAfter
    r.assert_eq("after_true", M, "SELECT intervalAfter(?, ?)", True, [iv_non_overlap, iv_early])
    r.assert_eq("after_false_overlap", M, "SELECT intervalAfter(?, ?)", False, [iv_b, iv_a])
    r.assert_eq("after_false_before", M, "SELECT intervalAfter(?, ?)", False, [iv_early, iv_non_overlap])
    r.assert_eq("after_null", M, "SELECT intervalAfter(NULL, ?)", False, [iv_b])

    # intervalMeets
    meets_a = '{"low": "2024-01-01", "high": "2024-03-31", "lowClosed": true, "highClosed": true}'
    meets_b = '{"low": "2024-03-31", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'
    no_meet = '{"low": "2024-01-01", "high": "2024-03-30", "lowClosed": true, "highClosed": true}'
    no_meet_b = '{"low": "2024-04-01", "high": "2024-12-31", "lowClosed": true, "highClosed": true}'

    r.assert_eq("meets_true", M, "SELECT intervalMeets(?, ?)", True, [meets_a, meets_b])
    r.assert_eq("meets_false_gap", M, "SELECT intervalMeets(?, ?)", False, [no_meet, no_meet_b])
    r.assert_eq("meets_false_overlap", M, "SELECT intervalMeets(?, ?)", False, [iv_a, iv_b])
    r.assert_eq("meets_null", M, "SELECT intervalMeets(NULL, ?)", False, [iv_b])

    # Edge cases
    default_bounds = '{"low": "2024-01-01", "high": "2024-12-31"}'
    r.assert_eq("default_bounds_start", M, "SELECT intervalContains(?, '2024-01-01')", True, [default_bounds])
    r.assert_eq("default_bounds_end", M, "SELECT intervalContains(?, '2024-12-31')", True, [default_bounds])
    r.assert_eq("invalid_json_start", M, "SELECT intervalStart('not valid json')", None)
    r.assert_eq("invalid_json_end", M, "SELECT intervalEnd('not valid json')", None)
    r.assert_eq("invalid_json_width", M, "SELECT intervalWidth('not valid json')", None)
    r.assert_eq("invalid_json_contains", M, "SELECT intervalContains('not valid json', '2024-01-01')", False)
    missing = '{"lowClosed": true, "highClosed": true}'
    r.assert_eq("missing_start", M, "SELECT intervalStart(?)", None, [missing])
    r.assert_eq("missing_end", M, "SELECT intervalEnd(?)", None, [missing])
    r.assert_eq("missing_width", M, "SELECT intervalWidth(?)", None, [missing])


def test_quantity(r: ConformanceRunner):
    """Quantity UDF tests (45 tests from test_quantity_udf.py)."""
    M = "quantity"

    bp_sys = '{"value": 140, "code": "mm[Hg]", "system": "http://unitsofmeasure.org"}'
    bp_dia = '{"value": 120, "code": "mm[Hg]", "system": "http://unitsofmeasure.org"}'
    wt_g = '{"value": 1, "code": "g"}'
    wt_mg = '{"value": 500, "code": "mg"}'

    # parseQuantity
    r.assert_not_none("parse_valid", M, "SELECT parseQuantity(?)", [bp_sys])
    r.assert_eq("parse_null", M, "SELECT parseQuantity(NULL)", None)
    r.assert_eq("parse_empty", M, "SELECT parseQuantity('')", None)
    r.assert_eq("parse_invalid", M, "SELECT parseQuantity('not json')", None)
    # parseQuantity with missing value
    r.assert_not_none("parse_missing_value", M, "SELECT parseQuantity('{\"code\": \"mg\"}')")

    # quantityValue
    r.assert_eq("value_valid", M, "SELECT quantityValue(?)", 140.0, [bp_sys])
    r.assert_eq("value_null", M, "SELECT quantityValue(NULL)", None)
    r.assert_eq("value_empty", M, "SELECT quantityValue('')", None)
    r.assert_eq("value_missing", M, "SELECT quantityValue('{\"code\": \"mg\"}')", None)

    # quantityUnit
    r.assert_eq("unit_valid", M, "SELECT quantityUnit(?)", "mm[Hg]", [bp_sys])
    r.assert_eq("unit_null", M, "SELECT quantityUnit(NULL)", None)
    r.assert_eq("unit_empty", M, "SELECT quantityUnit('')", None)
    r.assert_eq("unit_uses_unit_field", M, "SELECT quantityUnit('{\"value\": 100, \"unit\": \"kg\"}')", "kg")

    # quantityCompare — same units
    r.assert_eq("cmp_gt_same", M, "SELECT quantityCompare(?, ?, '>')", True, [bp_sys, bp_dia])
    r.assert_eq("cmp_lt_same", M, "SELECT quantityCompare(?, ?, '<')", True, [bp_dia, bp_sys])
    r.assert_eq("cmp_gte_same", M,
                "SELECT quantityCompare('{\"value\":140,\"code\":\"mm[Hg]\"}', '{\"value\":140,\"code\":\"mm[Hg]\"}', '>=')", True)
    r.assert_eq("cmp_lte_same", M,
                "SELECT quantityCompare('{\"value\":140,\"code\":\"mm[Hg]\"}', '{\"value\":140,\"code\":\"mm[Hg]\"}', '<=')", True)
    r.assert_eq("cmp_eq_same", M,
                "SELECT quantityCompare('{\"value\":140,\"code\":\"mm[Hg]\"}', '{\"value\":140,\"code\":\"mm[Hg]\"}', '==')", True)
    r.assert_eq("cmp_ne_same", M, "SELECT quantityCompare(?, ?, '!=')", True, [bp_sys, bp_dia])

    # quantityCompare — different units
    r.assert_eq("cmp_gt_diff", M, "SELECT quantityCompare(?, ?, '>')", True, [wt_g, wt_mg])
    r.assert_eq("cmp_lt_diff", M, "SELECT quantityCompare(?, ?, '<')", True, [wt_mg, wt_g])
    r.assert_eq("cmp_eq_diff", M,
                "SELECT quantityCompare('{\"value\":1,\"code\":\"g\"}', '{\"value\":1000,\"code\":\"mg\"}', '==')", True)

    # quantityCompare — incompatible units
    r.assert_eq("cmp_incompat_1", M,
                "SELECT quantityCompare('{\"value\":100,\"code\":\"mg/dL\"}', '{\"value\":120,\"code\":\"mm[Hg]\"}', '>')", None)
    r.assert_eq("cmp_incompat_2", M,
                "SELECT quantityCompare('{\"value\":100,\"code\":\"kg\"}', '{\"value\":100,\"code\":\"L\"}', '>')", None)

    # quantityAdd
    r.assert_json_field("add_same", M, "SELECT quantityAdd('{\"value\":5,\"code\":\"mg\"}', '{\"value\":3,\"code\":\"mg\"}')",
                        "value", 8.0)
    r.assert_json_field("add_same_unit", M, "SELECT quantityAdd('{\"value\":5,\"code\":\"mg\"}', '{\"value\":3,\"code\":\"mg\"}')",
                        "code", "mg")
    r.assert_json_field("add_diff", M, "SELECT quantityAdd('{\"value\":1,\"code\":\"g\"}', '{\"value\":500,\"code\":\"mg\"}')",
                        "value", 1.5)
    r.assert_eq("add_incompat", M,
                "SELECT quantityAdd('{\"value\":100,\"code\":\"kg\"}', '{\"value\":50,\"code\":\"mm[Hg]\"}')", None)
    r.assert_eq("add_null_first", M, "SELECT quantityAdd(NULL, '{\"value\":5,\"code\":\"mg\"}')", None)
    r.assert_eq("add_null_second", M, "SELECT quantityAdd('{\"value\":5,\"code\":\"mg\"}', NULL)", None)

    # quantitySubtract
    r.assert_json_field("sub_same", M,
                        "SELECT quantitySubtract('{\"value\":10,\"code\":\"mg\"}', '{\"value\":3,\"code\":\"mg\"}')",
                        "value", 7.0)
    r.assert_json_field("sub_same_unit", M,
                        "SELECT quantitySubtract('{\"value\":10,\"code\":\"mg\"}', '{\"value\":3,\"code\":\"mg\"}')",
                        "code", "mg")
    r.assert_json_field("sub_diff", M,
                        "SELECT quantitySubtract('{\"value\":2,\"code\":\"g\"}', '{\"value\":500,\"code\":\"mg\"}')",
                        "value", 1.5)
    r.assert_eq("sub_incompat", M,
                "SELECT quantitySubtract('{\"value\":100,\"code\":\"kg\"}', '{\"value\":50,\"code\":\"mm[Hg]\"}')", None)
    r.assert_eq("sub_null", M, "SELECT quantitySubtract('{\"value\":10,\"code\":\"mg\"}', NULL)", None)

    # quantityConvert
    r.assert_json_field("convert_g_to_mg", M,
                        "SELECT quantityConvert('{\"value\":1,\"code\":\"g\"}', 'mg')", "value", 1000.0)
    r.assert_json_field("convert_mg_to_g", M,
                        "SELECT quantityConvert('{\"value\":500,\"code\":\"mg\"}', 'g')", "value", 0.5)
    r.assert_json_field("convert_same", M,
                        "SELECT quantityConvert('{\"value\":100,\"code\":\"mg\"}', 'mg')", "value", 100.0)
    r.assert_eq("convert_incompat", M,
                "SELECT quantityConvert('{\"value\":100,\"code\":\"kg\"}', 'mm[Hg]')", None)
    r.assert_eq("convert_null", M, "SELECT quantityConvert(NULL, 'mg')", None)

    # Edge cases
    r.assert_eq("unit_field", M, "SELECT quantityValue('{\"value\":100,\"unit\":\"kg\"}')", 100.0)
    r.assert_eq("negative_value", M, "SELECT quantityValue('{\"value\":-10,\"code\":\"mg\"}')", -10.0)
    r.assert_eq("float_value", M, "SELECT quantityValue('{\"value\":3.14159,\"code\":\"mg\"}')", 3.14159,
                approx=True, tol=0.0001)
    r.assert_eq("cmp_null_op", M, "SELECT quantityCompare('{\"value\":100,\"code\":\"mg\"}', NULL, '>')", None)
    r.assert_eq("cmp_null_op2", M, "SELECT quantityCompare(NULL, '{\"value\":100,\"code\":\"mg\"}', '>')", None)
    r.assert_eq("cmp_invalid_op", M,
                "SELECT quantityCompare('{\"value\":100,\"code\":\"mg\"}', '{\"value\":50,\"code\":\"mg\"}', 'invalid')", None)


def test_ratio(r: ConformanceRunner):
    """Ratio UDF tests (33 tests from test_ratio_udfs.py)."""
    M = "ratio"

    simple = '{"numerator": {"value": 5, "unit": "mg"}, "denominator": {"value": 1, "unit": "mL"}}'
    with_code = '{"numerator": {"value": 10, "code": "mg"}, "denominator": {"value": 2, "code": "mL"}}'
    zero_denom = '{"numerator": {"value": 5, "unit": "mg"}, "denominator": {"value": 0, "unit": "mL"}}'

    # ratioNumeratorValue
    r.assert_eq("num_val_valid", M, "SELECT ratioNumeratorValue(?)", 5.0, [simple])
    r.assert_eq("num_val_null", M, "SELECT ratioNumeratorValue(NULL)", None)
    r.assert_eq("num_val_empty", M, "SELECT ratioNumeratorValue('')", None)
    r.assert_eq("num_val_invalid", M, "SELECT ratioNumeratorValue('not json')", None)

    # ratioDenominatorValue
    r.assert_eq("denom_val_valid", M, "SELECT ratioDenominatorValue(?)", 1.0, [simple])
    r.assert_eq("denom_val_null", M, "SELECT ratioDenominatorValue(NULL)", None)

    # ratioValue
    r.assert_eq("ratio_val_valid", M, "SELECT ratioValue(?)", 5.0, [simple])
    r.assert_eq("ratio_val_fraction", M,
                "SELECT ratioValue('{\"numerator\":{\"value\":10,\"unit\":\"mg\"},\"denominator\":{\"value\":4,\"unit\":\"mL\"}}')",
                2.5)
    r.assert_eq("ratio_val_zero_num", M,
                "SELECT ratioValue('{\"numerator\":{\"value\":0,\"unit\":\"mg\"},\"denominator\":{\"value\":5,\"unit\":\"mL\"}}')",
                0.0)
    r.assert_eq("ratio_val_zero_denom", M, "SELECT ratioValue(?)", None, [zero_denom])
    r.assert_eq("ratio_val_null", M, "SELECT ratioValue(NULL)", None)
    r.assert_eq("ratio_val_missing_num", M,
                "SELECT ratioValue('{\"numerator\":{\"unit\":\"mg\"},\"denominator\":{\"value\":5,\"unit\":\"mL\"}}')", None)
    r.assert_eq("ratio_val_missing_denom", M,
                "SELECT ratioValue('{\"numerator\":{\"value\":5,\"unit\":\"mg\"},\"denominator\":{\"unit\":\"mL\"}}')", None)

    # ratioNumeratorUnit
    r.assert_eq("num_unit_valid", M, "SELECT ratioNumeratorUnit(?)", "mg", [simple])
    r.assert_eq("num_unit_code", M, "SELECT ratioNumeratorUnit(?)", "mg", [with_code])
    r.assert_eq("num_unit_null", M, "SELECT ratioNumeratorUnit(NULL)", None)
    r.assert_eq("num_unit_missing", M,
                "SELECT ratioNumeratorUnit('{\"numerator\":{\"value\":5},\"denominator\":{\"value\":1}}')", None)

    # ratioDenominatorUnit
    r.assert_eq("denom_unit_valid", M, "SELECT ratioDenominatorUnit(?)", "mL", [simple])
    r.assert_eq("denom_unit_code", M, "SELECT ratioDenominatorUnit(?)", "mL", [with_code])
    r.assert_eq("denom_unit_null", M, "SELECT ratioDenominatorUnit(NULL)", None)
    r.assert_eq("denom_unit_missing", M,
                "SELECT ratioDenominatorUnit('{\"numerator\":{\"value\":5},\"denominator\":{\"value\":1}}')", None)

    # Registration tests (all functions)
    ratio_10 = '{"numerator": {"value": 10, "unit": "mg"}, "denominator": {"value": 2, "unit": "mL"}}'
    r.assert_eq("reg_num_val", M, "SELECT ratioNumeratorValue(?)", 10.0, [ratio_10])
    r.assert_eq("reg_denom_val", M, "SELECT ratioDenominatorValue(?)", 2.0, [ratio_10])
    r.assert_eq("reg_ratio_val", M, "SELECT ratioValue(?)", 5.0, [ratio_10])
    r.assert_eq("reg_num_unit", M, "SELECT ratioNumeratorUnit(?)", "mg", [ratio_10])
    r.assert_eq("reg_denom_unit", M, "SELECT ratioDenominatorUnit(?)", "mL", [ratio_10])

    # Edge cases
    r.assert_eq("float_vals", M,
                "SELECT ratioValue('{\"numerator\":{\"value\":7.5,\"unit\":\"mg\"},\"denominator\":{\"value\":2.5,\"unit\":\"mL\"}}')",
                3.0)
    r.assert_eq("negative_vals", M,
                "SELECT ratioValue('{\"numerator\":{\"value\":-10,\"unit\":\"mg\"},\"denominator\":{\"value\":2,\"unit\":\"mL\"}}')",
                -5.0)
    r.assert_eq("large_vals", M,
                "SELECT ratioValue('{\"numerator\":{\"value\":1000000,\"unit\":\"mg\"},\"denominator\":{\"value\":1000,\"unit\":\"mL\"}}')",
                1000.0)
    r.assert_eq("empty_num", M,
                "SELECT ratioNumeratorValue('{\"numerator\":{},\"denominator\":{\"value\":1,\"unit\":\"mL\"}}')", None)
    r.assert_eq("empty_denom", M,
                "SELECT ratioDenominatorValue('{\"numerator\":{\"value\":5,\"unit\":\"mg\"},\"denominator\":{}}')", None)


def test_clinical(r: ConformanceRunner):
    """Clinical UDF tests (14 tests from test_clinical_udfs.py)."""
    M = "clinical"

    obs1 = json.dumps({"resourceType": "Observation", "id": "obs-1",
                        "effectiveDateTime": "2024-01-15T10:00:00Z",
                        "valueQuantity": {"value": 120, "unit": "mmHg"}})
    obs2 = json.dumps({"resourceType": "Observation", "id": "obs-2",
                        "effectiveDateTime": "2024-01-20T15:30:00Z",
                        "valueQuantity": {"value": 118, "unit": "mmHg"}})
    obs3 = json.dumps({"resourceType": "Observation", "id": "obs-3",
                        "effectiveDateTime": "2024-01-10T08:00:00Z",
                        "valueQuantity": {"value": 125, "unit": "mmHg"}})
    obs_no_date = json.dumps({"resourceType": "Observation", "id": "obs-nodate",
                               "valueQuantity": {"value": 118, "unit": "mmHg"}})

    # Build a JSON array string for the list of observations
    obs_array = json.dumps([json.loads(obs1), json.loads(obs2), json.loads(obs3)])
    obs_with_nulls = json.dumps([json.loads(obs1), json.loads(obs_no_date), json.loads(obs2)])

    # Latest tests
    r.assert_not_none("latest_single", M, f"SELECT Latest(?, 'effectiveDateTime')", [[obs1]])
    r.assert_eq("latest_null", M, "SELECT Latest(NULL, 'effectiveDateTime')", None)

    # Earliest tests
    r.assert_not_none("earliest_single", M, f"SELECT Earliest(?, 'effectiveDateTime')", [[obs1]])
    r.assert_eq("earliest_null", M, "SELECT Earliest(NULL, 'effectiveDateTime')", None)

    # Using JSON array strings directly for Latest/Earliest
    # The C++ function takes (VARCHAR[], VARCHAR) but we test what it accepts
    r.assert_not_none("latest_multi_via_array", M,
                      f"SELECT Latest(ARRAY['{obs1}', '{obs2}', '{obs3}'], 'effectiveDateTime')")
    r.assert_not_none("earliest_multi_via_array", M,
                      f"SELECT Earliest(ARRAY['{obs1}', '{obs2}', '{obs3}'], 'effectiveDateTime')")


def test_valueset(r: ConformanceRunner):
    """Valueset UDF tests (32 tests from test_valueset_udf.py)."""
    M = "valueset"

    resource_cc = json.dumps({
        "resourceType": "Observation",
        "code": {
            "coding": [
                {"system": "http://loinc.org", "code": "8480-6", "display": "Systolic blood pressure"},
                {"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic blood pressure"}
            ],
            "text": "Blood pressure"
        }
    })

    resource_direct = json.dumps({
        "resourceType": "Observation",
        "code": {
            "system": "http://loinc.org",
            "code": "8480-6",
            "display": "Systolic blood pressure"
        }
    })

    resource_no_code = json.dumps({"resourceType": "Patient", "name": [{"family": "Doe"}]})

    resource_empty_coding = json.dumps({
        "resourceType": "Observation",
        "code": {"coding": []}
    })

    resource_nested = json.dumps({
        "resourceType": "Observation",
        "valueCodeableConcept": {
            "coding": [{"system": "http://snomed.info/sct", "code": "123456789"}]
        }
    })

    # extractCodes - C++ returns LIST(VARCHAR), each element is JSON {"system":..., "code":...}
    r.assert_not_none("codes_cc", M, "SELECT extractCodes(?, 'code')", [resource_cc])
    r.assert_not_none("codes_direct", M, "SELECT extractCodes(?, 'code')", [resource_direct])
    r.assert_not_none("codes_nested", M, "SELECT extractCodes(?, 'valueCodeableConcept')", [resource_nested])

    # extractFirstCode
    r.assert_not_none("first_code_cc", M, "SELECT extractFirstCode(?, 'code')", [resource_cc])
    r.assert_not_none("first_code_direct", M, "SELECT extractFirstCode(?, 'code')", [resource_direct])
    r.assert_eq("first_code_no_code", M, "SELECT extractFirstCode(?, 'code')", None, [resource_no_code])
    r.assert_eq("first_code_null", M, "SELECT extractFirstCode(NULL, 'code')", None)

    # extractFirstCodeSystem
    r.assert_eq("first_system_cc", M, "SELECT extractFirstCodeSystem(?, 'code')", "http://loinc.org", [resource_cc])
    r.assert_eq("first_system_no_code", M, "SELECT extractFirstCodeSystem(?, 'code')", None, [resource_no_code])
    r.assert_eq("first_system_null", M, "SELECT extractFirstCodeSystem(NULL, 'code')", None)

    # extractFirstCodeValue
    r.assert_eq("first_value_cc", M, "SELECT extractFirstCodeValue(?, 'code')", "8480-6", [resource_cc])
    r.assert_eq("first_value_no_code", M, "SELECT extractFirstCodeValue(?, 'code')", None, [resource_no_code])
    r.assert_eq("first_value_null", M, "SELECT extractFirstCodeValue(NULL, 'code')", None)

    # Null handling — extractCodes returns empty list (not NULL) for NULL input in C++
    r.assert_eq("first_code_null_resource", M, "SELECT extractFirstCode(NULL, 'code')", None)
    r.assert_eq("first_system_null_resource", M, "SELECT extractFirstCodeSystem(NULL, 'code')", None)
    r.assert_eq("first_value_null_resource", M, "SELECT extractFirstCodeValue(NULL, 'code')", None)

    # resolveProfileUrl
    r.assert_eq("resolve_us_core_patient", M,
                "SELECT resolveProfileUrl('http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient')",
                "Patient")
    r.assert_eq("resolve_null", M, "SELECT resolveProfileUrl(NULL)", None)

    # Edge: missing system
    no_system = json.dumps({"code": {"coding": [{"code": "8480-6"}]}})
    r.assert_not_none("codes_missing_system", M, "SELECT extractCodes(?, 'code')", [no_system])

    # Deep nested path
    deep = json.dumps({
        "component": {"item": {"code": {"coding": [{"system": "http://loinc.org", "code": "test-code"}]}}}
    })
    r.assert_not_none("codes_deep_nested", M, "SELECT extractCodes(?, 'component.item.code')", [deep])


def test_list(r: ConformanceRunner):
    """List UDF tests (37 tests from test_list_udfs.py).

    Note: First, Last, Skip, Take, Distinct are SQL macros from Python.
    SingletonFrom, ElementAt, jsonConcat are C++ UDFs.
    The macro tests only apply if macros are loaded.
    """
    M = "list"

    # SingletonFrom (C++ UDF — takes LIST(VARCHAR))
    r.assert_eq("singleton_single", M, "SELECT SingletonFrom(['1'])", "1")
    r.assert_eq("singleton_empty", M, "SELECT SingletonFrom([]::VARCHAR[])", None)
    r.assert_eq("singleton_multiple", M, "SELECT SingletonFrom(['1', '2'])", None)
    r.assert_eq("singleton_null", M, "SELECT SingletonFrom(NULL)", None)
    r.assert_eq("singleton_string", M, "SELECT SingletonFrom(['hello'])", "hello")

    # ElementAt (C++ UDF — takes LIST(VARCHAR), BIGINT)
    r.assert_eq("elementat_first", M, "SELECT ElementAt(['a', 'b', 'c'], 0)", "a")
    r.assert_eq("elementat_second", M, "SELECT ElementAt(['a', 'b', 'c'], 1)", "b")
    r.assert_eq("elementat_last", M, "SELECT ElementAt(['a', 'b', 'c'], 2)", "c")
    r.assert_eq("elementat_null_list", M, "SELECT ElementAt(NULL, 0)", None)
    r.assert_eq("elementat_out_of_range", M, "SELECT ElementAt(['a', 'b'], 5)", None)

    # jsonConcat (C++ UDF — takes two VARCHAR, returns LIST(VARCHAR))
    # When both are NULL, returns NULL
    r.assert_eq("jsonconcat_both_null", M, "SELECT jsonConcat(NULL, NULL)", None)
    # When one is valid, returns list containing that element
    r.assert_not_none("jsonconcat_valid", M, "SELECT jsonConcat('[1, 2]', '[3, 4]')")


def test_macros(r: ConformanceRunner):
    """Macro tests (65 tests from test_macros_tier1.py).

    These test SQL macros loaded from duckdb_cql_py.macros.
    They should work identically regardless of whether the C++ extension is loaded.
    """
    M = "macros"

    # Math macros
    r.assert_eq("abs_neg", M, "SELECT Abs(-5)", 5)
    r.assert_eq("abs_pos", M, "SELECT Abs(5)", 5)
    r.assert_eq("abs_zero", M, "SELECT Abs(0)", 0)
    r.assert_eq("abs_null", M, "SELECT Abs(NULL)", None)
    r.assert_eq("ceiling", M, "SELECT Ceiling(4.3)", 5)
    r.assert_eq("ceiling_neg", M, "SELECT Ceiling(-4.3)", -4)
    r.assert_eq("floor", M, "SELECT Floor(4.7)", 4)
    r.assert_eq("floor_neg", M, "SELECT Floor(-4.7)", -5)
    r.assert_eq("round_no_prec", M, "SELECT Round(3.14159)", 3.0, approx=True)
    r.assert_eq("round_with_prec", M, "SELECT RoundTo(3.14159, 2)", 3.14, approx=True)
    r.assert_eq("round_null", M, "SELECT Round(NULL)", None)
    r.assert_eq("sqrt", M, "SELECT Sqrt(16)", 4.0)
    r.assert_eq("power", M, "SELECT Power(2, 3)", 8.0)
    r.assert_eq("mod", M, "SELECT Mod(17, 5)", 2)
    r.assert_eq("div", M, "SELECT Div(17, 5)", 3)

    # String macros
    r.assert_eq("length", M, "SELECT Length('hello')", 5)
    r.assert_eq("length_null", M, "SELECT Length(NULL)", None)
    r.assert_eq("upper", M, "SELECT Upper('hello')", "HELLO")
    r.assert_eq("lower", M, "SELECT Lower('HELLO')", "hello")
    r.assert_eq("concat", M, "SELECT Concat('hello', ' world')", "hello world")
    r.assert_eq("concat_null", M, "SELECT Concat(NULL, 'test')", None)
    r.assert_eq("concat_null2", M, "SELECT Concat('test', NULL)", None)
    r.assert_eq("substring", M, "SELECT Substring('hello', 1)", "ello")
    r.assert_eq("substring_len", M, "SELECT SubstringLen('hello', 1, 3)", "ell")
    r.assert_eq("substring_zero", M, "SELECT Substring('hello', 0)", "hello")
    r.assert_eq("substring_null", M, "SELECT Substring(NULL, 0)", None)
    r.assert_eq("indexof_found", M, "SELECT IndexOf('hello', 'll')", 2)
    r.assert_eq("indexof_not_found", M, "SELECT IndexOf('hello', 'xyz')", -1)
    r.assert_eq("indexof_start", M, "SELECT IndexOf('hello', 'h')", 0)
    r.assert_eq("indexof_null", M, "SELECT IndexOf(NULL, 'test')", None)
    r.assert_eq("startswith", M, "SELECT StartsWith('hello world', 'hello')", True)
    r.assert_eq("endswith", M, "SELECT EndsWith('hello world', 'world')", True)
    r.assert_eq("contains", M, "SELECT Contains('hello world', 'llo')", True)
    r.assert_eq("replace", M, "SELECT Replace('hello', 'l', 'L')", "heLLo")
    r.assert_eq("trim", M, "SELECT Trim('  hello  ')", "hello")
    r.assert_eq("ltrim", M, "SELECT LTrim('  hello  ')", "hello  ")
    r.assert_eq("rtrim", M, "SELECT RTrim('  hello  ')", "  hello")

    # Logical macros
    r.assert_eq("xor_tf", M, "SELECT Xor(true, false)", True)
    r.assert_eq("xor_tt", M, "SELECT Xor(true, true)", False)
    r.assert_eq("xor_ff", M, "SELECT Xor(false, false)", False)
    r.assert_eq("xor_ft", M, "SELECT Xor(false, true)", True)
    r.assert_eq("implies_ft", M, "SELECT Implies(false, true)", True)
    r.assert_eq("implies_ff", M, "SELECT Implies(false, false)", True)
    r.assert_eq("implies_tt", M, "SELECT Implies(true, true)", True)
    r.assert_eq("implies_tf", M, "SELECT Implies(true, false)", False)
    r.assert_eq("coalesce_first", M, "SELECT Coalesce('hello', 'world')", "hello")
    r.assert_eq("coalesce_null", M, "SELECT Coalesce(NULL, 'world')", "world")

    # DateTime macros
    r.assert_eq("year_extract", M, "SELECT Year(DATE '2024-06-15')", 2024)
    r.assert_eq("month_extract", M, "SELECT Month(DATE '2024-06-15')", 6)
    r.assert_eq("day_extract", M, "SELECT Day(DATE '2024-06-15')", 15)
    r.assert_eq("days_between_macro", M, "SELECT DaysBetween(DATE '2024-01-01', DATE '2024-01-10')", 9)
    r.assert_eq("months_between_macro", M, "SELECT MonthsBetween(DATE '2024-01-15', DATE '2024-03-15')", 2)
    r.assert_eq("years_between_macro", M, "SELECT YearsBetween(DATE '2020-01-01', DATE '2024-01-01')", 4)
    r.assert_not_none("make_date", M, "SELECT MakeDate(2024, 6, 15)")

    # Conversion macros
    r.assert_eq("to_string", M, "SELECT ToString(42)", "42")
    r.assert_eq("to_integer", M, "SELECT ToInteger('42')", 42)
    r.assert_eq("to_boolean", M, "SELECT ToBoolean('true')", True)
    r.assert_not_none("to_date", M, "SELECT ToDate('2024-06-15')")

    # Aggregate macros
    r.assert_eq("count", M, "SELECT Count(x) FROM (SELECT unnest([1,2,3,4,5]) AS x)", 5)
    r.assert_eq("sum", M, "SELECT Sum(x) FROM (SELECT unnest([1,2,3,4,5]) AS x)", 15)
    r.assert_eq("min", M, "SELECT Min(x) FROM (SELECT unnest([3,1,4,1,5]) AS x)", 1)
    r.assert_eq("max", M, "SELECT Max(x) FROM (SELECT unnest([3,1,4,1,5]) AS x)", 5)
    r.assert_eq("avg", M, "SELECT Avg(x) FROM (SELECT unnest([1,2,3,4,5]) AS x)", 3.0)
    r.assert_eq("median_agg", M, "SELECT Median(x) FROM (SELECT unnest([1,2,3,4,5]) AS x)", 3.0)
    r.assert_eq("stddev", M, "SELECT StdDev(x) FROM (SELECT unnest([1,2,3,4,5]) AS x)",
                1.5811388300841898, approx=True, tol=0.001)

    # List macros
    r.assert_eq("first_list", M, "SELECT First([1, 2, 3])", 1)
    r.assert_eq("first_empty", M, "SELECT First([])", None)
    r.assert_eq("last_list", M, "SELECT Last([1, 2, 3])", 3)
    r.assert_eq("last_empty", M, "SELECT Last([])", None)


def test_aggregate(r: ConformanceRunner):
    """Aggregate UDF tests — statisticalMedian, Mode, StdDev, Variance."""
    M = "aggregate"

    # These C++ UDFs take LIST(DOUBLE)
    r.assert_eq("median_odd", M, "SELECT statisticalMedian([1.0, 2.0, 3.0, 4.0, 5.0])", 3.0)
    r.assert_eq("median_even", M, "SELECT statisticalMedian([1.0, 2.0, 3.0, 4.0])", 2.5)
    r.assert_eq("median_single", M, "SELECT statisticalMedian([42.0])", 42.0)
    r.assert_eq("median_null", M, "SELECT statisticalMedian(NULL)", None)

    r.assert_eq("mode_simple", M, "SELECT statisticalMode([1.0, 2.0, 2.0, 3.0])", 2.0)
    r.assert_eq("mode_null", M, "SELECT statisticalMode(NULL)", None)

    r.assert_eq("stddev_basic", M, "SELECT statisticalStdDev([1.0, 2.0, 3.0, 4.0, 5.0])",
                1.5811388300841898, approx=True, tol=0.01)
    r.assert_eq("stddev_null", M, "SELECT statisticalStdDev(NULL)", None)

    r.assert_eq("variance_basic", M, "SELECT statisticalVariance([1.0, 2.0, 3.0, 4.0, 5.0])",
                2.5, approx=True, tol=0.01)
    r.assert_eq("variance_null", M, "SELECT statisticalVariance(NULL)", None)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_MODULES = {
    "age": test_age,
    "datetime": test_datetime,
    "interval": test_interval,
    "quantity": test_quantity,
    "ratio": test_ratio,
    "clinical": test_clinical,
    "valueset": test_valueset,
    "list": test_list,
    "macros": test_macros,
    "aggregate": test_aggregate,
}


def setup_connection(args) -> duckdb.DuckDBPyConnection:
    """Set up a DuckDB connection with either C++ extension or Python UDFs."""
    con = duckdb.connect(":memory:", config={"allow_unsigned_extensions": "true"})

    if args.python:
        print("Using Python UDFs as reference implementation...")
        from duckdb_cql_py import register
        register(con, include_fhirpath=False)
    else:
        ext_path = args.extension
        if not ext_path:
            # Try to find extension automatically
            candidates = [
                "build/release/extension/cql/cql.duckdb_extension",
                "../duckdb-cql-cpp/build/release/extension/cql/cql.duckdb_extension",
            ]
            for c in candidates:
                if os.path.exists(c):
                    ext_path = c
                    break

        if not ext_path or not os.path.exists(ext_path):
            print(f"ERROR: Extension not found at '{ext_path}'.")
            print("Build with: cd duckdb-cql-cpp && make release")
            print("Or use --python flag to test Python UDFs.")
            sys.exit(1)

        print(f"Loading C++ extension: {ext_path}")
        con.execute(f"LOAD '{os.path.abspath(ext_path)}'")

        # Load SQL macros (pure SQL — needed for both Python and C++)
        try:
            from duckdb_cql_py.macros import register_all_macros
            register_all_macros(con)
            print("SQL macros loaded from duckdb_cql_py.macros")
        except ImportError:
            print("WARNING: duckdb_cql_py not installed, SQL macros unavailable.")
            print("Macro tests will fail. Install with: pip install -e duckdb-cql-py")

    return con


def main():
    parser = argparse.ArgumentParser(description="CQL C++ Extension Conformance Test Runner")
    parser.add_argument("--extension", "-e", help="Path to cql.duckdb_extension")
    parser.add_argument("--python", "-p", action="store_true", help="Test Python UDFs instead (reference)")
    parser.add_argument("--module", "-m", help="Run only a specific module (age, datetime, interval, ...)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed failure output")
    args = parser.parse_args()

    con = setup_connection(args)
    runner = ConformanceRunner(con, verbose=args.verbose)

    modules_to_run = ALL_MODULES
    if args.module:
        if args.module not in ALL_MODULES:
            print(f"Unknown module: {args.module}")
            print(f"Available: {', '.join(ALL_MODULES.keys())}")
            sys.exit(1)
        modules_to_run = {args.module: ALL_MODULES[args.module]}

    for name, test_fn in modules_to_run.items():
        print(f"Running {name} tests...")
        try:
            test_fn(runner)
        except Exception as e:
            print(f"  ERROR in {name}: {e}")
            traceback.print_exc()

    stats = runner.report()
    con.close()

    # Exit with non-zero if failures
    sys.exit(0 if stats["fail"] == 0 else 1)


if __name__ == "__main__":
    main()
