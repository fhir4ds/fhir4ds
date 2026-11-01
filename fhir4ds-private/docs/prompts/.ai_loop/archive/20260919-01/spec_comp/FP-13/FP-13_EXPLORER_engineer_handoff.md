# FP-13 EXPLORER Engineer Handoff (2026-08-17, iteration 1)

## Triage
| Issue | Category | Severity | Terminal |
|---|---|---|---|
| QA-001 quantity `~` least-precision tolerance | SPEC_VIOLATION | HIGH | RESOLVED |
| QA-002 JSON-integer `~` binary64 coercion | SPEC_VIOLATION | HIGH | RESOLVED |
| QA-003 `1 'cm' ~ 1 's'` empty | doctrine pin | LOW | INTENDED |

## Fixes (both native, evaluator.cpp; extension rebuilt + redeployed to repo
bundle, site-packages, /tmp/duckdb_cpp_ext, ~/.duckdb caches cleared)

1. **QA-001** — New `leastPrecisionDecimalPlaces(const FPValue&)` (routes
   through the existing trailing-zero-stripping `decimalPlacesFromNumberText`)
   replaces `countDecimalPlaces` at BOTH `quantityEquivalentState` tolerance
   sites (year↔month months path and unanchored-seconds path). §6.1.2: the
   tolerance half-width uses the precision of the LEAST precise operand with
   trailing zeros ignored (`1.0 'g'` → precision 0 → half-width 0.5), matching
   the Python fallback `decimal_places` (rstrip '0').
   `countDecimalPlaces` itself is untouched — lowBoundary/highBoundary
   legitimately preserve trailing zeros.
2. **QA-002** — `jsonNumbersEquivalent` now compares exactly via
   `yyjson_get_sint` when both JSON numbers are integers (cmp_prec is 0
   there, rounding is the identity); the binary64
   `round(double*scale)` path remains for real-valued pairs. Fixes
   `9007199254740992 ~ 9007199254740993` → false natively.
3. Test maintenance: stale NBSP expectation in
   `test_equality_parity.py::test_string_equivalence_normalizes_case_and_whitespace_without_collapse`
   updated to False (FP-13 HISTORIAN whitespace lexical-category doctrine —
   NBSP is not normalized; both engines agreed, only the test was stale).

## Regression coverage
- `test_comparison_parity.py::test_quantity_equivalence_least_precision_parity_fp13_explorer`
  (16 dual-path cases: same-unit/cross-unit tolerance boundaries, where/iif
  chaining, `=` unaffected).
- `test_equality_parity.py` large-JSON-numbers test now guards QA-002
  (annotated in-source).

## Validation (Recovery Gate)
- EXPLORER probe: 0 parity diffs / 0 spec failures (133 cases).
- `test_equality_parity.py + test_comparison_parity.py`: 91 passed.
- Full fhirpath pytest tree: 1874 passed.
- Conformance: **2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47)** —
  baseline held.

No new issues discovered during remediation. All issues terminal.
