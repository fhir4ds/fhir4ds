"""Tier A, OMOP mapping: the 38 sectioned checks on both surfaces.

``run_omop.build_connection`` loads the demo bundle and materialises the OMOP
views through the library's ViewDefinitions; ``run_omop.run_checks`` runs the
sectioned checks against a connection. The view SQL is identical on both
surfaces, so any difference is the function surface.
"""

from __future__ import annotations

import sys
import time

from ..reference_bundle import REPO_ROOT, EnvironmentInputMissing
from . import SuiteResult, _short, pass_fail_case

SUITE = "omop"


def runner():
    """``conformance.scripts.run_omop`` (namespace package at the repo root)."""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from conformance.scripts import run_omop

    return run_omop


def _build(con, run_omop) -> str:
    """``run_omop.build_connection`` on an existing connection; returns the view SQL.

    OR REPLACE: the suite evaluators share one connection per surface.
    """
    con.execute("CREATE OR REPLACE TABLE resources (resource JSON)")
    for line in (run_omop.OMOP_DIR / "demo" / "resources.ndjson").read_text().splitlines():
        if line.strip():
            con.execute("INSERT INTO resources VALUES (?)", [line.strip()])
    views = run_omop.create_omop_views(con, source_table="resources")
    return "\n".join(str(sql) for sql in views.values())


def _checks(results: dict) -> dict[str, tuple[bool, str]]:
    return {
        f"{section}::{item['name']}": (bool(item["ok"]), str(item.get("error", "")))
        for section, items in results["sections"].items()
        for item in items
    }


def run(desktop, browser, contract) -> SuiteResult:
    """Evaluate the OMOP mapping suite on both surfaces."""
    run_omop = runner()
    if not (run_omop.OMOP_DIR / "demo" / "resources.ndjson").exists():
        raise EnvironmentInputMissing(f"OMOP demo bundle not found at {run_omop.OMOP_DIR}")

    started = time.perf_counter()
    view_sql = _build(desktop, run_omop)
    desktop_checks = _checks(run_omop.run_checks(desktop))
    try:
        _build(browser, run_omop)
        browser_checks = _checks(run_omop.run_checks(browser))
    except Exception as exc:  # noqa: BLE001 - a surface that cannot build is the finding
        browser_checks = {}
        build_error = f"view build failed on the browser contract: {_short(exc)}"
    else:
        build_error = "check missing on the browser contract"

    outcomes = []
    for case_id, (passed_d, reason_d) in desktop_checks.items():
        passed_b, reason_b = browser_checks.get(case_id, (False, build_error))
        outcomes.append(
            pass_fail_case(case_id, passed_d, reason_d, passed_b, reason_b, sql=view_sql, contract=contract)
        )
    return SuiteResult(SUITE, tuple(outcomes), 0, time.perf_counter() - started)
