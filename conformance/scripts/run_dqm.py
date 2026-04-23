#!/usr/bin/env python3
"""
Run DQM (Data Quality Measures) conformance tests.

Leverages the benchmarking runner infrastructure to execute all 2025 QI Core
measures and verify their accuracy against official test cases.
"""

import json
import os
import sys
import time
from pathlib import Path

# Ensure we can import fhir4ds and benchmarking
sys.path.insert(0, os.getcwd())
sys.path.insert(0, str(Path(__file__).parent))
from conformance_log import log_run

# Deeply-nested CQL libraries can exceed Python's default recursion limit
sys.setrecursionlimit(8000)

from fhir4ds.dqm.tests.conformance.cli import _discover_measures
from fhir4ds.dqm.tests.conformance.database import BenchmarkDatabase
from fhir4ds.dqm.tests.conformance.loader import load_test_suite
from fhir4ds.dqm.tests.conformance.runner import run_measure
from fhir4ds.dqm.tests.conformance.config import SKIP_ON_FAILURE, KNOWN_FAILURES

OUTPUT_FILE = Path("conformance/reports/dqm_report.json")

def main():
    suite = "2025"
    print(f">>> Discovering DQM measures (suite: {suite})...")
    configs = _discover_measures(suite=suite)
    
    # Filter out known bad measures
    configs = [c for c in configs if c.id not in SKIP_ON_FAILURE]
    
    if not configs:
        print("ERROR: No valid measures found.")
        sys.exit(1)

    print("Initializing database...")
    db = BenchmarkDatabase()

    print(f"Loading test data for {len(configs)} measures...")
    db.load_all_test_data(configs)

    print("Loading valuesets...")
    all_vs_paths = []
    seen = set()
    for c in configs:
        for p in c.valueset_paths:
            if str(p) not in seen:
                seen.add(str(p))
                all_vs_paths.append(p)
    db.load_all_valuesets(all_vs_paths)

    report = {}
    total_measures = len(configs)
    passed_measures = 0
    
    print(f"\nRunning {total_measures} measures...")

    for config in configs:
        print(f"  {config.id}: ", end="", flush=True)
        try:
            # Scope data to this measure
            db.scope_to_measure(config.id)

            # Load test suite
            test_suite = load_test_suite(config)

            # Run measure
            result = run_measure(
                db.conn,
                config,
                test_suite,
                verbose=False,
                all_columns=False, # Only population definitions for conformance
                audit=False
            )

            accuracy = result.comparison.accuracy_pct if result.comparison else 0
            passed = (accuracy == 100.0)
            
            test_obj = {
                "name": "Full Logic Accuracy",
                "result": {
                    "passed": passed
                }
            }
            if not passed:
                test_obj["result"]["error"] = f"Accuracy: {accuracy:.1f}%"
                print(f"FAILED ({accuracy:.1f}%)")
            else:
                passed_measures += 1
                print("PASSED")

            report[config.id] = { "tests": [test_obj] }

        except Exception as e:
            print(f"ERROR: {e}")
            report[config.id] = {
                "tests": [{
                    "name": "Full Logic Accuracy",
                    "result": {
                        "passed": False,
                        "error": str(e),
                    }
                }]
            }
        finally:
            db.unscope_resources()

    # Save report
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nConformance report generated at {OUTPUT_FILE}")
    print(f"Summary: {passed_measures}/{total_measures} measures passed ({passed_measures/total_measures:.1%})")
    log_run("DQM (QI Core 2025)", OUTPUT_FILE)

if __name__ == "__main__":
    main()
