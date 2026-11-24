"""Tier A, ViewDefinition: 144 official SQL-on-FHIR v2 tests on both surfaces.

``run_viewdef.run_test`` is the official comparator: it loads each test's
resources into a ``resources`` table, runs the generated SQL and compares the
rows. The generator is pure Python, so both surfaces execute identical SQL by
construction; the same call simply runs on each connection.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from ..reference_bundle import REPO_ROOT, EnvironmentInputMissing
from . import SuiteResult, pass_fail_case

SUITE = "viewdef"


def runner():
    """``conformance.scripts.run_viewdef`` (namespace package at the repo root).

    The script imports its sibling ``conformance_log`` as a top-level module,
    which only resolves when ``conformance/scripts`` is on ``sys.path``.
    """
    scripts = REPO_ROOT / "conformance" / "scripts"
    for entry in (REPO_ROOT, scripts):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    from conformance.scripts import run_viewdef

    return run_viewdef


def run(desktop, browser, contract, *, spec_dir: Path | None = None) -> SuiteResult:
    """Evaluate the ViewDefinition spec tests on both surfaces."""
    run_viewdef = runner()
    directory = Path(spec_dir) if spec_dir is not None else Path(run_viewdef.SPEC_TESTS_DIR)
    if not directory.exists():
        raise EnvironmentInputMissing(f"ViewDefinition spec tests not found at {directory}")
    generator = run_viewdef.SQLGenerator(strict_collection=True)

    started = time.perf_counter()
    outcomes = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        resources = data.get("resources", [])
        for index, test in enumerate(data.get("tests", [])):
            case_id = f"{path.name}::{test.get('title', f'test_{index}')}"
            passed_d, reason_d = run_viewdef.run_test(desktop, generator, test, resources)
            passed_b, reason_b = run_viewdef.run_test(browser, generator, test, resources)
            outcomes.append(
                pass_fail_case(
                    case_id,
                    passed_d,
                    reason_d,
                    passed_b,
                    reason_b,
                    sql=_generated_sql(run_viewdef, generator, test),
                    contract=contract,
                )
            )
    return SuiteResult(SUITE, tuple(outcomes), 0, time.perf_counter() - started)


def _generated_sql(run_viewdef, generator, test) -> str:
    """The test's generated SQL (for name attribution); empty when it does not generate."""
    try:
        return generator.generate(run_viewdef.parse_view_definition(json.dumps(test.get("view", {}))))
    except Exception:  # noqa: BLE001 - invalid views are part of the corpus
        return ""
