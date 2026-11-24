"""Regression tests for the official CQL conformance runner's comparison logic.

FHIR4-33: ``conformance/scripts/run_cql.py::compare_results`` treated ``False``
and ``None`` as EQUAL ("both falsy"), so a fixture asserting ``false`` passed
when the engine produced CQL null, and a fixture asserting ``null`` passed when
the engine produced ``false``. That blanket rule was inherited verbatim from
``benchmarks/runner/comparison.py``, where it is correct: that comparer scores
per-patient *population* columns, and CQL Boolean define population boundaries
presence-encode null as false by design. The official-fixture harness scores the
bare expression, so the leniency only hid real divergences - the AMUX-171 Time
millisecond class among them, where an EXTERNAL runner had to be the referee.

The comparison is now strict whenever either side is Boolean-typed. The single
remaining Boolean allowance is structural: a fixture with NO ``<output>``
element makes no value assertion at all, and that shape cannot express "false".
"""

from __future__ import annotations

import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RUNNER_PATH = REPO_ROOT / "conformance" / "scripts" / "run_cql.py"


def _load_runner():
    """Import conformance/scripts/run_cql.py by path (it is not a package)."""
    # Appended, not inserted: the runner imports its sibling conformance_log,
    # and appending avoids shadowing anything else the test session imports.
    scripts_dir = str(RUNNER_PATH.parent)
    if scripts_dir not in sys.path:
        sys.path.append(scripts_dir)
    spec = importlib.util.spec_from_file_location("fhir4ds_conformance_run_cql", RUNNER_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {RUNNER_PATH}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


run_cql = _load_runner()


# ---------------------------------------------------------------------------
# compare_results: both strict directions (FHIR4-33 requirement a)
# ---------------------------------------------------------------------------


def test_expected_false_rejects_actual_null():
    """A fixture expecting `false` must fail when the engine answers null."""
    assert run_cql.compare_results(None, False) is False


def test_expected_null_rejects_actual_false():
    """A fixture expecting `null` must fail when the engine answers false."""
    assert run_cql.compare_results(False, None) is False


def test_boolean_equality_still_matches():
    assert run_cql.compare_results(True, True) is True
    assert run_cql.compare_results(False, False) is True


def test_expected_true_rejects_actual_null():
    assert run_cql.compare_results(None, True) is False


def test_both_null_matches():
    assert run_cql.compare_results(None, None) is True


def test_null_inside_a_collection_stays_strict():
    """Element comparisons inherit the strict rule (positional list compare)."""
    assert run_cql.compare_results([None], [False]) is False
    assert run_cql.compare_results([False], [None]) is False


# ---------------------------------------------------------------------------
# The narrow allowance: absent <output> only (FHIR4-33 requirement b)
# ---------------------------------------------------------------------------


def test_unasserted_expectation_allows_a_falsy_result():
    """No <output> element cannot express `false`; a falsy result is accepted."""
    assert run_cql.compare_results(False, None, expected_asserted=False) is True


def test_unasserted_expectation_still_rejects_a_true_result():
    """The allowance is falsy-only: `true` was never expressible as "no output"."""
    assert run_cql.compare_results(True, None, expected_asserted=False) is False


def test_asserted_null_stays_strict():
    """The default is strict: an explicit <output>null</output> rejects false."""
    assert run_cql.compare_results(False, None, expected_asserted=True) is False


def test_structural_non_boolean_leniency_is_unchanged():
    """An empty collection still compares equal to an empty expectation."""
    assert run_cql.compare_results([], None) is True
    assert run_cql.compare_results(None, None) is True


# ---------------------------------------------------------------------------
# run_test plumbing: fixture shape -> expected_asserted -> comparison
# ---------------------------------------------------------------------------

_FALSE_SQL = "FALSE"
_NULL_SQL = "NULL"


class _StubDefinition:
    """Stands in for a translated definition (only to_sql() is used)."""

    def __init__(self, sql: str) -> None:
        self._sql = sql

    def to_sql(self) -> str:
        return self._sql


def _test_element(output: str | None) -> ET.Element:
    """Build a <test> element shaped like the official corpus (namespaced)."""
    inner = "<expression>1 = 1</expression>"
    if output is not None:
        inner += f"<output>{output}</output>"
    return ET.fromstring(
        f"<test xmlns='{run_cql.NS['ns']}' name='Stub'>{inner}</test>"
    )


def _run_stub_test(monkeypatch, sql: str, output: str | None):
    import duckdb

    monkeypatch.setattr(
        run_cql,
        "translate_cql",
        lambda library_text, connection=None: {"TestResult": _StubDefinition(sql)},
    )
    conn = duckdb.connect(":memory:")
    try:
        return run_cql.run_test(conn, _test_element(output))
    finally:
        conn.close()


def test_run_test_fails_when_a_false_expectation_gets_null(monkeypatch):
    passed, reason = _run_stub_test(monkeypatch, _NULL_SQL, "false")
    assert passed is False
    assert "null result is not false" in reason


def test_run_test_fails_when_a_null_expectation_gets_false(monkeypatch):
    passed, reason = _run_stub_test(monkeypatch, _FALSE_SQL, "null")
    assert passed is False
    assert "false result is not null" in reason


def test_run_test_passes_null_expectation_with_null_result(monkeypatch):
    passed, reason = _run_stub_test(monkeypatch, _NULL_SQL, "null")
    assert passed is True, reason


def test_run_test_uses_the_allowance_for_a_fixture_with_no_output(monkeypatch):
    """The documented structural case: no <output> element, falsy result."""
    passed, reason = _run_stub_test(monkeypatch, _FALSE_SQL, None)
    assert passed is True, reason


def test_run_test_still_rejects_true_when_there_is_no_output(monkeypatch):
    passed, _reason = _run_stub_test(monkeypatch, "TRUE", None)
    assert passed is False
