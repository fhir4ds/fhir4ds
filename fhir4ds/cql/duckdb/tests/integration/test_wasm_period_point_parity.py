"""One-sided FHIR Periods and Period-as-point: the browser engine answers like desktop.

Found by WASM parity Tier C on us-core-2025 (WP-5): CMS645 (patient ``eeea0041``) and CMS996
(patient ``f6c7dbc1``) disagreed with desktop ONLY in a browser. A browser has just the
bundled C++; for these names desktop uses the Python UDFs
(``_PYTHON_PREFERRED_CPP_CONFLICTS``), and the two had drifted apart:

* ``collapse_intervals`` — the Python authority parses a Period with no ``start`` as an
  UNKNOWN start (open null low bound) and never lets a merge narrow an unbounded end; the
  bundled C++ read the missing start as "unbounded" and dropped an ongoing period's open end
  when it merged.
* the point predicates (``cqlBefore`` and siblings) — the Python authority answers NULL for
  an interval-shaped operand; the bundled C++ substituted the interval's low bound and
  answered a definite Boolean.

Three legs: the Python fallback, the desktop registration, and the no-Python surface (what a
browser actually runs). The expected values are the Python authority's.
"""

from __future__ import annotations

import json

import duckdb
import pytest

from fhir4ds.cql.duckdb import register
from fhir4ds.cql.duckdb.extension import _register_python_supplements

from .wasm_runtime_helpers import no_python_connection

END_ONLY = '{"end": "2026-01-05"}'
START_ONLY = '{"start": "2026-01-03"}'
JANUARY = '{"start": "2026-01-01", "end": "2026-01-05"}'
FEBRUARY = '{"start": "2026-02-01", "end": "2026-02-10"}'

UNKNOWN_START = {"low": None, "high": "2026-01-05", "lowClosed": False, "highClosed": True}
FEBRUARY_INTERVAL = {"low": "2026-02-01", "high": "2026-02-10", "lowClosed": True, "highClosed": True}

COLLAPSE_CASES: dict[str, tuple[str, list[dict]]] = {
    "an unknown start swallows an interval that ends with it": (
        f"[{END_ONLY},{JANUARY}]",
        [UNKNOWN_START],
    ),
    "an unknown start stays apart from a later interval": (
        f"[{END_ONLY},{FEBRUARY}]",
        [UNKNOWN_START, FEBRUARY_INTERVAL],
    ),
    "an ongoing period absorbs a later interval and stays unbounded": (
        f"[{START_ONLY},{FEBRUARY}]",
        [{"low": "2026-01-03", "high": None, "lowClosed": True, "highClosed": True}],
    ),
    "an ongoing period keeps the earliest start": (
        f"[{START_ONLY},{JANUARY}]",
        [{"low": "2026-01-01", "high": None, "lowClosed": True, "highClosed": True}],
    ),
}

POINT_PREDICATES = ("cqlBefore", "cqlAfter", "cqlSameOrBefore", "cqlSameOrAfter")


def _python_only_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    _register_python_supplements(con, cpp_loaded=False, include_fhirpath=True)
    return con


def _cpp_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(config={"allow_unsigned_extensions": True})
    register(con, include_fhirpath=True)
    return con


def _legs(*, python_fallback: bool = True):
    """Yield (label, connection) for the surfaces; closes them when the loop ends.

    `python_fallback=False` is for helpers that exist only in the C++ extension.
    """
    desktop = _cpp_connection()
    python_only = _python_only_connection() if python_fallback else None
    try:
        with no_python_connection() as no_python:
            if python_only is not None:
                yield ("python fallback", python_only)
            yield ("desktop", desktop)
            yield ("no-Python", no_python)
    finally:
        desktop.close()
        if python_only is not None:
            python_only.close()


def _text(con: duckdb.DuckDBPyConnection, expression: str):
    return con.execute(f"SELECT CAST(({expression}) AS VARCHAR)").fetchone()[0]


@pytest.mark.parametrize("label", sorted(COLLAPSE_CASES))
@pytest.mark.parametrize("with_per", [False, True], ids=["plain", "per-day"])
def test_collapse_one_sided_periods_match_the_python_authority(label: str, with_per: bool) -> None:
    interval_list, expected = COLLAPSE_CASES[label]
    per = ", '{\"value\": 1, \"unit\": \"day\"}'" if with_per else ""
    expression = f"collapse_intervals{'_per' if with_per else ''}('{interval_list}'{per})"
    for leg, con in _legs():
        raw = _text(con, expression)
        assert raw is not None, f"{leg}: {label}"
        assert json.loads(raw) == expected, f"{leg}: {label}"


@pytest.mark.parametrize("predicate", POINT_PREDICATES)
@pytest.mark.parametrize("period_first", [True, False], ids=["period-first", "period-second"])
def test_point_predicates_are_uncertain_for_a_period_operand(predicate: str, period_first: bool) -> None:
    operands = (JANUARY, "'2026-02-01'") if period_first else ("'2025-01-01'", JANUARY)
    expression = f"{predicate}('{operands[0]}', {operands[1]})"
    for leg, con in _legs():
        assert _text(con, expression) is None, f"{leg}: {predicate} must not compare a period as a point"


def test_list_element_temporal_equality_is_uncertain_for_a_period_element() -> None:
    equal = f"cqlDateTimeEqualListElement('{JANUARY}', '2026-01-01')"
    equivalent = f"cqlDateTimeEquivalentListElement('{JANUARY}', '2026-01-01')"
    for leg, con in _legs():
        assert _text(con, equal) is None, f"{leg}: equality of a period element is uncertain"
        assert _text(con, equivalent) == "false", f"{leg}: equivalence is two-valued and false"


def test_precision_qualified_helpers_keep_the_low_bound_of_an_interval_operand() -> None:
    """These three are native on desktop too, so desktop and browser already agree."""
    cases = {
        "cqlSameAsP": f"cqlSameAsP('{JANUARY}', '2026-01-01', 'day')",
        "cqlSameOrBeforeP": f"cqlSameOrBeforeP('{JANUARY}', '2026-02-01', 'day')",
        "cqlSameOrAfterP": f"cqlSameOrAfterP('{JANUARY}', '2025-01-01', 'day')",
    }
    for leg, con in _legs(python_fallback=False):
        for name, expression in cases.items():
            assert _text(con, expression) == "true", f"{leg}: {name}"


def test_interval_start_and_end_of_one_sided_periods_are_unchanged() -> None:
    """`intervalStart`/`intervalEnd` are native on desktop as well: a missing side resolves to
    the point-type extreme there. Only the collapse list parser applies the unknown-start rule."""
    cases = {
        "intervalStart": (f"intervalStart('{END_ONLY}')", "0001-01-01"),
        "intervalEnd": (f"intervalEnd('{START_ONLY}')", "9999-12-31"),
    }
    for leg, con in _legs(python_fallback=False):
        for name, (expression, expected) in cases.items():
            assert _text(con, expression) == expected, f"{leg}: {name}"
