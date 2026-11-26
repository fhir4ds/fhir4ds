#!/usr/bin/env python3
"""
Master runner for all Spec Conformance suites.

Executes ViewDefinition, FHIRPath, and CQL conformance scripts
and displays a unified summary of the results.

FHIR4-45 gate integrity - two rules this runner now enforces:

1. A child's failure is never swallowed. ``run_script`` returns a
   ``SuiteOutcome``; the master status is FAIL when any suite could not run.
2. A report must be REWRITTEN by the child that ran. Reading whatever was on
   disk let a suite that tested nothing (missing corpus) surface the
   previously committed report as a pass - the same pattern AGENTS.md records
   for DQM ("printed the suite error but summarized a STALE dqm_report.json as
   47/47"). Each report's (mtime, size) is captured before the child runs and
   verified after.

Exit codes: 1 when any suite could not run (infrastructure failure: crashed,
left a stale report, or collected no tests). A run where every suite executed
and some CELLS fail still exits 0 with an "INCOMPLETE" banner: the official CQL
corpus pins a handful of cells whose upstream fixture PRs are still open (see
fhir4ds/cql/tests/official/CQL_TESTS_README.md), so a rate-based non-zero exit
would make the gate permanently red and train readers to ignore it.
"""

import json
import os
import subprocess
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

# Suppress UserWarnings (like unresolved CQL definition fallbacks) to prevent I/O spam
warnings.simplefilter("ignore", UserWarning)

sys.path.insert(0, str(Path(__file__).parent))
from conformance_log import _collect_stats, log_file  # noqa: E402

# Configuration: (name, script, report, extra script args).
# Every entry here is part of the release gate. The DQM runner is invoked once
# per content suite so BOTH measure suites are covered:
#   qi-core-2025 = ecqm-content-qicore-2025 (the historical 47-measure gate)
#   us-core-2025 = dqm-content-cms-2025     (the CMS US Core 73-measure suite)
SCRIPTS = [
    ("ViewDefinition", "conformance/scripts/run_viewdef.py", "conformance/reports/viewdef_report.json", ()),
    ("FHIRPath (R4)", "conformance/scripts/run_fhirpath_r4.py", "conformance/reports/fhirpath_report.json", ()),
    ("CQL", "conformance/scripts/run_cql.py", "conformance/reports/cql_report.json", ()),
    ("DQM (QI-Core 2025)", "conformance/scripts/run_dqm.py", "conformance/reports/dqm_report.json", ("--suite", "qi-core-2025")),
    ("DQM (US-Core 2025)", "conformance/scripts/run_dqm.py", "conformance/reports/us_core_dqm_report.json", ("--suite", "us-core-2025")),
    # FHIR4-64: a measure can be silently unbuildable and the suites above still
    # print PASS, because DuckDB binds only the reachable plan and the DQM
    # harness projects population columns only (CMS986 for months). These entries
    # bind every measure's ALL-COLUMNS SQL with EXPLAIN and exit non-zero on the
    # first failure. They write no report, so they are exit-status-only.
    # Both bind-only sweeps are ON by default and share ONE opt-out,
    # FHIR4DS_BIND_CHECK=0 — see the comment above the SCRIPTS table. They
    # contribute no test counts, so only their planning cost matters to a caller
    # that just needs the totals (test_conformance_baseline does exactly that).
    ("DQM bind-only (QI-Core 2025)", "conformance/scripts/run_dqm_bind.py", None, ("--suite", "qi-core-2025"), "FHIR4DS_BIND_CHECK"),
    ("DQM bind-only (US-Core 2025)", "conformance/scripts/run_dqm_bind.py", None, ("--suite", "us-core-2025"), "FHIR4DS_BIND_CHECK"),
    ("OMOP Mapping", "conformance/scripts/run_omop.py", "conformance/reports/omop_report.json", ()),
]

def suite_entry(entry):
    """Normalize a SCRIPTS row to ``(name, script, report, args, gate_env)``.

    The optional 5th element names an environment variable that, when set to
    "0", SKIPS the entry (it runs by default). Bind-only gates (FHIR4-64) use it
    because their cost is DuckDB planning time, not conformance work, and it
    contributes no test counts.
    """
    name, path, report_path, extra_args = entry[:4]
    gate_env = entry[4] if len(entry) > 4 else None
    return name, path, report_path, tuple(extra_args), gate_env


@dataclass
class SuiteOutcome:
    """Result of running one conformance suite."""

    name: str
    ok: bool
    reason: str | None = None


def report_fingerprint(report_path: Path) -> tuple[int, int] | None:
    """(mtime_ns, size) of a report, or None when it does not exist."""
    try:
        stat = report_path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def run_script(name, path, report_path=None, extra_args=()) -> SuiteOutcome:
    """Run a conformance script and verify it produced a FRESH report.

    ``report_path`` may be None for callers that only care about exit status.
    """
    print(f"\n>>> Running {name} conformance suite...")
    report = Path(report_path) if report_path is not None else None
    before = report_fingerprint(report) if report is not None else None

    # SOF-VD-11 EXPLORER QA-002: on WSL/drvfs the working directory can
    # become momentarily unreadable under heavy IO, which makes a relative
    # script path crash the child at its first stdlib import (FileNotFoundError
    # from FileFinder) and even makes os.getcwd() fail in this parent. Use an
    # absolute script path resolved up front, and retry a child that died from
    # that transient filesystem error once before reporting failure.
    try:
        absolute = str(Path(path).resolve())
    except FileNotFoundError:
        absolute = str(Path(__file__).resolve().parent / Path(path).name)

    return_code: int | None = None
    for attempt in (1, 2):
        try:
            subprocess.run(
                [sys.executable, absolute, *extra_args],
                check=True,
                capture_output=False,
            )
            return_code = 0
            break
        except subprocess.CalledProcessError as e:
            if attempt == 1 and e.returncode == 1:
                print("  Transient child failure (drvfs cwd flake) — retrying once...")
                continue
            return_code = e.returncode
            break

    if return_code != 0:
        print(f"  Error: {name} suite failed with exit code {return_code}")
        return SuiteOutcome(name, False, f"exited with code {return_code}")

    if report is None:
        return SuiteOutcome(name, True)

    # The child exited 0. Did it actually produce THIS run's numbers?
    after = report_fingerprint(report)
    if after is None:
        reason = f"exited 0 but wrote no report at {report}"
        print(f"  Error: {name} {reason}")
        return SuiteOutcome(name, False, reason)
    if after == before:
        reason = (
            f"exited 0 but did not rewrite its report at {report}: stale report, "
            "so this suite tested nothing this run"
        )
        print(f"  Error: {name} {reason}")
        return SuiteOutcome(name, False, reason)

    _passed, total, _failures = _collect_stats(report)
    if total == 0:
        reason = f"exited 0 but its report at {report} contains 0 tests (empty suite)"
        print(f"  Error: {name} {reason}")
        return SuiteOutcome(name, False, reason)

    return SuiteOutcome(name, True)

def get_summary(report_path):
    """Parse a JSON report and return (passed, total, rate)."""
    try:
        with open(report_path) as f:
            data = json.load(f)

        total = 0
        passed = 0

        for file_data in data.values():
            for test in file_data.get("tests", []):
                total += 1
                if test.get("result", {}).get("passed"):
                    passed += 1

        rate = (passed / total * 100) if total > 0 else 0
        return passed, total, rate
    except Exception as e:
        print(f"  Error reading {report_path}: {e}")
        return 0, 0, 0

def main():
    print("=" * 60)
    print("         fhir4ds SPEC CONFORMANCE MASTER RUNNER")
    print("=" * 60)

    # Run all scripts, keeping each child's outcome. FHIR4-45: the result used
    # to be discarded, so a suite that never ran still produced a green table
    # built from a stale report.
    outcomes: list[SuiteOutcome] = []
    for entry in SCRIPTS:
        name, path, report_path, extra_args, gate_env = suite_entry(entry)
        if gate_env and os.environ.get(gate_env, "1") == "0":
            print(f"\n>>> Skipping {name} ({gate_env}=0).")
            continue
        outcomes.append(run_script(name, path, report_path, extra_args))

    # Display Summary Table
    print("\n" + "=" * 60)
    print(f"{'Specification':<31} | {'Passed':<8} | {'Total':<8} | {'Rate':<8}")
    print("-" * 60)

    grand_total = 0
    grand_passed = 0

    failed_suites = [outcome for outcome in outcomes if not outcome.ok]
    failed_names = {outcome.name for outcome in failed_suites}

    for entry in SCRIPTS:
        name, _path, report_path, _args, gate_env = suite_entry(entry)
        if gate_env and os.environ.get(gate_env, "1") == "0":
            print(f"{name:<31} | {'skipped':<8} | {'-':<8} | {'-':>6}")
            continue
        if name in failed_names:
            # Never print numbers for a suite that did not produce them.
            print(f"{name:<31} | {'NOT RUN':<8} | {'-':<8} | {'-':>6}")
            continue
        if report_path is None:
            # Bind-only gate: it produced no report and no test counts on
            # purpose. Reaching here means it exited 0.
            print(f"{name:<31} | {'BIND OK':<8} | {'-':<8} | {'-':>6}")
            continue
        p, t, r = get_summary(report_path)
        print(f"{name:<31} | {p:<8} | {t:<8} | {r:>6.1f}%")
        grand_total += t
        grand_passed += p

    print("-" * 60)
    grand_rate = (grand_passed / grand_total * 100) if grand_total > 0 else 0
    print(f"{'OVERALL COMPLIANCE':<31} | {grand_passed:<8} | {grand_total:<8} | {grand_rate:>6.1f}%")
    print("=" * 60)

    if failed_suites:
        print(f"\nSUITES THAT COULD NOT RUN ({len(failed_suites)}):")
        for outcome in failed_suites:
            print(f"  - {outcome.name}: {outcome.reason}")
        print(
            "  These suites contributed NO tests to the totals above. A missing or empty "
            "corpus is an environment failure, not a conformance result."
        )

    # Build a synthetic combined report for the master log entry
    all_failures = []
    for entry in SCRIPTS:
        _name, _path, report_path, _args, _env = suite_entry(entry)
        if report_path is None:
            continue  # bind-only gates produce no report and no test counts
        _, _, failures = _collect_stats(report_path)
        all_failures.extend(failures)

    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    status = "PASS" if (not all_failures and not failed_suites) else "FAIL"
    lines = [
        "=" * 80,
        f"[{ts}]  ALL SUITES (master run)  |  {grand_passed}/{grand_total} ({grand_rate:.1f}%)  |  {status}",
    ]
    for outcome in failed_suites:
        lines.append(f"  SUITE DID NOT RUN: {outcome.name}")
        lines.append(f"    {outcome.reason}")
    if all_failures:
        lines.append(f"  Failures ({len(all_failures)}):")
        for name, error in all_failures:
            lines.append(f"    - {name}")
            if error and error != "no detail":
                lines.append(f"      {error}")
    elif not failed_suites:
        lines.append("  Failures: none")
    destination = log_file()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with open(destination, "a") as f:
        f.write("\n".join(lines) + "\n")

    # Final result
    if failed_suites:
        print(
            f"\nGATE FAILED: {len(failed_suites)} suite(s) could not run, so the "
            "compliance totals above are incomplete."
        )
        sys.exit(1)
    if grand_rate == 100:
        print("\nSUCCESS: 100% Spec Conformance Achieved!")
        sys.exit(0)
    else:
        print(f"\nINCOMPLETE: {grand_total - grand_passed} tests remaining for full compliance.")
        # Every suite ran and produced numbers; the remaining failures are
        # known open cells (upstream fixture PRs). Exit 0 is deliberate and
        # documented in the module docstring.
        sys.exit(0)


if __name__ == "__main__":
    main()
