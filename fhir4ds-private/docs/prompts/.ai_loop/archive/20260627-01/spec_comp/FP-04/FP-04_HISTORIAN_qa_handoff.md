# QA Handoff - SPEC FP-04 HISTORIAN

## Scope

- Chunk: FHIRPath §5.2 Filtering and Projection.
- Personality: HISTORIAN.
- Functions covered: `where(criteria)`, `select(projection)`, `repeat(projection)`, `ofType(type)`.
- Backends covered: bundled native DuckDB/C++ extension and forced Python fallback.

## Spec Basis

- HL7 FHIRPath §5.2.1: `where(criteria)` evaluates criteria per item with `$this` and `$index`; only singleton Boolean `true` includes the item; false/empty exclude; non-singleton/non-Boolean criteria signal an error.
- HL7 FHIRPath §5.2.2: `select(projection)` evaluates per item with `$this` and `$index`, flattens projection collections, and omits empty projections.
- HL7 FHIRPath §5.2.3: `repeat(projection)` evaluates projection for queued items, emits only new projection results by `=` equality, queues those new results, and does not set `$index`.
- HL7 FHIRPath §5.2.4: `ofType(type)` returns items of the requested type or subclass; the type argument is a model type specifier and must resolve.

## Fresh Probing

Created and ran `.temp/qa/fp04_historian_fresh_probe.py`.

The probe compared native and forced fallback public outputs for 24 fresh expressions covering:

- `where()` true/false/empty filtering and strict invalid criteria.
- `select()` flattening and `$index`.
- `repeat()` projection-only traversal, duplicate removal, numeric projection, and repeat-local `$index` absence.
- `ofType()` Resource/DomainResource/Observation/Quantity/Integer/String/System.Any paths plus invalid type/arity shapes.
- Fresh `defineVariable()` scope-leak probes through `select()` and `repeat()`.

## Findings

- No new issue opened.
- Native and forced Python fallback matched for all fresh probe expressions.
- Existing focused parity coverage passed.

## Validation

- `python3 .temp/qa/fp04_historian_fresh_probe.py` passed, 24 expressions.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py -q` passed, 8/8.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py -q` passed, 9/9.
