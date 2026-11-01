# QA Handoff — SOF-VD-01 SKEPTIC (2026-08-23, iteration 1)

## Scope
SQL-on-FHIR v2 ViewDefinition logical model key elements: `resource` (1..1
ResourceType), `profile` (0..* canonical), `fhirVersion` (0..* FHIRVersion),
root table selection + resourceType filtering, zero-or-more rows per resource.

## Method
39-assertion hypothesis-driven probe (H1–H7) at
`/mnt/d/fhir4ds/.temp/qa/sof_vd01_skeptic_2026_08_23/probe.py` covering parser,
`from_dict`, direct dataclass generate, SQL generation, DuckDB execution
(native fhirpath registration), shared-table filtering, and the official
`view_resource.json` suite file end-to-end (incl. `expectError` semantics).
Spec grounding fetched live: StructureDefinition-ViewDefinition.json (IG
3.0.0-ballot, fhirVersion 6.0.0-ballot5), FHIR-version code system
(build.fhir.org + R5), resource-types binding, IG sushi-config.yaml.

## Result: 38/39 clean; 1 HIGH issue
- **QA-001 (HIGH, OPEN)**: `FHIR_VERSION_CODES` in
  `fhir4ds/viewdef/metadata.py` is a stale R4B-era 42-code set. The IG builds
  on FHIR 6.0.0-ballot5, whose required FHIR-version binding has 24
  two-segment codes (`4.0`, `5.0`, `6.0`, ...). Current code REJECTS
  spec-valid `4.0`/`5.0`/`6.0` and ACCEPTS spec-invalid `4.0.1`/`5.0.0`/
  `6.0.0-ballot4`. Fix = replace the set with the official R6 code-system
  codes; update ~15 tests that encode `4.0.1` as valid (use `4.0`).

## Verified clean (NOT A BUG confirmations)
- H1: missing/empty/lowercase/unknown/array/null `resource` all rejected at
  parser and direct-dataclass generate; permissive validator warns only.
- H2: shared source_table filters `$.resourceType` on the root row only;
  contained/nested same-type resources do NOT leak; top-level unionAll
  branches each carry the filter.
- H3: `profile` canonical format validated (empty/whitespace/non-string/
  bad-pipe rejected); valid version-suffixed canonicals preserved; profiles
  do NOT filter rows at runtime (spec: informative for validators).
- H4 (shape): scalar / present-null / bogus-member fhirVersion rejected;
  valid multi-code arrays accepted (modulo QA-001 code-set bug).
- H5: where-filtered-out resources → 0 rows; zero matching resourceType → 0
  rows; forEach multiplies rows; forEachOrNull preserves parent row.
- H6: default table = pluralized per-type (`patients`), no resourceType
  predicate; shared table = explicit predicate. No stale
  `_current_resource_type` across generator reuse.
- Official `view_resource.json`: 3/3 tests behave per expectation (incl.
  `resource not specified` expectError), `only pts` returns pt1+pt2 only.

## Gates (fresh, this iteration)
ViewDef conformance: 144/144 passed.
