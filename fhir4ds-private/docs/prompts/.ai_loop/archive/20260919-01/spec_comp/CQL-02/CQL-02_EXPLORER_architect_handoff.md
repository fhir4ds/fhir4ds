# Architect Handoff — CQL-02 EXPLORER (iteration 1, 2026-08-19)

## Golden standard (scoped to this launch's changes)
Grounded in the existing CQL-02 golden standard (spec_comp/CQL-02/golden_standard_cql02_skeptic.md)
plus chunk invariants: (1) clinical `=`/`~` semantics come from the CQL 1.5 Equal/Equivalent
sections, not per-operator intuition; (2) null elements in structured clinical values are "no
value" — absent and explicit null must be indistinguishable downstream; (3) equivalence folding
happens at the translator layer and must be shared by native and Python backends; (4) no
silent fallbacks — unresolvable operands defer to runtime rather than guessing; (5) list-level
and Concept-level equivalence are DIFFERENT semantics (ordered element-wise vs intersection).

## Audit of this launch's changes (fhir4ds/cql/translator/expressions/_operators.py)
- `_normalize_static_clinical_code` null-elision: invariant-consistent (single normalization
  choke point; value-vs-null defers to the existing key-set-mismatch SQLNull branch rather
  than inventing a new default). No silent fallback introduced.
- `_code_equivalence_key`: spec-cited, null-aware, shared by the static fold and the closure
  path; preserves "null is not equivalent to ''". Replaces the prior case-only key without
  changing its case/whitespace normalization. The now-dead local
  `_cql_string_equivalence_key` closure was removed (logic lives in the shared method).
- `_static_code_list`: deliberately does NOT resolve bare Concept values — this preserves the
  list-vs-intersection semantic split (verified: `.codes ~` order/length-sensitive, Concept
  `~` order-insensitive). Resolution failures return None and defer to runtime — no guessing.
- No hardcoding, no SQLRaw introduced, translator layering respected, both backends share
  the translator change (parity tests cover both).

## QA audit (EXPLORER)
Sufficient: 50-case dual-backend boundary probe (whitespace/unicode casefold, null-vs-absent
matrices, list ops, Coalesce/case/First, ToConcept roundtrips, pathological systems) plus
targeted follow-ups that separated harness artifacts (fhirpath registration) from real bugs.
No veto; RETRY_QA remains false.

## Issue summary
2 issues, both HIGH SPEC_VIOLATION, both RESOLVED and verified (reproducers pass; full
conformance gate 2832/2832; clinical parity file 24/24 after cleanup re-run). Zero open
CRITICAL/HIGH/MEDIUM issues.

## Structural health
No new architecture drift. Recommended follow-up (out of chunk, unchanged): generic scalar
literal define aliases share the CTE shape mismatch noted by SKEPTIC (CQL-01 scope);
codesystem resolver included-library lookup remains the known LOW gap.

## Handoff compression
QA found 2 HIGH translator-layer spec violations shared by both backends: absent-vs-null
Code system asymmetry in `=`/`~`, and `.codes` List<Code> equivalence falling through to
byte-wise CQLListEquivalentEq. Engineer fixed both at shared choke points
(`_normalize_static_clinical_code`, new `_code_equivalence_key`, new `_static_code_list`
fold in `_translate_equivalence_op`) with dual-backend regression tests; conformance
baseline held at 2832/2832.
