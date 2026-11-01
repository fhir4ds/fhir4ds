# Architect Handoff — CQL-06 HISTORIAN (iteration 1, 2026-08-20)

## Audit scope
The iteration's delta: `QuantityToString` calendar-keyword rendering fix in `fhir4ds/cql/duckdb/macros/conversion.py` + regression test.

## Golden-standard check (invariants evaluated)
1. **Data-driven model knowledge**: PASS — the calendar-keyword set is imported from the existing `_CQL_CALENDAR_DURATION_UNITS` registry (`udf/quantity.py`), not duplicated or hardcoded in the macro.
2. **Layering**: PASS — fix is in the macro layer, which is the single serving path for `ToString`/`QuantityToString` on BOTH the Python-supplement and native-supplemented backends; no translator or evaluator boundary was crossed; no C++ mirror required (verified empirically that the Python UDF/macro serves the surface when the extension is loaded).
3. **No silent fallbacks / no test hacks**: PASS — pure CASE branch on the registry; no fixture-specific special cases.
4. **Spec grounding**: PASS — fix cites the verbatim Appendix B §ToString sentence and Table 9-G format `(-)?#0.0# (('<unit>')|(<unit>))`.
5. **Dual-backend lockstep**: PASS — shared macro; dual-backend assertions in the regression test.

## QA quality gate
HISTORIAN QA was sufficient: live spec verification, re-verification of the prior SKEPTIC fix on both backends, ~45 fresh dual-backend probes, 30-case end-to-end translate→SQL→DuckDB matrix, plus explicit non-issue pinning (Long `L` suffix). No veto. RETRY_QA = false.

## Empirical validation
- `test_conversion_check_parity.py` 9/9; adjacent conversion/macro tests 79/79.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47 — **2832/2832, baseline held**.

## State hygiene
- QA-001 RESOLVED with reproducer, root cause, and verification evidence; tombstoned in `evolution.json` and archived to `ARCHIVE_LOG.md` / `spec_comp/CQL-06/CQL-06_HISTORIAN_*`.
- Zero non-terminal CRITICAL/HIGH/MEDIUM issues remain; iteration 1 ≥ min_iterations 1 → **CLEAN exit**.

## Handoff compression
SKEPTIC had fixed ToQuantity's bare calendar-duration keyword parsing; HISTORIAN found and fixed the inverse rendering divergence — `ToString` of calendar-duration quantities must emit a bare keyword (`4 day`), not a quoted UCUM form — in the shared `QuantityToString` macro using the data-driven calendar registry, with dual-backend regression tests and the 2832/2832 baseline intact. Two NOT-A-BUG pins added (Long `L` suffix; native `to_quantity` shadowed by Python UDF).
