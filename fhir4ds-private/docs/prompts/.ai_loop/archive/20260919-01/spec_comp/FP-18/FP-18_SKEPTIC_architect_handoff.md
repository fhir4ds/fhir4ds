# Architect Handoff — FP-18 SKEPTIC iteration 1 (2026-08-18)

## Golden Standard invariants applied (scoped audit of this iteration's delta)
1. Dual-engine lockstep: every FHIRPath semantic change lands in Python core,
   Python fallback, and native evaluator.cpp, with a parity test.
2. Error-message contract coupling: new execution-type-error messages must be
   added to `_is_valid_empty_result_error` (udf.py) and stay consistent with
   native `FhirpathIsValid` acceptance semantics.
3. Native semantic changes require rebuild + redeploy of the bundled
   `fhirpath.duckdb_extension`.
4. Strict core raises typed FHIRPathError; DuckDB wrappers stay row-resilient.

## Audit findings on the delta
- **PASS (lockstep)**: exact div/mod implemented in math.py (Python) and
  evaluator.cpp (native, int64 path + __int128 decimal-mod path); parity tests
  added (`test_fp18_math_operators.py::TestDualEngineParity`, 57 tests total).
  Extension rebuilt twice and redeployed to the repo bundle
  (`fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`).
- **CAUGHT DURING AUDIT (fixed inline as engineer follow-up, would otherwise
  be a contract violation)**: the new div/mod Quantity-operand and temporal
  unit messages were NOT in `_is_valid_empty_result_error`, so
  `fhirpath_is_valid('1 'cm' div 2')` returned False while the native engine
  returns empty/valid — exactly the recurring "error-message contract"
  family. Fixed in udf.py (div/mod "Cannot" family + the three "For date/
  time arithmetic," prefixes) and `_evaluate_literal_temporal_arithmetic` now
  converts `FP_TimeBase.plus` ValueError to FHIRPathError instead of leaking
  it. Contract tests added (`TestIsValidContract`).
- **CAUGHT AND ALIGNED**: `-9223372036854775808L` — native special-cases
  unary minus on `9223372036854775808L` to LLONG_MIN; the initial Python
  Long-range guard rejected it. Relaxed to allow exactly 2^63 (only
  meaningful under unary minus). int64 div overflow (LLONG_MIN div -1)
  normalized to empty on BOTH engines (native `return {}`, Python `[]`),
  avoiding a new coupled error message entirely.
- **Architecture note (no action)**: `_evaluate_literal_temporal_arithmetic`
  in udf.py duplicates engine temporal arithmetic via regex, bypassing
  engine/invocations layering (pre-existing). It is a validation fast path;
  its ValueError leak was fixed, but the duplication remains a drift
  candidate for a future chunk.

## Verification
- `fhir4ds/fhirpath/tests/unit/test_fp18_math_operators.py`: 57 passed
  (values, ranges, error contract, is_valid contract, dual-engine parity).
- Full package pytest + conformance master gate: see GLOBAL_KNOWLEDGE stats
  row (unit suites green; full-package pytest: 9002 passed, 183 pre-existing integration failures — see Addendum; conformance 2832/2832).
- RETRY_QA not required: reproducer tests pass, no regression, issues
  terminal (5 RESOLVED, 2 DEFERRED with rationale).

## Addendum (post-audit environmental finding — QA-007, DEFERRED HIGH)
Full-package pytest (9002 passed / 183 failed) surfaced integration-parity
failures in FP-02/FP-11/FP-12/FP-15 suites. Verified pre-existing via binary
A/B: the pre-FP-18 site-packages binary (Aug 18 14:05) fails them with
identical counts, and the ARCHIVE_LOG-described FP-11 helpers
(`expandScientificToFixed`/`shortestRoundTripText`) are absent from
evaluator.cpp at HEAD and in the working tree — the campaign tree carries a
source/binary/test three-way drift that predates this launch. NOT caused by
FP-18's delta (whose own parity/contract tests are 57/57 green) and NOT a
PROC_VALIDATION regression (conformance 2832/2832 before and after).
Recommend the outer orchestrator schedule a reconciliation chunk before the
next C++-touching chunk, since any rebuild re-flows this drift into shipped
binaries.
