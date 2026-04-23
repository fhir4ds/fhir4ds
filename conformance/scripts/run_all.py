#!/usr/bin/env python3
"""
Master runner for all Spec Conformance suites.

Executes ViewDefinition, FHIRPath, and CQL conformance scripts
and displays a unified summary of the results.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from conformance_log import log_run, _collect_stats

# Configuration
SCRIPTS = [
    ("ViewDefinition", "conformance/scripts/run_viewdef.py", "conformance/reports/viewdef_report.json"),
    ("FHIRPath (R4)", "conformance/scripts/run_fhirpath_r4.py", "conformance/reports/fhirpath_report.json"),
    ("CQL", "conformance/scripts/run_cql.py", "conformance/reports/cql_report.json"),
    ("DQM (QI Core 2025)", "conformance/scripts/run_dqm.py", "conformance/reports/dqm_report.json"),
]

def run_script(name, path):
    """Run a conformance script and handle output."""
    print(f"\n>>> Running {name} conformance suite...")
    try:
        # Run and capture output to prevent it from cluttering the master summary
        # but print a progress indicator.
        subprocess.run([sys.executable, path], check=True, capture_output=False)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  Error: {name} suite failed with exit code {e.returncode}")
        return False

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

    # Run all scripts
    for name, path, _ in SCRIPTS:
        run_script(name, path)

    # Display Summary Table
    print("\n" + "=" * 60)
    print(f"{'Specification':<25} | {'Passed':<8} | {'Total':<8} | {'Rate':<8}")
    print("-" * 60)
    
    grand_total = 0
    grand_passed = 0

    for name, _, report_path in SCRIPTS:
        p, t, r = get_summary(report_path)
        print(f"{name:<25} | {p:<8} | {t:<8} | {r:>6.1f}%")
        grand_total += t
        grand_passed += p

    print("-" * 60)
    grand_rate = (grand_passed / grand_total * 100) if grand_total > 0 else 0
    print(f"{'OVERALL COMPLIANCE':<25} | {grand_passed:<8} | {grand_total:<8} | {grand_rate:>6.1f}%")
    print("=" * 60)

    # Build a synthetic combined report for the master log entry
    all_failures = []
    for _, _, report_path in SCRIPTS:
        _, _, failures = _collect_stats(report_path)
        all_failures.extend(failures)

    from datetime import datetime, timezone
    from pathlib import Path as _P
    LOG_FILE = _P("conformance/reports/conformance.log")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    status = "PASS" if not all_failures else "FAIL"
    lines = [
        "=" * 80,
        f"[{ts}]  ALL SUITES (master run)  |  {grand_passed}/{grand_total} ({grand_rate:.1f}%)  |  {status}",
    ]
    if all_failures:
        lines.append(f"  Failures ({len(all_failures)}):")
        for name, error in all_failures:
            lines.append(f"    - {name}")
            if error and error != "no detail":
                lines.append(f"      {error}")
    else:
        lines.append("  Failures: none")
    with open(LOG_FILE, "a") as f:
        f.write("\n".join(lines) + "\n")

    # Final result
    if grand_rate == 100:
        print("\nSUCCESS: 100% Spec Conformance Achieved!")
        sys.exit(0)
    else:
        print(f"\nINCOMPLETE: {grand_total - grand_passed} tests remaining for full compliance.")
        # We don't exit with non-zero here because we expect some failures during development
        sys.exit(0)

if __name__ == "__main__":
    main()
