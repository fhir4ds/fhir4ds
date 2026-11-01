# Engineer Handoff — CQL-02 EXPLORER (iteration 1, 2026-08-19)

## Triage
| Issue | Category | Triage | Terminal |
|---|---|---|---|
| QA-001 absent-vs-null system asymmetry (=/~) | SPEC_VIOLATION | CONFIRMED (reproduced both backends) | RESOLVED |
| QA-002 `.codes` List<Code> equivalence case-sensitive | SPEC_VIOLATION | CONFIRMED (reproduced both backends) | RESOLVED |

## Fixes (all in fhir4ds/cql/translator/expressions/_operators.py; translator layer, shared by native + Python backends)
- QA-001:
  - `_normalize_static_clinical_code` no longer materializes null-valued elements
    (absent system and `system: null` now fold identically; value-vs-null falls into
    the existing key-set-mismatch `SQLNull` branch — spec: tuple equality is a
    conjunction of equality comparisons, null element → null).
  - New shared `_code_equivalence_key`: null code/system map to a `None` key
    (null ~ null → true; null vs '' → false, per "null is not equivalent to the
    empty string"); strings keep casefold + whitespace normalization.
- QA-002:
  - New `_static_code_list` resolves statically-known List<Code> operands (Code list
    literals; `.codes` on static Concept values incl. ToConcept(...) and define
    aliases). `_translate_equivalence_op` folds `~`/`!~` over such operands to
    element-wise Code equivalence with length check (CQL list equivalence).
    Bare Concept operands are deliberately excluded so Concept `~` retains
    intersection (order-insensitive) semantics.

## Verification
- Reproducers pass: .temp/qa/cql02_explorer_followup1.py all spec-correct on both
  backends (incl. new correct `None` for value-vs-null `=`).
- Guard semantics verified: `.codes ~` stays order/length-sensitive; Concept `~`
  stays intersection-based; `!~` negation; `'' ~ null` stays false.
- New dual-backend regression tests:
  test_cql02_explorer_absent_vs_null_system_equivalence_and_equality,
  test_cql02_explorer_concept_codes_list_equivalence_case_insensitive
  (fhir4ds/cql/duckdb/tests/integration/test_clinical_type_parity.py; file now 24/24).
- Full conformance gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 — baseline holds, no regressions.

## No new issues discovered during remediation.
