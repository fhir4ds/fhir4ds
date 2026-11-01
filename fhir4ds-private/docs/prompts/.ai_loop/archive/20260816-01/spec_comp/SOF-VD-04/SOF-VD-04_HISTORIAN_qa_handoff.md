# QA Handoff — SOF-VD-04 HISTORIAN iter 1 fresh run (2026-07-03)

## Personality: HISTORIAN (Role B — Spec Compliance Verifier)

## Mission
Systematically walk through the SQL-on-FHIR v2 spec section-by-section, testing
every mandatory behavior for `column.collection`, `column.type`, and
`column.tag` (chunk SOF-VD-04).

## Authoritative Spec Reference
- Source: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html (v2.1.0-pre)
- Key normative text:
  - **§Column Types**: "All values in a given column must be of a single data type. The data type can be explicitly specified with the `collection` and `type` for a column."
  - **§Processing Algorithm > Process(S, N) step 2.2.1**: For each Column `col` of `S.column`, define `val` as `fhirpath(col.path, f)`:
    1. empty set → `null`
    2. single element → that element
    3. `col.collection` true → `val` (the whole collection)
    4. **else: throw "Multiple values found but not expected for column"**
  - **§Specifying a Select > forEachOrNull**: empty foci → emit one row with all-`null` column bindings.
  - **§Generating Schemas / Database Type Hints**: `tag` is an array of `{name, value}` objects used for implementation-specific type hints (e.g. `ansi/type = DATE`).

## Probe Coverage
43-assertion / 6-battery systematic spec-walkthrough probe at
`/mnt/d/fhir4ds/.temp/qa/sof_vd04_historian_2026_07_03_fresh/probe.py`.

Batteries:
- **Item 1 — collection default false**: 5 assertions across direct construction, `to_dict()` round-trip, parser path (omitted), explicit `false`, parser explicit `false`.
- **Item 2 — multi-value non-collection error**: 2 assertions covering SQL cardinality guard presence + DuckDB runtime execution (multi-given Patient raises `Invalid Input Error: ViewDefinition column 'givens' path 'name.given' violates collection=false`).
- **Item 3 — collection=true multi-value**: 5 assertions covering direct construction, `to_dict()`, parser path, SQL generation, DuckDB runtime (returns `[['Alpha', 'Beta']]` without error).
- **Item 4 — type URI handling (primitive + non-primitive)**: 15 assertions covering all 8 primitive types (`string`, `integer`, `boolean`, `decimal`, `dateTime`, `Coding`, `CodeableConcept`, `Quantity`), full StructureDefinition URI normalization, fragment form acceptance, unknown external URI preservation, whitespace rejection, non-string rejection, parser null-type rejection.
- **Item 5 — type mismatch reporting**: 3 assertions covering typed-column SQL generation, typed `to_dict()` round-trip, DuckDB runtime type-mismatch error (`declared type integer` reported for string-valued path).
- **Item 6 — tag 0..* with required name/value**: 13 assertions covering empty array acceptance, default empty array, single-tag round-trip, missing-name rejection, missing-value rejection, whitespace name/value rejection, non-dict item rejection, None rejection, 100-tag stress, parser single-tag, plural `tags` rejection, duplicate-name acceptance.

## Results
**43 PASS / 0 FAIL / 0 INFO**

All six SOF-VD-04 spec items verified CLEAN. Notable confirmations:

- **Item 1**: `Column(path='id', name='pid').collection` is `False` (not `None`, not missing). `to_dict()` correctly omits the default. Parser path with omitted `collection` produces `False`. Explicit `false` accepted at all boundaries.
- **Item 2**: SQL generator emits `array_length(fhirpath(...)) > 1` cardinality guard. Runtime DuckDB execution on a Patient with `name=[{"given": ["Alice", "Bob"]}]` correctly raises `Invalid Input Error: ViewDefinition column 'givens' path 'name.given' violates collection=false / type unset; non-primitive output`.
- **Item 3**: `Column(path='name.given', name='givens', collection=True)` round-trips. SQL generated without parse failure. Runtime execution returns `[(['Alpha', 'Beta'],)]` — the whole collection — without raising a cardinality error.
- **Item 4**: All 8 primitive/non-primitive types normalize to `ColumnType`. Full URI `http://hl7.org/fhir/StructureDefinition/string` normalizes to `ColumnType.STRING`. Fragment form `http://hl7.org/fhir/StructureDefinition/Observation#referenceRange` accepted (returns `'referenceRange'`). Unknown external URI `http://example.com/Foo` preserved verbatim. Whitespace-only URI rejected. Non-string type rejected. Parser null-type rejected with clear ParseError.
- **Item 5**: Typed column SQL includes both cardinality and type guards. `to_dict()['type']` correctly emits `'string'`. Runtime execution on `type=integer` column whose path returns a non-integer string correctly raises `Invalid Input Error: ViewDefinition column 'pid' path 'id' violates collection=false / declared type integer`.
- **Item 6**: Empty tag array accepted (0..* lower bound). Default `tag=[]`. Single-tag `to_dict()` round-trip exact. Missing name/value rejected at `ColumnTag.from_dict` and `ColumnTag.__post_init__`. Whitespace name/value rejected (per SOF-VD-03 EXPLORER fix). Non-dict tag item rejected. `tag=None` rejected. 100-tag stress passes. Parser single-tag round-trip exact. Plural `tags` rejected with helpful error message. Duplicate tag names accepted (spec has no dedup rule).

## Validation
- ViewDefinition pytest: **1055/1055** PASS (no regressions)
- Full conformance baseline preserved (per `PROC_VALIDATION.md` baseline check below).

## Conclusion
**CLEAN.** Zero non-terminal CRITICAL/HIGH/MEDIUM issues identified for SOF-VD-04.
Per `GLOBAL_RULES.md` §Orchestration, clean exit is allowed at `min_iterations=1`.
The SOF-VD-04 collection/type/tag surface is spec-compliant end-to-end across
direct dataclass construction, parser, `to_dict()`, SQL generation, and DuckDB
execution boundaries. All earlier SOF-VD-04 SKEPTIC/HISTORIAN/EXPLORER fixes
(SOF-VD-03 SKEPTIC 2026-07-03 `Column.__post_init__`, SOF-VD-03 EXPLORER
2026-07-03 whitespace rejection, multi-value cardinality guard, type-mismatch
runtime reporting) remain intact.

## Methodology Note
HISTORIAN's spec-walkthrough approach is the right tool for re-validating a
chunk whose prior iterations have already fixed all known defects. Walking the
spec section-by-section forces the auditor to enumerate every mandatory
behavior (collection default, cardinality error, collection=true semantics,
type URI forms, type-mismatch reporting, tag cardinality) and write a targeted
reproducer for each, rather than relying on hypothesis-driven or fuzzing
approaches. The 43 assertions cover the full surface and confirm no
regressions remained after the post-SOF-VD-03 SKEPTIC 2026-07-03 hardening.
