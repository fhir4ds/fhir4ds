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
    outcomes: list[CaseOutcome] = []
    gated = 0
    for test in run_cql.iter_corpus_tests(directory):
        if test.superseded:
            gated += 1
            continue
        outcomes.append(_outcome(run_cql, test, desktop, browser, contract))
    return SuiteResult(SUITE, tuple(outcomes), gated, time.perf_counter() - started)


def _short(text: object, limit: int = 200) -> str:
    return " ".join(str(text).split())[:limit]


def _outcome(run_cql, test, desktop, browser, contract) -> CaseOutcome:
    case_id = f"{test.filename}::{test.name}"
    expr = run_cql.test_expression(test.test_elem)
    if expr is None:
        return CaseOutcome(
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
        return CaseOutcome(
            case_id, TRANSLATE_ERROR, f"translate: {_short(exc)}", "-", "translation-layer"
        )
    differing = [label for label, text in variants.items() if text != sql]
    if differing:
        return CaseOutcome(
            case_id,
            TRANSLATE_DIFF,
            "translated",
            "translated",
            f"SQL differs when translated with {differing}",
        )

    exec_d = run_cql.execute_test_select(desktop, sql, with_type=True)
    exec_b = run_cql.execute_test_select(browser, sql, with_type=True)
    passed_d, reason_d = run_cql.assess_test(test.test_elem, exec_d)
    passed_b, reason_b = run_cql.assess_test(test.test_elem, exec_b)
    verdict_d = "pass" if passed_d else f"fail: {_short(reason_d)}"
    verdict_b = "pass" if passed_b else f"fail: {_short(reason_b)}"

    if passed_d and passed_b:
        if exec_d.value == exec_b.value and exec_d.value_type == exec_b.value_type:
            outcome, detail = GREEN, ""
        else:
            outcome = ENGINE_DIFF
            if exec_d.value == exec_b.value:
                detail = f"type: desktop={exec_d.value_type} browser={exec_b.value_type}"
            else:
                detail = f"value: desktop={_short(exec_d.value, 120)!r} browser={_short(exec_b.value, 120)!r}"
    elif passed_d:
        outcome, detail = PARITY_GAP, verdict_b
    elif passed_b:
        outcome, detail = BROWSER_ONLY_PASS, verdict_d
    else:
        outcome, detail = BOTH_FAIL, verdict_d

    suspects, missing = suspects_for(sql, contract)
    return CaseOutcome(case_id, outcome, verdict_d, verdict_b, detail, suspects, missing)
