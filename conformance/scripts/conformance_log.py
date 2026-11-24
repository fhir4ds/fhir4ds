"""Shared utility for appending conformance run results to a persistent log."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path("conformance/reports/conformance.log")


def log_file() -> Path:
    """Resolve the log path, honouring FHIR4DS_CONFORMANCE_LOG.

    FHIR4-45: the gate-integrity tests exercise ``run_cql.main`` in-process,
    and those runs must not append entries to the tracked log. Resolving the
    path at call time (instead of importing a frozen constant) is what makes
    the override reach the log writer.
    """
    override = os.environ.get("FHIR4DS_CONFORMANCE_LOG")
    return Path(override) if override else LOG_FILE


def _collect_stats(report_path: str | Path):
    """Parse a conformance report JSON and return (passed, total, failures).

    failures is a list of (name, error) tuples for every non-passed test.
    """
    try:
        with open(report_path) as f:
            data = json.load(f)
    except Exception as e:
        return 0, 0, [("(could not read report)", str(e))]

    passed = 0
    total = 0
    failures = []

    for suite_key, suite_data in data.items():
        for test in suite_data.get("tests", []):
            total += 1
            result = test.get("result", {})
            if result.get("passed"):
                passed += 1
            else:
                name = f"{suite_key}::{test.get('name', '?')}"
                error = result.get("error") or result.get("reason") or "no detail"
                failures.append((name, error))

    return passed, total, failures


def log_run(suite_name: str, report_path: str | Path) -> None:
    """Append a conformance run entry to the persistent log file."""
    passed, total, failures = _collect_stats(report_path)
    rate = (passed / total * 100) if total > 0 else 0.0
    status = "PASS" if not failures else "FAIL"
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    lines = [
        "=" * 80,
        f"[{ts}]  {suite_name}  |  {passed}/{total} ({rate:.1f}%)  |  {status}",
    ]
    if failures:
        lines.append(f"  Failures ({len(failures)}):")
        for name, error in failures:
            lines.append(f"    - {name}")
            if error and error != "no detail":
                lines.append(f"      {error}")
    else:
        lines.append("  Failures: none")

    destination = log_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "a") as f:
        f.write("\n".join(lines) + "\n")
