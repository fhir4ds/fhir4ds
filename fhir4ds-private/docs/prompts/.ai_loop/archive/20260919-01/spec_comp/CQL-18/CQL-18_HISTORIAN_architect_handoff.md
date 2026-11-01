# Architect Handoff — CQL-18 re-launch (HISTORIAN), iteration 1

## Structural health (chunk scope: CQL 1.5 List Operators Part 1)

Golden standard: `.temp/architect/golden_standard.md` (7 invariants). The
fix set conforms: all dispatch is shape-driven (`stores_list_value` metadata,
`_is_list_returning_sql`), cardinality knowledge is data-driven via the new
`FHIRSchemaRegistry.is_multi_valued_element` (StructureDefinition snapshot
data, prefix-walking), invalid static typing fails fast (First/Last over
String → typed TranslationError), no SQLRaw, no silent fallbacks. One
abstraction nit corrected: `_resource_rows_navigation` now reuses the
module's `_FHIR_PRIMITIVE_LOWERCASE` constant instead of an inline literal
set (behavior unchanged; parity test green).

Key architectural clarification institutionalized: a query-produced define
(`define Q: (from {1,2,3} X return X)`) and a value-list define (`define G:
Patient.name.given` / static list literal) are DIFFERENT physical shapes with
the same inferred CQL type (List<Integer> vs List<Any>). The explicit
`DefinitionMeta.stores_list_value` discriminator now separates them; this
distinction was the single regression encountered mid-fix (caught by
test_list_part2_parity, fixed before landing).

## QA quality gate
HISTORIAN pass was adequate: re-verified all SKEPTIC fixes regression-free,
adjudicated `not in` ParseError against the official grammar (correct), and
its 4 findings all reproduced and were fixed. One evidence sub-claim was
fixture-shaped (`O.component.code.code` is invalid FHIRPath navigation —
CodeableConcept has no `code` child; empty/false is spec-correct → NOT A BUG
registry). No RETRY_QA.

## Issue summary (see tombstones in evolution.json; details in ARCHIVE_LOG)
QA-001 CRITICAL resolved; QA-002 HIGH resolved; QA-003 HIGH resolved;
QA-004 MEDIUM resolved (one sub-claim INTENDED). Zero open issues.

## Empirical validation (final tree, fresh run)
ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47,
OVERALL 2832/2832 — baseline holds. Focused: list parity 26/26 (3 new
regression tests), CQL unit 1612/1612. Python-only fixes; extension binaries
unchanged and md5-matched repo bundle vs site-packages
(cql 3e7d4167143e01907fdd8561db43b7d7, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a).

## Recommended next (non-blocking, logged for future chunks)
- Sum over Integer lists returns Decimal-typed results (6.0); Integer
  preservation pass if a fixture ever pins the rendering.
- `[Resource].field` (retrieve-then-navigate without an alias) still raises
  a typed TranslationError by design; the QA-004 machinery now makes a
  general expansion feasible if a future chunk requires it.
