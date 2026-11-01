# Engineer Handoff — FP-06 EXPLORER (launch 3), iteration 1 (2026-08-17)

## Triage

| Issue | Category | Severity | Terminal state |
|---|---|---|---|
| QA-001 iif criterion defineVariable scope (fallback) | SPEC_VIOLATION | MEDIUM | RESOLVED |
| QA-002 JSON-null root resource parity | DATA_HANDLING | LOW | DEFERRED |

## QA-001 fix

- Root cause: `iif_macro` in `fhir4ds/fhirpath/engine/invocations/misc.py`
  (FP-06 HISTORIAN fix) snapshotted `ctx['vars']` before criterion evaluation
  and restored it after the criterion, so criterion-defined variables were
  invisible in the taken branch and afterwards. Native `fn_iif`
  (extensions/fhirpath/src/fhirpath/evaluator.cpp:7169) evaluates the
  criterion in the expression's main scope; only the branch snapshots are
  restored, so criterion vars persist for the remainder of the expression
  (verified natively for true, false, and empty criteria) — matching
  §5.2.9 defineVariable ("available for the remainder of the expression").
- Fix: criterion now evaluated in the caller's scope (no restore); each
  branch snapshots post-criterion vars, clears `_chain_defined_vars`, and
  restores the snapshot after (branch vars remain branch-scoped, preserving
  the HISTORIAN regression expectations).
- Python-side only; native already correct; NO extension rebuild.
- Regression coverage: 10 new dual-path cases appended to
  `test_conversion_parity.py::test_integer_conversion_trailing_newline_and_iif_scope_parity_fp06_historian`
  (criterion-var visibility in taken branch, persistence after the iif for
  true/false/empty criteria, branch-scoped non-leak, pre-iif vars in both
  branches).

## QA-002 (deferred)

Documented in evolution.json; no code change. Recommendation: a future
root-context null-semantics decision (core `arraify(None)` vs wrapper JSON
null mapping) — both partial fixes leave a `type().name` divergence.

## Validation

- `test_conversion_parity.py`: 40/40 pass.
- iif/variable/scope/filter-projection FHIRPath tests: 76/76 pass.
- EXPLORER probe: 100/100 (was 98/100 with 2 parity failures pre-fix).
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, DQM 47/47,
  OVERALL 2832/2832 — baseline held.
