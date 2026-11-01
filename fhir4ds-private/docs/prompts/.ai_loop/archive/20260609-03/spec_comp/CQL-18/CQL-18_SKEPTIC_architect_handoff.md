# Architect Handoff: CQL-18 SKEPTIC

## Golden Standard

Golden standard invariants were written to `.temp/architect/golden_standard.md`.
`SPEC_ARCHITECTURE.md` was not present, so the audit used root/CQL AGENTS,
translator architecture guidance, durable knowledge, and the local code shape.

## Structural Audit

No new architectural finding is open. The remediation is localized to the CQL
list semantic boundary and translator type-detection boundary:
`CQLListElementEquivalent` now delegates clinical Code/Concept equivalence
before raw equality, `singleton from` over nested lists is recognized as
list-typed, and bare Quantity-containing list literals no longer masquerade as
scalar Quantity expressions.

The fix follows the established AST/type-metadata discipline: direct helper
semantics live in CQL DuckDB macros, translator dispatch recognizes list vs
scalar shapes before SQL generation, and no measure/profile/fixture-specific
logic was introduced.

## QA Gate

QA was sufficient for the SKEPTIC mandate. It challenged null lists, empty
lists, lists containing null, transported aliases, Quantity unit-aware list
comparison, clinical Code/Concept list equivalence, direct helpers, translated
CQL, forced Python fallback, native-loaded registration, and no-Python C++
runtime behavior. `RETRY_QA` was not set.

## Issues

- `QA-001` HIGH `SPEC_VIOLATION`: verified fixed. Transported
  `List<Code>` / `List<Concept>` equivalence now uses CQL clinical
  equivalence instead of raw JSON equality.
- `QA-002` HIGH `SPEC_VIOLATION`: verified fixed. Quantity list equality now
  routes through CQL list equality with unit-aware element comparison instead
  of scalar Quantity comparison.

Recommended fix order: none. Both issues are verified and no engineer phase is
needed.

## Validation

- Fresh probe: `.temp/qa/cql18_skeptic_probe.py` passed across forced Python
  fallback, native-loaded, and no-Python runtimes.
- List Part 1 parity: 7/7.
- List Part 1 + Part 2 parity: 13/13.
- Official list parser category: 212/212.
- CQL conformance: 1706/1706.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
