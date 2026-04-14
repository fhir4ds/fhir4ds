"""
Command-line interface for benchmarking runner.
"""
import argparse
from pathlib import Path
import sys
import json
import re
import time

# Deeply-nested CQL libraries (e.g. with many included fluent functions)
# can exceed Python's default recursion limit during AST translation.
sys.setrecursionlimit(8000)


def main():
    parser = argparse.ArgumentParser(
        description="Run CQL measure benchmarks"
    )
    parser.add_argument(
        "--measure", "-m",
        help="Measure ID(s) to run (e.g., CMS165 or CMS165,CMS124). If not specified, runs all discovered measures.",
    )
    parser.add_argument(
        "--all-columns",
        action="store_true",
        help="Output all definition columns (not just population definitions)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run with audit_mode=True to capture evidence structs and measure overhead vs. baseline",
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output directory",
    )
    parser.add_argument(
        "--sql-format",
        choices=["mozilla", "default"],
        default="mozilla",
        help="SQL formatting style",
    )
    parser.add_argument(
        "--measurement-period-start",
        default="2026-01-01",
        help="Measurement period start date (default: 2026-01-01)"
    )
    parser.add_argument(
        "--measurement-period-end",
        default="2026-12-31",
        help="Measurement period end date (default: 2026-12-31)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of measures to run",
    )
    parser.add_argument(
        "--skip-errors",
        action="store_true",
        help="Continue on errors instead of stopping",
    )
    parser.add_argument(
        "--suite",
        choices=["2025", "2026"],
        default="2025",
        help="Content suite to benchmark: '2025' (ecqm-content-qicore-2025, default) or '2026' (dqm-content-qicore-2026)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print verbose output",
    )

    args = parser.parse_args()

    # Import modules (deferred to handle dependencies)
    from .config import OUTPUT_CQL_PY_DIR, SKIP_ON_FAILURE, KNOWN_FAILURES, MeasureConfig
    from .database import BenchmarkDatabase
    from .test_loader import load_test_suite
    from .measure_runner import run_measure
    from .result_writer import write_results

    # Set output directory
    output_dir = args.output or OUTPUT_CQL_PY_DIR

    # Auto-discover measures from selected suite
    configs = _discover_measures(suite=args.suite)

    # Filter by measure ID if specified (before applying limit)
    if args.measure:
        measure_ids = [m.strip().upper() for m in args.measure.split(",")]
        configs = [c for c in configs if c.id.upper() in measure_ids]
        missing = [mid for mid in measure_ids if mid not in [c.id.upper() for c in configs]]
        if missing:
            print(f"WARNING: Measures not found: {missing}")
            print(f"  Available: {[c.id for c in _discover_measures(suite=args.suite)][:10]}...")
    else:
        # Pre-filter measures known to hang/not-exist so they never block the run.
        # These are skipped unconditionally even without --skip-errors.
        pre_skip = [c for c in configs if c.id in SKIP_ON_FAILURE]
        if pre_skip:
            for c in pre_skip:
                print(f"Skipping {c.id} (in SKIP_ON_FAILURE)")
            configs = [c for c in configs if c.id not in SKIP_ON_FAILURE]

    if args.limit:
        configs = configs[:args.limit]

    if not configs:
        print("ERROR: No valid measures found.")
        sys.exit(1)

    # Initialize database once
    print("Initializing database...")
    db = BenchmarkDatabase()

    print(f"\nLoading test data for {len(configs)} measures...")
    try:
        data_stats = db.load_all_test_data(configs)
        print(f"  Loaded {data_stats['total_patients']} patients, "
              f"{data_stats['total_resources']} resources in {data_stats['load_time_s']:.2f}s")
    except Exception as e:
        print(f"  Warning: Data loading issue: {e}")

    # Load all valuesets
    print("Loading valuesets...")
    try:
        # Collect all unique valueset paths from all configs
        all_vs_paths = []
        seen = set()
        for c in configs:
            for p in c.valueset_paths:
                if str(p) not in seen:
                    seen.add(str(p))
                    all_vs_paths.append(p)
        vs_stats = db.load_all_valuesets(all_vs_paths)
        print(f"  Loaded {vs_stats['total_valuesets']} valuesets, "
              f"{vs_stats['total_codes']} codes in {vs_stats['load_time_s']:.2f}s")
    except Exception as e:
        print(f"  Warning: ValueSet loading issue: {e}")

    # Run each measure
    print(f"\nRunning {len(configs)} measures...")

    # Track results for summary
    results_summary = []
    successful = 0
    failed = 0
    skipped = 0

    for config in configs:
        print(f"\n{'='*60}")
        print(f"Measure: {config.id} - {config.name}")
        print(f"{'='*60}")

        # Clear module-level state from previous measure to prevent contamination
        try:
            from fhir4ds.cql.duckdb.udf.variable import clear_variables
            clear_variables(db.conn)
        except ImportError:
            pass

        # Free memory from previous measure's translator/SQL to avoid OOM
        # on memory-intensive measures like CMS1056
        import gc
        gc.collect()

        try:
            # Scope data to this measure to prevent cross-contamination
            # when multiple measures share patient IDs
            if len(configs) > 1:
                db.scope_to_measure(config.id)

            # Load test suite
            test_suite = load_test_suite(config)
            print(f"Test cases: {test_suite.total_patients}")

            # Run measure (pass all_columns and audit flags)
            result = run_measure(
                db.conn,
                config,
                test_suite,
                verbose=args.verbose,
                all_columns=args.all_columns,
                audit=args.audit,
            )

            # Write outputs
            paths = write_results(result, output_dir, args.sql_format)

            # Print summary
            print(f"\nResults:")
            print(f"  Patients: {result.patient_count}")
            print(f"  Total time: {result.timings.get('total_ms', 0):.1f}ms")

            if 'cql_parse_ms' in result.timings:
                print(f"  - Parse: {result.timings['cql_parse_ms']:.1f}ms")
            if 'sql_generation_ms' in result.timings:
                print(f"  - Translate: {result.timings['sql_generation_ms']:.1f}ms")
            if 'sql_execution_ms' in result.timings:
                print(f"  - Execute: {result.timings['sql_execution_ms']:.1f}ms")

            total_ms = result.timings.get('total_ms', 1)
            if total_ms > 0:
                print(f"  Patients/sec: {result.patient_count / (total_ms / 1000):.0f}")

            if result.comparison:
                print(f"\nAccuracy: {result.comparison.accuracy_pct:.1f}% "
                      f"({result.comparison.matching_patients}/{result.comparison.total_patients})")

                if result.comparison.mismatched_patients:
                    print(f"\nMismatches ({len(result.comparison.mismatched_patients)}):")
                    for mm in result.comparison.mismatched_patients:
                        print(f"  - {mm['patient_id']}: {mm['mismatches']}")

            print(f"\nOutputs:")
            for name, path in paths.items():
                print(f"  {name}: {path}")

            # Track for summary
            results_summary.append({
                "id": config.id,
                "name": config.name,
                "status": "success",
                "patient_count": result.patient_count,
                "accuracy_pct": result.comparison.accuracy_pct if result.comparison else 0,
                "total_ms": result.timings.get('total_ms', 0),
                "audit_fallback": getattr(result, 'audit_fallback', False),
                "audit_tier": getattr(result, 'audit_tier', None),
            })
            successful += 1

        except Exception as e:
            error_msg = str(e)
            results_summary.append({
                "id": config.id,
                "name": config.name,
                "status": "error",
                "error": error_msg,
            })

            if config.id in SKIP_ON_FAILURE or args.skip_errors:
                print(f"  WARNING: {config.id} failed, skipping: {e}")
                failed += 1
                continue
            else:
                print(f"  ERROR: {config.id} failed: {e}")
                failed += 1
                if args.verbose:
                    import traceback
                    traceback.print_exc()
                if not args.skip_errors:
                    print("\nStopping due to error. Use --skip-errors to continue.")
                    sys.exit(1)
        finally:
            if len(configs) > 1:
                db.unscope_resources()

    # Print summary if running multiple measures
    if len(configs) > 1:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Total measures: {len(configs)}")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print(f"  Skipped: {skipped}")

        # Calculate overall accuracy
        success_results = [r for r in results_summary if r['status'] == 'success' and r.get('patient_count', 0) > 0]
        if success_results:
            total_patients = sum(r['patient_count'] for r in success_results)
            total_time = sum(r['total_ms'] for r in success_results)
            print(f"\nOverall:")
            print(f"  Total patients: {total_patients}")
            print(f"  Total time: {total_time/1000:.1f}s")
            if total_time > 0:
                print(f"  Avg patients/sec: {total_patients / (total_time / 1000):.0f}")

        # Separate known failures from real regressions
        perfect = []
        known = []
        regressions = []
        errors = []

        for r in results_summary:
            mid = r["id"]
            if r["status"] == "error":
                if mid in KNOWN_FAILURES:
                    known.append(r)
                else:
                    errors.append(r)
            elif r.get("accuracy_pct", 0) == 100:
                perfect.append(r)
            elif mid in KNOWN_FAILURES:
                known.append(r)
            else:
                regressions.append(r)

        print(f"\n  PERFECT: {len(perfect)}/{len(configs)}")

        if known:
            print(f"\n  Known failures ({len(known)}) — upstream test-data issues:")
            for r in known:
                info = KNOWN_FAILURES.get(r["id"], {})
                acc = f"{r['accuracy_pct']:.1f}%" if r.get("accuracy_pct") is not None else "error"
                print(f"    {r['id']}: {acc} — {info.get('reason', r.get('error', 'unknown'))}")

        if regressions:
            print(f"\n  REGRESSIONS ({len(regressions)}) — NEEDS INVESTIGATION:")
            for r in regressions:
                print(f"    {r['id']}: {r.get('accuracy_pct', 0):.1f}%")

        if errors:
            print(f"\n  ERRORS ({len(errors)}):")
            for r in errors:
                print(f"    {r['id']}: {r.get('error', 'unknown')}")

        # Report audit fallback status when running with --audit
        if args.audit:
            audit_full = [r for r in success_results if r.get("audit_tier") == "full"]
            audit_pop = [r for r in success_results if r.get("audit_tier") == "population"]
            audit_fb = [r for r in success_results if r.get("audit_fallback")]
            audit_ok = [r for r in success_results if not r.get("audit_fallback")]
            print(f"\n  Audit coverage: {len(audit_ok)}/{len(success_results)} measures with audit evidence")
            if audit_full:
                print(f"    Full audit: {len(audit_full)}")
            if audit_pop:
                print(f"    Population-only audit: {len(audit_pop)}")
            if audit_fb:
                print(f"    Non-audit fallback: {', '.join(r['id'] for r in audit_fb)}")

        # Assert baseline: all non-known measures should be 100%
        if regressions:
            print(f"\n  BASELINE REGRESSION: {len(regressions)} measure(s) below 100% "
                  f"that are NOT in KNOWN_FAILURES!")
        else:
            print(f"\n  BASELINE OK: {len(perfect)}/{len(configs)} perfect, "
                  f"{len(known)} known failures (all upstream)")

        # Write summary JSON
        summary_path = output_dir / "all_measures_summary.json"
        with open(summary_path, 'w') as f:
            json.dump({
                "total_measures": len(configs),
                "successful": successful,
                "failed": failed,
                "skipped": skipped,
                "perfect": len(perfect),
                "known_failures": len(known),
                "regressions": len(regressions),
                "measures": results_summary
            }, f, indent=2)
        print(f"\nSummary written to: {summary_path}")


def _discover_measures(suite: str = "2025"):
    """Auto-discover all measures from the selected content suite.

    Args:
        suite: "2025" for ecqm-content-qicore-2025, "2026" for dqm-content-qicore-2026.
    """
    from .config import (
        VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR, MeasureConfig, get_suite_paths
    )

    suite_paths = get_suite_paths(suite)
    cql_dir = suite_paths["cql_dir"]
    valueset_dir = suite_paths["valueset_dir"]
    tests_dir = suite_paths["tests_dir"]
    bundle_dir = suite_paths["bundle_dir"]

    measures = []

    if not tests_dir.exists():
        print(f"ERROR: Test directory not found: {tests_dir}")
        return measures

    for test_dir in sorted(tests_dir.iterdir()):
        if not test_dir.is_dir():
            continue

        measure_name = test_dir.name

        # Find CQL file
        cql_path = cql_dir / f"{measure_name}.cql"
        if not cql_path.exists():
            # Try alternate naming (some measures have different CQL names)
            for cql_file in cql_dir.glob("*.cql"):
                if measure_name in cql_file.stem or cql_file.stem in measure_name:
                    cql_path = cql_file
                    break

        if not cql_path.exists():
            continue

        # Get population definitions from a MeasureReport in the test directory
        pop_defs = _extract_population_definitions(test_dir)
        if not pop_defs:
            continue

        # Build valueset paths including measure-specific bundle
        vs_paths = [valueset_dir, VALIDATOR_VALUESET_DIR, SUPPLEMENTAL_VALUESET_DIR]
        measure_vs_bundle = (
            bundle_dir / measure_name / f"{measure_name}-files"
            / f"valuesets-{measure_name}-bundle.json"
        )
        if measure_vs_bundle.exists():
            vs_paths.append(measure_vs_bundle)

        # For 2026, also include 2025 CQL dir for shared libraries
        # (CumulativeMedicationDuration, FHIRHelpers, etc.)
        inc_paths = [cql_dir]
        if suite == "2026":
            from .config import SUITE_2025_DIR
            fallback_cql = SUITE_2025_DIR / "input" / "cql"
            if fallback_cql.exists():
                inc_paths.append(fallback_cql)

        measures.append(MeasureConfig(
            id=_extract_measure_id(measure_name),
            name=measure_name,
            cql_path=cql_path,
            test_dir=test_dir,
            include_paths=inc_paths,
            valueset_paths=vs_paths,
            population_definitions=pop_defs,
        ))

    print(f"Discovered {len(measures)} measures from suite '{suite}'")
    return measures


def _extract_measure_id(measure_name: str) -> str:
    """
    Extract measure ID from measure name.

    Handles patterns:
    - CMS165FHIRControllingHighBloodPressure -> CMS165
    - CMS0334FHIRPCCesareanBirth -> CMS0334
    - CMSFHIR844HybridHospitalWideMortality -> CMSFHIR844
    - NHSNGlycemicControlHypoglycemiaInitialPopulation -> NHSNGlycemicControl
    """
    import re

    # CMS with optional FHIR prefix/suffix
    match = re.match(r'^(CMS(?:FHIR)?\d+)', measure_name)
    if match:
        return match.group(1)

    # NHSN prefix - capture first CamelCase word group after NHSN
    # e.g., NHSNGlycemicControlHypoglycemiaInitialPopulation -> NHSNGlycemicControl
    match = re.match(r'^(NHSN[A-Z][a-z]+(?:[A-Z][a-z]+)?)', measure_name)
    if match:
        return match.group(1)

    # Fallback
    return measure_name


def _extract_population_definitions(test_dir: Path) -> list:
    """Extract population definitions from MeasureReports in test directory.

    For multi-group measures, produces numbered definitions (e.g.
    ``"Denominator 1"``, ``"Denominator 2"``).  Single-group measures
    produce plain names (``"Denominator"``).
    """
    mapping = {
        "initial-population": "Initial Population",
        "denominator": "Denominator",
        "denominator-exclusion": "Denominator Exclusion",
        "denominator-exception": "Denominator Exception",
        "numerator": "Numerator",
        "numerator-exclusion": "Numerator Exclusion",
    }

    # First pass: determine max group count across all MeasureReports
    max_groups = 1
    for patient_dir in test_dir.iterdir():
        if not patient_dir.is_dir():
            continue
        for report_file in patient_dir.glob("MeasureReport-*.json"):
            try:
                with open(report_file) as f:
                    data = json.load(f)
                num_groups = len(data.get("group", []))
                if num_groups > max_groups:
                    max_groups = num_groups
            except Exception:
                pass

    # Second pass: collect definitions (numbered for multi-group)
    definitions = set()
    for patient_dir in test_dir.iterdir():
        if not patient_dir.is_dir():
            continue
        for report_file in patient_dir.glob("MeasureReport-*.json"):
            try:
                with open(report_file) as f:
                    data = json.load(f)

                for group_idx, group in enumerate(data.get("group", [])):
                    for pop in group.get("population", []):
                        coding = pop.get("code", {}).get("coding", [])
                        if not coding:
                            continue
                        code = coding[0].get("code", "")
                        base_name = mapping.get(code)
                        if base_name:
                            if max_groups > 1:
                                definitions.add(f"{base_name} {group_idx + 1}")
                            else:
                                definitions.add(base_name)
            except Exception:
                pass

    # Sort by canonical eCQM population gating order so cascaded gating
    # logic in compare_results always processes prerequisites first.
    _CANONICAL_ORDER = [
        "Initial Population",
        "Denominator",
        "Denominator Exclusion",
        "Denominator Exception",
        "Numerator",
        "Numerator Exclusion",
        "Numerator Exception",
        "Measure Population",
        "Measure Population Exclusion",
    ]

    def _sort_key(name: str) -> tuple:
        # Strip trailing group number for canonical lookup, keep it for
        # stable secondary sort within the same base name.
        base = re.sub(r"\s+\d+$", "", name)
        group = re.search(r"\s+(\d+)$", name)
        group_num = int(group.group(1)) if group else 0
        try:
            return (group_num, _CANONICAL_ORDER.index(base), name)
        except ValueError:
            return (group_num, len(_CANONICAL_ORDER), name)

    return sorted(definitions, key=_sort_key)


if __name__ == "__main__":
    main()
