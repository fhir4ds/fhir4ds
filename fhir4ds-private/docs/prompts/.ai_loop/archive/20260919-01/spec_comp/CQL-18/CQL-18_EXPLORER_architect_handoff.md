# Architect Handoff — CQL-18 EXPLORER launch, iteration 1

## Structural audit of the FIX pass (translator layer, CQL list operators)

Golden-standard invariants applied (established in prior CQL-18 launches):
1. List-operator semantics live in the Python translator + DuckDB list
   macros; no per-test special cases.
2. `stores_list_value` / `stores_patient_list` are the single discriminators
   for "CTE value column holds a whole per-patient list"; consumers must not
   guess from `List<` typing alone.
3. Typed TranslationError at translate time for statically ill-typed CQL; no
   raw engine exceptions may surface for static errors.

Findings: all five fixes satisfy the invariants.
- QA-001/QA-004 extend the HISTORIAN stored-list mechanism rather than adding
  a parallel one; the new `stores_patient_list` marker flows into the existing
  `stores_list_value` metadata — consistent with invariant 2.
- QA-002 is a dispatch-completeness fix (list-producing SQL recognized by
  `_is_single_list_expr`) plus a general scalar→singleton-list promotion per
  App B list promotion — not a fixture hack.
- QA-003 reuses the contains macro for the singleton overload, matching the
  spec's "synonym for contains" wording. Population Boolean presence-encoding
  (null→false at the define boundary) is documented INTENDED behavior.
- QA-005 is a typed, general static check (String/numeric/Boolean mixing);
  int+decimal mixing correctly still allowed (common Decimal supertype).

No new drift entries. No silent fallbacks introduced. Fix footprint is the
smallest consistent with root-cause repair.

## QA audit (Phase 1 quality)
EXPLORER performed per-define bisected population-SQL probes, multi-patient
correlation checks, and 3-mode parity (python/native/no_python) before the
chained-define crash; coverage of the chunk's operator matrix was thorough
(null-element, null-list, duplicate, tuple, alias-depth, chaining, hetero
literals, multi-patient). RETRY_QA not warranted.

## Empirical validation (this session, fresh)
- Master gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- CQL unit 1612/1612; list part1 parity 18/18.
- Binaries unchanged (Python-only): cql ext md5 3e7d4167143e01907fdd8561db43b7d7,
  fhirpath ext md5 57d0634b6ee6eddee9fc06a1355bef5a.

## Verdict
Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 >= min_iterations 1.
Exit CLEAN; return control to the outer spec-compliance orchestrator.
Recommended next-launch attention (non-blocking): Sum over Integer list
returns Decimal (6.0) — numeric-preservation pass candidate.
