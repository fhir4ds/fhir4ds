# Engineer Handoff — FP-07 (iteration 1, 2026-08-17)

## Triage
| Issue | Severity | Category | Triage |
|---|---|---|---|
| QA-001 lenient `toDate()` on dateTime-shaped strings | LOW | SHARED_CONVENTION | INTENDED — no fix |
| QA-002 `'5L'` Long-suffix `toDecimal()` convention | LOW | SHARED_CONVENTION | INTENDED — no fix |
| QA-003 `'5L\n'.toDecimal()` fallback UDF crash | MEDIUM | SPEC_VIOLATION + parity | RESOLVED |

## QA-003 remediation (root cause, fix, validation)
- Reproducer: forced-fallback connection,
  `SELECT fhirpath('{"resourceType":"Patient","id":"p1"}', "'5L\n'.toDecimal()")`
  raised `decimal.InvalidOperation: ConversionSyntax` from
  `misc.py:507` (`Decimal(value[:-1])` on `'5L'`), surfacing as a DuckDB
  `InvalidInputException`. Native returns `[]` (empty) and
  `convertsToDecimal` → `false` (both `is_valid=True`).
- Root cause: `longDecimalStringRegex` (misc.py:24) still ended in `$`,
  which matches before one trailing newline; the match sent `'5L\n'` into
  the Long-suffix branch whose `value[:-1]` strip produced `'5L'` for
  `Decimal()`. Exactly the sibling FP-06 HISTORIAN pre-flagged for the
  FP-07 chunk owner ("longDecimalStringRegex still ends in `$`... should
  pre-harden it to `\Z`").
- Spec: FHIRPath N1 §5.5.6 — String convertible to Decimal must match
  `(\+|-)?\d+(\.\d+)?`; `'5L\n'` does not; result must be empty.
- Fix (Python-only, one line + comment): `$` → `\Z` anchor in
  `longDecimalStringRegex` (`fhir4ds/fhirpath/engine/invocations/misc.py`).
  No extension rebuild needed (native already correct).
- Regression: 6 cases appended to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py::
  test_integer_conversion_trailing_newline_and_iif_scope_parity_fp06_historian`
  (`'5L\n'` empty/false, `'-5L\n'` empty, valid `'5L'` → `5.0`/true,
  `'5.5L'` empty) — native-vs-fallback asserted for each.
- Validation: targeted parity test 1/1 pass; full
  `test_conversion_parity.py` + `fhir4ds/fhirpath/tests/unit` → 218 passed;
  full conformance post-fix: ViewDef 144/144, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, OVERALL 2832/2832 (baseline held; log:
  `.temp/qa/fp07_skeptic_2026_08_17/validation_summary_post_fix.log`).

## Handoff
All issues terminal (2 INTENDED, 1 RESOLVED). Zero non-terminal
CRITICAL/HIGH/MEDIUM. Proceed to ARCHITECT; clean exit eligible at
iteration 1.
