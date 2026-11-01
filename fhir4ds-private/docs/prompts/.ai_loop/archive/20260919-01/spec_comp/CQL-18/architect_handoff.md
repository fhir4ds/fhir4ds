# Architect Handoff — CQL-18 re-launch (SKEPTIC), iteration 1

Scope audited: this launch's delta — translator/expressions/_utils.py (new
`_promote_fhirpath_text_list`), _operators.py (promotion in 6 list-macro
helpers + Equivalent dispatch + Contains fallthrough guard), _lists.py (Exists
fhirpath_bool branch, Distinct fallback promotion), _functions.py (flatten
pre-translate, IndexOf arg promotion), registry registration in
expressions/__init__.py, plus the new population-SQL regression test.

## Golden-standard invariants checked
1. Translator layering: all changes are inside the translator expression
   layer; no SQLRaw, no to_sql mid-pipeline, no cross-boundary SQL strings.
   PASS.
2. Dual-engine lockstep: the fix is engine-neutral (SQL shape), verified by
   the new test asserting py-only == native-cpp results, and by probe4
   (17/17 identical). No native rebuild required; extension binaries
   unchanged and md5-matched:
   - cql.duckdb_extension 3e7d4167143e01907fdd8561db43b7d7 (repo bundle ==
     ~/.local site-packages)
   - fhirpath.duckdb_extension 57d0634b6ee6eddee9fc06a1355bef5a (repo ==
     site-packages)
3. Generalizability: the promotion is a single shape-based rewrite
   (2-arg fhirpath_text → from_json list projection), not fixture-specific;
   it mirrors the pre-existing `in`-operator repair and follows it
   uniformly. PASS.
4. No silent fallbacks added: the Contains fallthrough change REPLACES an
   incorrect substring fallback with spec semantics rather than adding a new
   fallback; failure modes still surface as DuckDB errors. PASS.
5. Spec grounding: every behavioral change cites CQL 1.5 Appendix B §10.x
   (fetched live this session); fixture-vs-prose conflicts adjudicated in
   favor of official fixtures per GLOBAL_RULES, and documented in
   fhir4ds/cql/AGENTS.md.

## Validation (final tree state)
- Master gate: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM (QI Core 2025) 47/47 — OVERALL 2832/2832, no regressions, no DQM
  measure errors (no REV-009 retry needed).
- Focused: test_list_part1_parity.py 10/10 (incl. new dynamic-FHIR test),
  test_list_part2_parity.py 12/12, test_v2_expressions.py 169/169.

## QA quality gate
QA (SKEPTIC) was effective: found a 6-issue cluster the three prior CQL-18
personalities missed because they only tested static-literal lists; this
launch tested end-to-end retrieved multi-valued FHIR fields as the chunk
mandate requires. No RETRY_QA.

## Findings / follow-ups (logged, non-blocking)
- Numeric/temporal dynamic list elements go through the VARCHAR coercion of
  `from_json(..., '["VARCHAR"]')` (same shape as the pre-existing `in`
  repair). String surfaces verified; numeric equality across int/decimal
  dynamic list elements inherits the same limitation and belongs in a future
  list-chunk follow-up if clinical use cases surface it.
- Architectural observation: the scalar-vs-multi-valued property distinction
  is not statically modeled in the translator (fhirpath_text truncation is
  the symptom). A longer-term fix is a multiplicity-aware property typing
  layer; the centralized promotion helper is the correct interim seam.
