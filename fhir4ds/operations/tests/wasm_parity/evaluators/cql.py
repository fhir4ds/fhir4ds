"""Tier A, CQL corpus: 2,037 official tests on both surfaces (plan section 4.4).

Each test is translated three times (desktop connection, browser connection,
``connection=None``); the SQL texts must be identical. The identical SQL then
runs on both surfaces and the official comparator (``run_cql.assess_test``)
decides each verdict. ``TRANSLATE_ERROR`` is engine-independent and only
reported.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from ..reference_bundle import REPO_ROOT, EnvironmentInputMissing
from . import (
    BOTH_FAIL,
    BROWSER_ONLY_PASS,
    ENGINE_DIFF,
    GREEN,
    PARITY_GAP,
    TRANSLATE_DIFF,
    TRANSLATE_ERROR,
    CaseOutcome,
    SuiteResult,
    suspects_for,
)

CORPUS_DIR = REPO_ROOT / "fhir4ds" / "cql" / "tests" / "official" / "cql-tests" / "tests" / "cql"
SUITE = "cql"


def runner():
    """``conformance.scripts.run_cql`` (namespace package at the repo root)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from conformance.scripts import run_cql

    return run_cql


def run(desktop, browser, contract, *, corpus_dir: Path | None = None) -> SuiteResult:
    """Evaluate the CQL corpus on both surfaces."""
    run_cql = runner()
    directory = Path(corpus_dir) if corpus_dir is not None else Path(run_cql.CQL_TESTS_DIR)
    if not directory.exists():
        raise EnvironmentInputMissing(
            f"CQL corpus not checked out at {directory} (pinned gitlink; clone "
            "cqframework/cql-tests there)"
        )
    for con in (desktop, browser):
        con.execute("CREATE TABLE IF NOT EXISTS resources (resource VARCHAR, patient_id VARCHAR)")

    started = time.perf_counter()
    tests = [test for test in run_cql.iter_corpus_tests(directory) if not test.superseded]
    gated = sum(1 for _ in run_cql.iter_corpus_tests(directory)) - len(tests)
    if hasattr(browser, "execute_many"):
        # A remote surface (the real browser engine) evaluates in batches: one round trip
        # per chunk instead of one per test.
        outcomes = _run_batched(run_cql, tests, desktop, browser, contract)
    else:
        outcomes = [_outcome(run_cql, test, desktop, browser, contract) for test in tests]
    return SuiteResult(SUITE, tuple(outcomes), gated, time.perf_counter() - started)


def _run_batched(run_cql, tests, desktop, browser, contract) -> list[CaseOutcome]:
    translated: list[tuple[int, object, str]] = []
    outcomes: dict[int, CaseOutcome] = {}
    for index, test in enumerate(tests):
        sql, pre = _translate(run_cql, test, desktop, browser)
        if pre is None:
            translated.append((index, test, sql))
        else:
            outcomes[index] = pre
    sqls = [sql for _, _, sql in translated]
    desktop_execs = [run_cql.execute_test_text(desktop, sql) for sql in sqls]
    browser_execs = browser.execute_many(sqls)
    if len(browser_execs) != len(sqls):
        raise RuntimeError(
            f"browser returned {len(browser_execs)} executions for {len(sqls)} statements"
        )
    for (index, test, sql), exec_d, exec_b in zip(
        translated, desktop_execs, browser_execs, strict=False
    ):
        outcomes[index] = _judge(run_cql, test, sql, exec_d, exec_b, contract)
    return [outcomes[i] for i in range(len(tests))]


def _short(text: object, limit: int = 200) -> str:
    return " ".join(str(text).split())[:limit]


def _translate(run_cql, test, desktop, browser):
    """``(sql, None)`` or ``(None, outcome)`` when translation itself is the finding."""
    case_id = f"{test.filename}::{test.name}"
    expr = run_cql.test_expression(test.test_elem)
    if expr is None:
        return None, CaseOutcome(
            case_id, BOTH_FAIL, "No expression found", "not run", "corpus test has no expression"
        )
    cql_expr = expr[0]
    try:
        sql = run_cql.translate_test_sql(cql_expr, desktop)
        variants = {
            "browser connection": run_cql.translate_test_sql(cql_expr, browser),
            "connection=None": run_cql.translate_test_sql(cql_expr, None),
        }
    except Exception as exc:  # noqa: BLE001 - translation errors are the finding
        return None, CaseOutcome(
            case_id, TRANSLATE_ERROR, f"translate: {_short(exc)}", "-", "translation-layer"
        )
    differing = [label for label, text in variants.items() if text != sql]
    if differing:
        return None, CaseOutcome(
            case_id,
            TRANSLATE_DIFF,
            "translated",
            "translated",
            f"SQL differs when translated with {differing}",
        )
    return sql, None


def _outcome(run_cql, test, desktop, browser, contract) -> CaseOutcome:
    sql, pre = _translate(run_cql, test, desktop, browser)
    if pre is not None:
        return pre
    exec_d = run_cql.execute_test_select(desktop, sql, with_type=True)
    exec_b = run_cql.execute_test_select(browser, sql, with_type=True)
    return _judge(run_cql, test, sql, exec_d, exec_b, contract)


def _judge(run_cql, test, sql, exec_d, exec_b, contract) -> CaseOutcome:
    case_id = f"{test.filename}::{test.name}"
    passed_d, reason_d = run_cql.assess_test(test.test_elem, exec_d)
    passed_b, reason_b = run_cql.assess_test(test.test_elem, exec_b)
    verdict_d = "pass" if passed_d else f"fail: {_short(reason_d)}"
    verdict_b = "pass" if passed_b else f"fail: {_short(reason_b)}"

    if passed_d and passed_b:
        # Values moved as text compare as text (the batched path); raw objects compare raw.
        if exec_d.text is not None and exec_b.text is not None:
            same = exec_d.text == exec_b.text
        else:
            same = exec_d.value == exec_b.value
        if same and exec_d.value_type == exec_b.value_type:
            outcome, detail = GREEN, ""
        else:
            outcome = ENGINE_DIFF
            if same:
                detail = f"type: desktop={exec_d.value_type} browser={exec_b.value_type}"
            else:
                shown_d = exec_d.text if exec_d.text is not None else _short(exec_d.value, 120)
                shown_b = exec_b.text if exec_b.text is not None else _short(exec_b.value, 120)
                detail = f"value: desktop={shown_d!r} browser={shown_b!r}"
    elif passed_d:
        outcome, detail = PARITY_GAP, verdict_b
    elif passed_b:
        outcome, detail = BROWSER_ONLY_PASS, verdict_d
    else:
        outcome, detail = BOTH_FAIL, verdict_d

    suspects, missing = suspects_for(sql, contract)
    return CaseOutcome(case_id, outcome, verdict_d, verdict_b, detail, suspects, missing)
