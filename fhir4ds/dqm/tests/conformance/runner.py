"""
Execute measures and collect results.
"""
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass

@dataclass
class TimingMetrics:
    """Performance metrics for a single phase."""
    phase_name: str
    duration_ms: float

@dataclass
class MeasureResult:
    """Results from running a single measure."""
    measure_id: str
    patient_count: int
    timings: Dict[str, float]  # phase -> duration_ms
    sql: str                   # Generated SQL
    results: List[Dict]        # Per-patient results
    comparison: Optional["ComparisonResult"] = None

@dataclass
class ComparisonResult:
    """Comparison between cql-py and expected results."""
    total_patients: int
    matching_patients: int
    mismatched_patients: List[Dict]  # Details of mismatches
    accuracy_pct: float


def run_measure(
    conn,
    measure_config: "MeasureConfig",
    test_suite: "TestSuite",
    verbose: bool = False,
    all_columns: bool = True,
    audit: bool = False,
) -> MeasureResult:
    """
    Execute a single measure and collect results.

    Args:
        conn: Database connection
        measure_config: Measure configuration
        test_suite: Test suite with expected results
        verbose: Print verbose output
        all_columns: If True, output all definitions; if False, only population definitions
        audit: If True, run with audit_mode=True to capture evidence structs.
               Falls back to non-audit mode if audit translation or execution fails.
    """
    timings = {}

    # Parse CQL (shared across audit and non-audit attempts)
    start = time.perf_counter()
    from fhir4ds.cql.parser import parse_cql
    cql_text = measure_config.cql_path.read_text()
    library = parse_cql(cql_text)
    timings["cql_parse_ms"] = (time.perf_counter() - start) * 1000

    # Normalize population definitions (shared)
    from fhir4ds.cql.parser.ast_nodes import Definition
    actual_defs = {
        stmt.name for stmt in library.statements
        if isinstance(stmt, Definition)
    }
    normalized_pop_defs, pop_name_map = _normalize_population_definitions(
        measure_config.population_definitions, actual_defs
    )

    # Build output columns (shared)
    if all_columns:
        all_definitions = [
            stmt.name for stmt in library.statements
            if isinstance(stmt, Definition) and not stmt.name.startswith("SDE")
        ]
        output_columns = {name: name for name in all_definitions}
    else:
        output_columns = {name: name for name in normalized_pop_defs}

    mp_params = {}
    if test_suite.measurement_period:
        mp_params["Measurement Period"] = test_suite.measurement_period

    measure_patient_ids = [tc.patient_id for tc in test_suite.test_cases]

    # Three-tier audit strategy (optimized: non-audit first as size heuristic):
    #   1. Generate non-audit SQL first (always needed as fallback, cheapest)
    #   2. Use non-audit SQL size AND translation time to decide which audit tier
    #   3. If audit fails or too large/slow, fall back to non-audit result
    #
    # Heuristics (audit translation is more memory/time intensive than non-audit):
    #   Time: non-audit translation >60s → skip audit (translation OOM risk)
    #   Size: <200KB non-audit → try full audit
    #         <350KB non-audit → try population-only audit
    #         >=350KB non-audit → skip audit entirely
    _NOAUDIT_FULL_THRESHOLD = 200_000    # try full audit if non-audit < 200KB
    _NOAUDIT_POP_THRESHOLD = 350_000     # try pop-only audit if non-audit < 350KB
    _NOAUDIT_TIME_THRESHOLD = 60_000     # skip audit if non-audit translation > 60s

    audit_fallback = False
    audit_tier = None  # tracks which tier succeeded: "full", "population", or None

    # Always generate non-audit SQL first (cheapest, always needed)
    noaudit_sql, noaudit_gen_ms = _translate_measure(
        conn, library, measure_config, output_columns, mp_params,
        measure_patient_ids, audit_mode=False,
    )

    if audit:
        from .config import KNOWN_FAILURES

        # Time guard: skip audit if non-audit translation was too slow (OOM risk)
        if noaudit_gen_ms > _NOAUDIT_TIME_THRESHOLD:
            print(f"  Skipping audit for {measure_config.id} "
                  f"(non-audit translation took {noaudit_gen_ms / 1000:.0f}s)")
        else:
            # Tier 1: Try full audit (only if non-audit SQL is small enough)
            if len(noaudit_sql) < _NOAUDIT_FULL_THRESHOLD:
                try:
                    sql, gen_ms = _translate_measure(
                        conn, library, measure_config, output_columns, mp_params,
                        measure_patient_ids, audit_mode=True, audit_expressions=True,
                    )
                    timings["sql_generation_ms"] = gen_ms
                    # Always save the full audit SQL — even if execution fails below,
                    # this file is preserved so prepare_cms_data.py can use it for
                    # the WASM demo (which runs on a small patient subset without OOM).
                    _write_sql(sql, measure_config, verbose, suffix="_audit_full")

                    # Raise expression depth limit to handle deeply nested audit expressions
                    conn.execute("SET max_expression_depth TO 10000")
                    start = time.perf_counter()
                    result_df = conn.execute(sql).df()
                    timings["sql_execution_ms"] = (time.perf_counter() - start) * 1000

                    # Accuracy guard
                    audit_results = result_df.to_dict("records")
                    import numpy as np
                    for row in audit_results:
                        for key, value in row.items():
                            if isinstance(value, np.ndarray):
                                row[key] = value.tolist()
                    audit_comparison = compare_results(
                        audit_results, test_suite, measure_config, pop_name_map,
                    )
                    expected_mismatches = KNOWN_FAILURES.get(
                        measure_config.id, {},
                    ).get("mismatches", 0)
                    actual_mismatches = (
                        audit_comparison.total_patients
                        - audit_comparison.matching_patients
                    )
                    if actual_mismatches > expected_mismatches:
                        raise RuntimeError(
                            f"Audit accuracy regression: "
                            f"{audit_comparison.accuracy_pct:.1f}% "
                            f"({actual_mismatches} mismatches vs "
                            f"{expected_mismatches} expected)"
                        )
                    audit_tier = "full"
                    # Write verified full audit SQL as the canonical _audit.sql.
                    # Do NOT write to the base file here — the base file always
                    # holds the non-audit SQL (written unconditionally below).
                    _write_sql(sql, measure_config, verbose, suffix="_audit")
                except Exception as full_err:
                    if verbose:
                        print(
                            f"  Full audit failed for {measure_config.id} "
                            f"({type(full_err).__name__}: "
                            f"{str(full_err)[:200]})"
                        )
                    else:
                        print(
                            f"  Full audit → population-only for "
                            f"{measure_config.id}: "
                            f"{type(full_err).__name__}"
                        )

            # Tier 2: Try population-only audit (if full didn't succeed and size ok)
            if audit_tier is None and len(noaudit_sql) < _NOAUDIT_POP_THRESHOLD:
                try:
                    sql, gen_ms = _translate_measure(
                        conn, library, measure_config, output_columns, mp_params,
                        measure_patient_ids, audit_mode=True,
                        audit_expressions=False,
                    )
                    timings["sql_generation_ms"] = gen_ms
                    _write_sql(sql, measure_config, verbose, suffix="_audit")

                    start = time.perf_counter()
                    result_df = conn.execute(sql).df()
                    timings["sql_execution_ms"] = (
                        (time.perf_counter() - start) * 1000
                    )

                    # Accuracy guard
                    pop_results = result_df.to_dict("records")
                    import numpy as np
                    for row in pop_results:
                        for key, value in row.items():
                            if isinstance(value, np.ndarray):
                                row[key] = value.tolist()
                    pop_comparison = compare_results(
                        pop_results, test_suite, measure_config, pop_name_map,
                    )
                    expected_mismatches = KNOWN_FAILURES.get(
                        measure_config.id, {},
                    ).get("mismatches", 0)
                    actual_mismatches = (
                        pop_comparison.total_patients
                        - pop_comparison.matching_patients
                    )
                    if actual_mismatches > expected_mismatches:
                        raise RuntimeError(
                            f"Population-only audit accuracy issue: "
                            f"{pop_comparison.accuracy_pct:.1f}%"
                        )
                    audit_tier = "population"
                    _write_sql(sql, measure_config, verbose)
                    if verbose:
                        print(
                            f"  Using population-only audit for "
                            f"{measure_config.id}"
                        )
                except Exception as pop_err:
                    if verbose:
                        print(
                            f"  Population-only audit failed for "
                            f"{measure_config.id} "
                            f"({type(pop_err).__name__}: "
                            f"{str(pop_err)[:200]})"
                        )
                    else:
                        print(
                            f"  Audit fallback (non-audit) for "
                            f"{measure_config.id}: "
                            f"{type(pop_err).__name__}"
                        )

            if audit_tier is None and len(noaudit_sql) >= _NOAUDIT_POP_THRESHOLD:
                print(
                    f"  Skipping audit for {measure_config.id} "
                    f"(non-audit SQL {len(noaudit_sql) // 1024}KB too large)"
                )

        if audit_tier is None:
            audit_fallback = True

    # Always write non-audit SQL as the canonical base file so that prepare_cms_data.py
    # and other downstream tools can rely on {measure}.sql being audit-expression-free.
    _write_sql(noaudit_sql, measure_config, verbose)

    if not audit or audit_fallback:
        # Non-audit path: execute and time pre-generated non-audit SQL
        sql = noaudit_sql
        timings["sql_generation_ms"] = noaudit_gen_ms

        start = time.perf_counter()
        result_df = conn.execute(sql).df()
        timings["sql_execution_ms"] = (time.perf_counter() - start) * 1000

    timings["total_ms"] = sum(timings.values())

    # Convert to list of dicts
    results = result_df.to_dict("records")

    # Post-process: convert numpy arrays to Python lists
    import numpy as np
    for row in results:
        for key, value in row.items():
            if isinstance(value, np.ndarray):
                row[key] = value.tolist()

    # Compare with expected (pass name map for singular/plural normalization)
    comparison = compare_results(results, test_suite, measure_config, pop_name_map)

    if verbose:
        print(f"Measure: {measure_config.id}")
        print(f"  Patients: {len(results)}")
        print(f"  Timings: {timings}")
        print(f"  Accuracy: {comparison.accuracy_pct:.1f}%")

    result = MeasureResult(
        measure_id=measure_config.id,
        patient_count=len(results),
        timings=timings,
        sql=sql,
        results=results,
        comparison=comparison,
    )
    result.audit_fallback = audit_fallback
    result.audit_tier = audit_tier
    return result


def _translate_measure(
    conn,
    library,
    measure_config,
    output_columns,
    mp_params,
    patient_ids,
    audit_mode: bool,
    audit_expressions: bool = True,
) -> tuple:
    """Translate a CQL library to population SQL.

    Returns (sql_string, generation_time_ms).
    """
    from fhir4ds.cql.parser import parse_cql
    from fhir4ds.cql.translator import CQLToSQLTranslator

    def library_loader(alias: str, version=None):
        for path in measure_config.include_paths:
            lib_file = path / f"{alias}.cql"
            if lib_file.exists():
                return parse_cql(lib_file.read_text())
        return None

    translator = CQLToSQLTranslator(
        connection=conn,
        library_loader=library_loader,
        audit_mode=audit_mode,
        audit_expressions=audit_expressions,
    )
    translator.translate_library(library)

    start = time.perf_counter()
    sql = translator.translate_library_to_population_sql(
        library=library,
        output_columns=output_columns,
        parameters=mp_params,
        patient_ids=patient_ids if patient_ids else None,
    )
    gen_ms = (time.perf_counter() - start) * 1000
    return sql, gen_ms


def _write_sql(sql: str, measure_config, verbose: bool, suffix: str = "") -> None:
    """Write generated SQL to output file for debugging."""
    from pathlib import Path
    from .config import OUTPUT_CQL_PY_DIR

    sql_dir = OUTPUT_CQL_PY_DIR / "sql"
    sql_dir.mkdir(parents=True, exist_ok=True)
    sql_path = sql_dir / f"{measure_config.id}{suffix}.sql"

    if len(sql) < 50000:
        try:
            import sqlparse
            formatted_sql = sqlparse.format(sql, reindent=True, keyword_case="upper", indent_width=2)
        except Exception:
            formatted_sql = sql
    else:
        formatted_sql = sql

    sql_path.write_text(f"-- Generated SQL for {measure_config.id}\n\n{formatted_sql}\n")
    if verbose:
        print(f"  SQL written to: {sql_path}")


def _unwrap_audit(val):
    """Extract .result from an audit struct dict, or return value as-is."""
    if isinstance(val, dict) and "result" in val and "evidence" in val:
        return val["result"]
    return val


def compare_results(
    actual_results: List[Dict],
    test_suite: "TestSuite",
    measure_config: "MeasureConfig",
    pop_name_map: Optional[Dict[str, str]] = None,
) -> ComparisonResult:
    """Compare actual results with expected results from test suite."""
    if pop_name_map is None:
        pop_name_map = {}

    expected_lookup = {
        tc.patient_id: tc.expected_results
        for tc in test_suite.test_cases
    }

    matching = 0
    mismatched = []

    # Deduplicate actual results by patient_id to prevent inflated counts
    # when LEFT JOINs in generated SQL produce multiple rows per patient.
    seen_patients = set()

    # Only evaluate patients that have expected results (test cases)
    for result in actual_results:
        patient_id = (
            result.get("patient_id") or
            result.get("Patient_id") or
            result.get("PATIENT_ID") or
            result.get("patient")
        )

        if patient_id not in expected_lookup:
            continue

        if patient_id in seen_patients:
            continue
        seen_patients.add(patient_id)

        expected = expected_lookup[patient_id]

        patient_matches = True
        mismatches = {}

        def _get_or_value(pop_key, default_key=None):
            """Get actual value for a population.

            Tries the exact key first, then falls back to the unnumbered
            base name (e.g. "Initial Population 1" → "Initial Population")
            for shared populations in multi-group measures.
            """
            mapped = pop_name_map.get(pop_key, default_key or pop_key)
            if isinstance(mapped, list):
                return any(bool(_unwrap_audit(result.get(n, False))) for n in mapped)
            val = _unwrap_audit(result.get(mapped))
            if val is not None:
                return bool(val)
            # Fallback: try unnumbered base name for shared populations
            base = _base_name(mapped)
            if base != mapped:
                val = _unwrap_audit(result.get(base))
                if val is not None:
                    return bool(val)
            return False

        def _get_count(pop_key, default_key=None):
            """Get the encounter/resource count for a population.

            Returns the number of items in a JSON list result, or 1/0 for
            boolean values.  Used for encounter-level gating decisions.
            """
            import json as _json
            mapped = pop_name_map.get(pop_key, default_key or pop_key)
            if isinstance(mapped, list):
                return sum(_get_count(n) for n in mapped)
            val = _unwrap_audit(result.get(mapped))
            if val is None:
                base = _base_name(mapped)
                if base != mapped:
                    val = _unwrap_audit(result.get(base))
            if val is None:
                return 0
            if isinstance(val, bool):
                return 1 if val else 0
            if isinstance(val, str):
                try:
                    parsed = _json.loads(val)
                    if isinstance(parsed, list):
                        return len(parsed)
                except (ValueError, TypeError):
                    pass
                return 1 if val else 0
            if isinstance(val, (list, tuple)):
                return len(val)
            return 1 if val else 0

        def _extract_group_suffix(name: str) -> Optional[str]:
            """Extract trailing group number from a numbered population name."""
            import re
            m = re.search(r'\s+(\d+)$', name)
            return m.group(1) if m else None

        def _base_name(name: str) -> str:
            """Strip trailing group number from a population name."""
            import re
            return re.sub(r'\s+\d+$', '', name)

        gated_values = {}  # Track gated population values for cascading

        for def_name in measure_config.population_definitions:
            # Map MeasureReport name to actual CQL column name(s)
            actual_val = _get_or_value(def_name)

            # eCQM population gating — use same group suffix for
            # multi-group measures so that e.g. "Numerator 1" is gated
            # by "Denominator 1", not by any Denominator.
            suffix = _extract_group_suffix(def_name)
            base = _base_name(def_name)
            _ip_key = f"Initial Population {suffix}" if suffix else "Initial Population"
            _denom_key = f"Denominator {suffix}" if suffix else "Denominator"
            _denom_excl_key = f"Denominator Exclusion {suffix}" if suffix else "Denominator Exclusion"
            _denom_except_key = f"Denominator Exception {suffix}" if suffix else "Denominator Exception"

            ip_actual = _get_or_value(_ip_key)
            # For shared IP (single IP for multi-group), fall back to plain IP
            if not ip_actual and suffix:
                ip_actual = _get_or_value("Initial Population")
            denom_actual = _get_or_value(_denom_key)
            denom_excl_actual = _get_or_value(
                _denom_excl_key,
                f"Denominator Exclusions {suffix}" if suffix else "Denominator Exclusions",
            )
            denom_except_actual = _get_or_value(
                _denom_except_key,
                f"Denominator Exceptions {suffix}" if suffix else "Denominator Exceptions",
            )

            if base != "Initial Population" and not ip_actual:
                actual_val = False
            elif base not in ("Initial Population", "Denominator") and not denom_actual:
                actual_val = False
            elif base == "Numerator" and (denom_excl_actual or denom_except_actual):
                # Gate numerator only when ALL denominator encounters are
                # excluded or excepted. For multi-encounter patients some
                # encounters may be excluded while others legitimately
                # satisfy the numerator.
                # Exception: if the patient is also in Numerator Exclusion,
                # the SQL legitimately places them in both Numerator AND
                # Denominator Exclusion (e.g. CMS871: hyperglycemic event +
                # comfort care). In that case keep the SQL result as-is.
                numer_excl_key = f"Numerator Exclusion {suffix}" if suffix else "Numerator Exclusion"
                numer_excl_actual = _get_or_value(
                    numer_excl_key,
                    f"Numerator Exclusions {suffix}" if suffix else "Numerator Exclusions",
                )
                if not numer_excl_actual:
                    denom_cnt = _get_count(_denom_key)
                    excl_cnt = _get_count(
                        _denom_excl_key,
                        f"Denominator Exclusions {suffix}" if suffix else "Denominator Exclusions",
                    )
                    except_cnt = _get_count(
                        _denom_except_key,
                        f"Denominator Exceptions {suffix}" if suffix else "Denominator Exceptions",
                    )
                    if denom_cnt > 0 and excl_cnt + except_cnt >= denom_cnt:
                        actual_val = False
            elif base in ("Numerator Exclusion", "Numerator Exclusions"):
                # Numerator Exclusion only applies to patients IN the
                # Numerator.  Look up the already-gated Numerator value.
                numer_key = f"Numerator {suffix}" if suffix else "Numerator"
                gated_numer = gated_values.get(numer_key)
                if gated_numer is None:
                    gated_numer = gated_values.get("Numerator")
                if not gated_numer:
                    actual_val = False

            gated_values[def_name] = actual_val

            # Expected values from test_loader use singular FHIR names;
            # config may use plural CQL names. Try both variants.
            expected_val = (
                expected.get(def_name)
                if expected.get(def_name) is not None
                else expected.get(def_name + "s")
                if expected.get(def_name + "s") is not None
                else expected.get(def_name.rstrip("s"))
            )

            if expected_val is not None and actual_val != expected_val:
                patient_matches = False
                mismatches[def_name] = {
                    "actual": actual_val,
                    "expected": expected_val,
                }

        if patient_matches:
            matching += 1
        else:
            mismatched.append({
                "patient_id": patient_id,
                "mismatches": mismatches,
            })

    total = len(expected_lookup)
    accuracy = (matching / total * 100) if total > 0 else 0

    return ComparisonResult(
        total_patients=total,
        matching_patients=matching,
        mismatched_patients=mismatched,
        accuracy_pct=accuracy,
    )


def _normalize_population_definitions(
    pop_defs: List[str], actual_defs: set
) -> tuple:
    """
    Normalize population definition names to match actual CQL definition names.

    MeasureReport codes use singular ("Denominator Exclusion") but CQL
    definitions often use plural ("Denominator Exclusions"). This function
    cross-references against the actual library definitions.

    For multi-group measures, CQL definitions are numbered (e.g.,
    "Denominator 1", "Denominator 2"). We detect these and include all
    numbered variants, mapping them back to the generic name for comparison.

    Numbered expected names (e.g. "Initial Population 1") that don't match
    a numbered CQL definition are mapped to the shared unnumbered CQL
    definition (e.g. "Initial Population") if it exists.

    Returns:
        (normalized_list, name_map) where name_map maps original -> CQL name
        For multi-group, name_map maps generic name -> list of numbered CQL names.
    """
    import re
    normalized = []
    name_map = {}

    for pd in pop_defs:
        if pd in actual_defs:
            normalized.append(pd)
            name_map[pd] = pd
        elif pd + "s" in actual_defs:
            normalized.append(pd + "s")
            name_map[pd] = pd + "s"
        elif pd.rstrip("s") in actual_defs:
            normalized.append(pd.rstrip("s"))
            name_map[pd] = pd.rstrip("s")
        else:
            # For numbered expected names (e.g. "Initial Population 1",
            # "Denominator Exception 1"), try variant forms:
            #   - unnumbered base as a shared CQL definition
            #   - numbered base with plural suffix ("Denominator Exceptions 1")
            base_match = re.match(r'^(.+?)\s+(\d+)$', pd)
            if base_match:
                base = base_match.group(1)
                num = base_match.group(2)
                # Try unnumbered shared definition
                for candidate in [base, base + "s", base.rstrip("s")]:
                    if candidate in actual_defs:
                        normalized.append(candidate)
                        name_map[pd] = candidate
                        break
                if pd in name_map:
                    continue
                # Try numbered with plural/singular variants
                for candidate in [base + "s", base.rstrip("s"), base]:
                    numbered_candidate = f"{candidate} {num}"
                    if numbered_candidate in actual_defs:
                        normalized.append(numbered_candidate)
                        name_map[pd] = numbered_candidate
                        break
                if pd in name_map:
                    continue

            # Check for numbered variants (multi-group measures):
            # e.g., "Denominator" -> "Denominator 1", "Denominator 2"
            # Also check with plural suffix
            numbered = []
            for candidate in [pd, pd + "s", pd.rstrip("s")]:
                for i in range(1, 10):
                    variant = f"{candidate} {i}"
                    if variant in actual_defs:
                        numbered.append(variant)
            if numbered:
                for n in numbered:
                    normalized.append(n)
                name_map[pd] = numbered  # list signals multi-group

    return normalized, name_map
