# FP-19 Engineer Handoff — EXPLORER iteration 1 (2026-08-18)

## QA-001 (HIGH, RESOLVED) — incompatible arithmetic errors must abort parents
- Root cause: `extensions/fhirpath/src/fhirpath/evaluator.cpp` evalBinaryOp
  degraded incompatible-operand arithmetic (`1+'x'`, `1+true`, `1+{}`,
  `'a'-'b'`) to an empty collection, so parents kept evaluating
  (`(1+'x') | 99` -> ['99'] natively vs [] on fallback; errored aggregate
  `.count()` -> ['0'] vs []).
- Fix: throw `FHIRPathSpecError("Incompatible operands for arithmetic
  operator 'op'")` (N1 §6.6 "evaluation ... will end and signal an error");
  message added to native `FhirpathIsValidFunction` acceptance list (same
  execution-type-error class as the fallback's accepted "Cannot [..]").
- is_valid parity: `fhirpath_is_valid('1+\'x\'')` true on both engines.

## QA-002 (MEDIUM, RESOLVED) — mixed-unit quantity sum unit
- Root cause: different-unit +/- branch returned the canonical base unit
  (`3.5 'wk' + 2 'd'` -> `2289600 's'`).
- Fix: choose the most granular input unit (smaller |factor-to-base|; ties
  prefer the canonical/base-form operand), mirroring the fallback's
  `_quantity_add_or_sub` (N1 §6.6.3). `3 'm' + 3 'cm'` -> `303 'cm'`,
  `3.5 'wk' ± 2 'd'` -> `26.5/22.5 'd'` on BOTH engines now.

## Build/deploy
- `make release` in extensions/fhirpath; binary deployed to repo bundle
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` and user
  site-packages. ucum_units.hpp and the CQL extension untouched.

## QA-003 (MEDIUM, DEFERRED) — pre-existing native gaps (out of chunk)
- Verified against the git-HEAD binary: `1 'kN' = 1000 'N'` -> [] and
  `2 + 2 '1'` -> [] natively while the fallback returns true / `4 '1'`.
  86 integration-parity failures pre-date this launch (84 in
  test_arithmetic_parity.py, 1 each in environment_type/existence parity).
- AGENTS.md FP-11 documents a native `FhirpathDerivedUnitTable()` that does
  NOT exist in the current evaluator.cpp (no commit ever added it) — the
  institutional memory overstates native coverage.
- Deferred to the quantity-conversion chunk family (needs curated native
  derived-unit table + compound-unit reduction + number±quantity branch +
  coordinated extension rebuilds).

## Validation
- Master gate: run_all.py 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.
- pytest fhir4ds/fhirpath/tests: 253 passed.
- pytest fhir4ds/fhirpath/duckdb/tests/unit: 993 passed.
- test_aggregate_lexical_parity.py: 10 passed (incl. 2 new FP-19 EXPLORER
  regressions).
- test_operator_parity.py: 60 passed.

## Files changed
- extensions/fhirpath/src/fhirpath/evaluator.cpp (2 fixes)
- extensions/fhirpath/src/fhirpath_extension.cpp (is_valid acceptance)
- extensions/fhirpath/build/** + deployed fhirpath.duckdb_extension (bundle
  + site-packages)
- fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py
  (2 new regression tests)
