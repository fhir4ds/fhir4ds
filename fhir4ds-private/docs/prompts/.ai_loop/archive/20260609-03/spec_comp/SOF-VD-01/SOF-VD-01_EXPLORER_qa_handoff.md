# QA Handoff: SOF-VD-01 EXPLORER

Scope: SQL-on-FHIR ViewDefinition root logical model fields for
`resource`, `profile`, and `fhirVersion`, plus root table selection,
resourceType filtering, and zero-or-more output rows per matching resource.

Spec basis: SQL-on-FHIR latest ViewDefinition says a ViewDefinition is a
tabular projection of a FHIR resource, each instance is tied to a single FHIR
resource type and creates zero or more rows per resource, `resource` is `1..1`
with required ResourceType binding, `profile` is `0..* canonical`, and
`fhirVersion` is `0..* code` with required FHIRVersion binding:
https://sql-on-fhir.org/ig/latest/StructureDefinition-ViewDefinition.html

EXPLORER probes exercised chained boundaries rather than archived evidence:

- Parser input -> dataclass -> `to_dict()` -> parser round trip.
- Direct dataclass construction bypassing the parser, then `to_dict()` and
  `SQLGenerator.generate()`.
- Malformed `resource`, `profile`, `meta.profile`, and `fhirVersion` values
  after SKEPTIC/HISTORIAN fixes.
- Shared mixed `resources` table SQL requiring an explicit root
  `resourceType = 'Patient'` predicate.
- DuckDB execution where one Patient expands to multiple `forEachOrNull` rows,
  an Observation in the same table is filtered out, and a Patient without
  telecom still produces a null child row.
- Root `where` producing zero rows.
- Native-loaded FHIRPath registration and forced Python fallback.

Fresh probe:

- `python3 .temp/qa/sof_vd01_explorer_probe.py`
- Result: PASS, `native_available=True`

Validation:

- Focused parser/generator/integration pytest: 65 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

Issues found: 0.

Notes:

- The first probe attempt imported an installed `fhir4ds` from site-packages
  because `.temp/qa` was first on `sys.path`. The probe now prepends the repo
  root before importing, matching the ViewDefinition AGENTS warning.
