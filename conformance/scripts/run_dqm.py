#!/usr/bin/env python3
"""
Run DQM (Data Quality Measures) conformance tests.

Leverages the benchmarking runner infrastructure to execute all 2025 QI Core
measures and verify their accuracy against official test cases.
"""

import json
import os
import sys
import warnings
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

# Suppress UserWarnings (like unresolved CQL definition fallbacks) to prevent I/O spam
warnings.simplefilter("ignore", UserWarning)

OUTPUT_FILE = Path("conformance/reports/dqm_report.json")

def _elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000


def _time_phase(timings: dict, name: str, func):
    start = time.perf_counter()
    result = func()
    timings[name] = _elapsed_ms(start)
    return result


def _print_slowest(report: dict, timing_key: str, label: str, limit: int = 8) -> None:
    rows = []
    for measure_id, measure_report in report.items():
        if measure_id.startswith("_"):
            continue
        timings = measure_report.get("timings_ms", {})
        value = timings.get(timing_key, 0)
        if value:
            rows.append((value, measure_id))
    if not rows:
        return
    print(f"\nSlowest by {label}:")
    for value, measure_id in sorted(rows, reverse=True)[:limit]:
        print(f"  {measure_id}: {value / 1000:.2f}s")


def main():
    suite = "2025"
    suite_start = time.perf_counter()
    suite_timings = {}

    print(f">>> Discovering DQM measures (suite: {suite})...")
    configs = _time_phase(
        suite_timings,
        "measure_discovery_ms",
        lambda: _discover_measures(suite=suite),
    )
    
    # Filter out known bad measures
    configs = [c for c in configs if c.id not in SKIP_ON_FAILURE]

    if not configs:
        print("ERROR: No valid measures found.")
        sys.exit(1)

    print("Initializing database...")
    db = _time_phase(suite_timings, "database_init_ms", BenchmarkDatabase)
    if db.is_cpp:
        print(">>> C++ extension and Python fallback UDFs loaded successfully")
    else:
        print(">>> Python fallback UDFs loaded successfully (C++ extension NOT loaded)")

    print(f"Loading test data for {len(configs)} measures...")
    _time_phase(
        suite_timings,
        "test_data_load_ms",
        lambda: db.load_all_test_data(configs),
    )

    print("Loading valuesets...")
    all_vs_paths = []
    seen = set()
    for c in configs:
        for p in c.valueset_paths:
            if str(p) not in seen:
                seen.add(str(p))
                all_vs_paths.append(p)
    _time_phase(
        suite_timings,
        "valueset_load_ms",
        lambda: db.load_all_valuesets(all_vs_paths),
    )
    suite_timings["valueset_file_count"] = len(all_vs_paths)

    report = {}
    total_measures = len(configs)
    passed_measures = 0
    total_patients = 0
    library_cache = {}
    
    print(f"\nRunning {total_measures} measures...")

    for config in configs:
        print(f"  {config.id}: ", end="", flush=True)
        measure_wall_start = time.perf_counter()
        try:
            # Scope data to this measure
            scope_start = time.perf_counter()
            db.scope_to_measure(config.id)
            scope_ms = _elapsed_ms(scope_start)

            # Load test suite
            test_suite_start = time.perf_counter()
            test_suite = load_test_suite(config)
            test_suite_load_ms = _elapsed_ms(test_suite_start)

            # Run measure
            result = run_measure(
                db.conn,
                config,
                test_suite,
                verbose=False,
                all_columns=False, # Only population definitions for conformance
                audit=False,
                library_cache=library_cache,
            )

            accuracy = result.comparison.accuracy_pct if result.comparison else 0
            passed = (accuracy == 100.0)
            total_patients += result.patient_count
            
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

            timings = dict(result.timings)
            timings["resource_scope_ms"] = scope_ms
            timings["test_suite_load_ms"] = test_suite_load_ms
            timings["measure_wall_ms"] = _elapsed_ms(measure_wall_start)
            report[config.id] = {
                "tests": [test_obj],
                "patient_count": result.patient_count,
                "accuracy_pct": accuracy,
                "sql_size_bytes": len(result.sql),
                "timings_ms": timings,
            }

        except Exception as e:
            print(f"ERROR: {e}")
            report[config.id] = {
                "tests": [{
                    "name": "Full Logic Accuracy",
                    "result": {
                        "passed": False,
                        "error": str(e),
                    }
                }],
                "timings_ms": {
                    "measure_wall_ms": _elapsed_ms(measure_wall_start),
                },
            }
        finally:
            db.unscope_resources()

    suite_timings["measure_run_ms"] = sum(
        measure.get("timings_ms", {}).get("measure_wall_ms", 0)
        for key, measure in report.items()
        if not key.startswith("_")
    )
    suite_timings["suite_wall_ms"] = _elapsed_ms(suite_start)
    report["_summary"] = {
        "suite": suite,
        "total_measures": total_measures,
        "passed_measures": passed_measures,
        "accuracy_pct": (passed_measures / total_measures * 100) if total_measures else 0,
        "total_patients": total_patients,
        "library_cache_entries": len(library_cache),
        "timings_ms": suite_timings,
    }

    # Save report
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nConformance report generated at {OUTPUT_FILE}")
    print(f"Summary: {passed_measures}/{total_measures} measures passed ({passed_measures/total_measures:.1%})")
    print("\nSuite timings:")
    for key, value in suite_timings.items():
        if key.endswith("_ms"):
            print(f"  {key}: {value / 1000:.2f}s")
        else:
            print(f"  {key}: {value}")
    print(f"  library_cache_entries: {len(library_cache)}")
    _print_slowest(report, "total_ms", "measure total")
    _print_slowest(report, "library_translation_ms", "library translation")
    _print_slowest(report, "sql_generation_ms", "SQL generation")
    _print_slowest(report, "sql_execution_ms", "SQL execution")
    _print_slowest(report, "sql_write_ms", "SQL writing")
    _print_slowest(report, "test_suite_load_ms", "test suite loading")
    log_run("DQM (QI Core 2025)", OUTPUT_FILE)

if __name__ == "__main__":
    main()
