# Architect Handoff — CQL-08 SKEPTIC (iteration 1, 2026-08-20)

## Golden Standard invariants applied
1. Translator layering: nullological semantics fixed at the AST/translator
   layer, not by SQL string patching (no SQLRaw/to_sql introduced).
2. No silent fallbacks: order-dependent DuckDB COALESCE binder acceptance
   replaced with a typed, order-independent TranslationError.
3. Dual-engine lockstep: public `Coalesce` is served by the Python UDF on
   both native-cpp and python-only connections (native registers only
   `logicalCoalesce`), so a single-source fix satisfies parity; verified
   py==cpp on every probe.
4. General, not specific: the type-family guard classifies any static
   String/Integer/Long/Decimal mix; unknown/dynamic-typed operands pass
   through untouched.

## Audit findings
- No new architectural drift. QA-001/QA-002 fixes are minimal-footprint and
  spec-grounded (CQL 1.5 §Coalesce).
- Minor observation (no action): the type-family sets are inline locals in
  `_translate_function_ref`; consistent with neighboring inline sets in the
  same file, so not elevated to shared constants.
- QA quality gate: PASS — QA probed dual-path expression-level matrices,
  prefix/postfix/infix forms, FHIR-data population SQL, where-clauses, the
  CQL-04 expression-vs-population boundary, and error containment. No veto.

## Empirical validation
- Fresh full conformance: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held. Focused nullological parity 13/13. Full
  fhir4ds/cql pytest running in background (log retained); no failures
  observed in completed portion at handoff time.

## Summary (compression)
QA found 2 real spec violations (Coalesce arity cap HIGH; order-dependent
String/numeric type mixing MEDIUM) plus 2 LOW INTENDED lenient behaviors.
Engineering removed the arity cap in translator + public UDF and added a
uniform static type-family guard; stale arity pins updated and a variadic
regression test added; conformance gate held 2832/2832.

## Recommended fix order
None pending. Chunk CQL-08 (SKEPTIC launch) is CLEAN at iteration 1.

## Out-of-scope observation (not CQL-08)
Two PRE-EXISTING failures in the shared working tree, reproduced with the CQL-08 edits
removed (git-checkout of the two touched source files), so not caused by this launch:
- test_structural_type_parity.py::test_cql_structural_quantity_assertion_preserves_fhir_quantity_comparison
  (cpp "38 'weeks'" vs py "38 weeks" — CQL-06 QuantityToString territory)
- test_cql01_primitive_types.py::TestCanConvert::test_can_convert_false
  (CanConvert(1.5, Integer) returns True — CQL-01 territory)
Also test_primitive_parity.py::test_cql_primitive_conversion_translation_uses_spec_boundaries
  (a ToInteger/convert-to-Integer boundary returns 1 instead of None — CQL-01 territory, same
  family as the CanConvert(1.5, Integer) failure; no Coalesce anywhere in these tests).
Left for the owning chunk's next personality launch; conformance suite unaffected (2832/2832).
