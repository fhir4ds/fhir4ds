# Engineer Handoff — FP-05 SKEPTIC, iteration 1 (2026-08-17)

## Triage

| Issue | Category | Severity | Action |
|---|---|---|---|
| QA-001 | API_CONSISTENCY (is_valid doctrine) | MEDIUM | CONFIRMED (reproduced on both surfaces) -> fixed |

## QA-001 fix (RESOLVED)

**Root cause**: `fhirpath_is_valid` classifies statically-known wrong-typed §5.3
arguments (`skip('x')`, `take(true)`, `[1.5]`, `'abc'['x']`) as invalid on both
surfaces because those execution-error message forms were never added to the
accepted-message lists, unlike their doctrinal siblings (`'a' - 'b'`, unary
+/-, Boolean ordering — all True).

**Fix (surgical, both classifiers)**:
- `fhir4ds/fhirpath/duckdb/udf.py::_is_valid_empty_result_error`: accept
  `Expected integer, got: ` and `Indexer requires an integer index`.
- `extensions/fhirpath/src/fhirpath_extension.cpp::FhirpathIsValidFunction`:
  accept `Indexer requires an integer index`, `skip() requires an integer
  argument`, `take() requires an integer argument`.
- Singleton/multi-item variants (`requires a singleton integer index`,
  `Unexpected collection[...]; expected singleton of type Integer`,
  `requires a single integer ...`) remain invalid in both — the FP-02
  singleton-violation doctrine is preserved.
- Native extension rebuilt (`make fhirpath_loadable_extension`) and redeployed
  to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` and
  `~/.local/lib/python3.10/site-packages/fhir4ds/.../extensions/`.

**Spec grounding**: FHIRPath N1 §5.3 declares `num: Integer` / `index:
Integer`; the mismatch signals at evaluation on otherwise-valid grammar —
the same execution-type-error class the is_valid doctrine already accepts.

## Validation (Recovery Gate)

- Reproducer battery now True on both surfaces; singleton forms still False.
- Regression: `test_subsetting_argument_type_error_validity_classification_fp05_skeptic`
  (15 parametrized cases) in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py` — 15 passed.
- Full fhirpath pytest: 1738 passed.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 — baseline holds.
- FP-05 dual-path probes (67 + 38 cases) re-run against the rebuilt native:
  0 parity diffs.

No new issues discovered during remediation.
