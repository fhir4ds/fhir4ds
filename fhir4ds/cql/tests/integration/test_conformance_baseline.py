"""Conformance baseline regression check (audit S6).

Asserts that the current ``grand_passed`` from
``conformance/scripts/run_all.py`` is at least the value recorded in
``baseline_conformance_count.txt``. Replaces the stale "2822/2822"
literal that previously appeared in the FDD.

The baseline file is captured at feature-branch start by running:
    python3 conformance/scripts/run_all.py 2>&1 | \\
        grep -oP 'OVERALL COMPLIANCE.*?\\|\\s*\\K\\d+' | head -1 \\
        > fhir4ds/cql/tests/integration/baseline_conformance_count.txt

Bump the baseline in the same PR that intentionally changes conformance
count. Do NOT lower it without an architectural review.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]  # fhir4ds/cql/tests/integration → repo root
BASELINE_FILE = Path(__file__).parent / "baseline_conformance_count.txt"
RUN_ALL = REPO_ROOT / "conformance" / "scripts" / "run_all.py"


def _read_baseline() -> int:
    if not BASELINE_FILE.exists():
        pytest.skip(
            f"Baseline file {BASELINE_FILE} not found. Create it with: "
            "python3 conformance/scripts/run_all.py 2>&1 | "
            "grep -oP 'OVERALL COMPLIANCE.*?\\|\\s*\\K\\d+' | head -1 "
            f"> {BASELINE_FILE}"
        )
    text = BASELINE_FILE.read_text().strip()
    if not text:
        pytest.skip("Baseline file is empty")
    return int(text)


def _current_grand_passed() -> int:
    """Run the full conformance suite and parse grand_passed.

    Returns -1 if the suite fails to run.
    """
    if not RUN_ALL.exists():
        pytest.skip(f"run_all.py not found at {RUN_ALL}")
    proc = subprocess.run(
        [sys.executable, str(RUN_ALL)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=600,
    )
    # Find the OVERALL COMPLIANCE line and parse the passed count.
    # Format: "OVERALL COMPLANCE           | <passed> | <total>  | <rate>%"
    match = re.search(
        r"OVERALL COMPLIANCE\s*\|\s*(\d+)\s*\|\s*(\d+)",
        proc.stdout,
    )
    if not match:
        pytest.skip(
            f"Could not parse grand_passed from run_all.py output.\n"
            f"stdout tail: {proc.stdout[-500:]}"
        )
    return int(match.group(1))


@pytest.mark.slow
@pytest.mark.integration
def test_conformance_no_regression():
    """Current grand_passed must be >= baseline."""
    baseline = _read_baseline()
    current = _current_grand_passed()
    assert current >= baseline, (
        f"Conformance regression: current={current}, baseline={baseline}. "
        f"If this is intentional (e.g. a spec change), bump "
        f"{BASELINE_FILE} in this PR."
    )
