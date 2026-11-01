# Engineer Handoff — FP-06 HISTORIAN (iteration 1, 2026-08-17)

## Triage
| Issue | Category | Severity | Action |
|---|---|---|---|
| QA-001 trailing-newline toInteger grammar | PARITY/SPEC_VIOLATION | MEDIUM | Fixed |
| QA-002 defineVariable leak from iif branch | PARITY | MEDIUM | Fixed |
| QA-003 out-of-range Integer literal doctrine | SPEC_NOTE | LOW | INTENDED (no change) |

## Fixes (both Python-fallback-only; native already spec-correct, no rebuild)

### QA-001 — `fhir4ds/fhirpath/engine/invocations/misc.py`
`intRegex` was `^[+-]?[0-9]+$`. Python `re` `$` also matches immediately
before a single trailing newline, so `'1\n'.toInteger()` → `1` and
`'1\n'.convertsToInteger()` → true in the fallback while the native evaluator
(and the exact `(\+|-)?\d+` grammar of FHIRPath §5.5.3) reject them. Fix:
anchor with `\Z`. `'1\n\n'`, `'\n1'`, `'1\t'` were already rejected by both
engines; `-1\n` variant now also rejected. Same bug class lineage as the
FP-07 EXPLORER Unicode-`\d` fix (comment cross-references it).

### QA-002 — `fhir4ds/fhirpath/engine/invocations/misc.py::iif_macro`
The fallback's `iif_macro` evaluated criterion/branch lambdas without scope
save/restore, so `defineVariable` inside an iif branch leaked into subsequent
expressions (`iif(true, defineVariable('dv', 9).select(1), 2).select(%dv)` →
`9` in fallback vs empty natively). Fix mirrors native `fn_iif`
(`extensions/fhirpath/src/fhirpath/evaluator.cpp:7169`): vars restored after
criterion evaluation; each branch evaluated with a cleared
`_chain_defined_vars_` and restored vars/chain. Variables remain visible
inside their defining branch and variables defined before the iif remain
visible in criterion and branches (regression-tested).

## Regression coverage
`test_integer_conversion_trailing_newline_and_iif_scope_parity_fp06_historian`
in `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
(13 cases, native vs forced fallback, exact expected values).

## Validation (Recovery Gate)
- Probe re-run: 123/123 PASS (5 stale probe expectations corrected to the
  spec-verified values; both engines agree on all).
- `pytest fhir4ds/fhirpath`: 1739 passed.
- Full conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held. Summary:
  `.temp/qa/fp06_historian_2026_08_17/validation_summary.log`.

## New issues discovered
None. No native/C++ changes; bundled extension untouched.
