# CQL-01 EXPLORER Architect Handoff

## Audit Result

PASS. No open EXPLORER issues remain for CQL-01 primitive types.

## Architecture Notes

- CQL primitive assertions need two layers of type evidence:
  - direct FHIR values should use FHIRPath runtime metadata, especially `type().name` for choice values;
  - materialized query definitions should use inferred `definition_meta.cql_type` before falling back to SQL physical types.
- Primitive conversions are public DuckDB surface area. Keep the translator, Python fallback registration, and native-loaded connection behavior aligned by routing through the same macro/UDF names.
- Generic DuckDB casts are not a safe substitute for CQL primitive conversion functions because they round numeric values and may throw where CQL expects null/false.
- Numeric suffix validation belongs in the lexer only for no-whitespace suffixes; whitespace-separated tokens remain parser/query semantics.

## Regression Gates

- Full conformance: 2822/2822 overall.
- Official CQL conformance: 1706/1706.
- Broad CQL pytest: 1361 passed, 5 skipped.
- Native-loaded and forced Python fallback CQL DuckDB parity: covered by primitive and conversion parity tests.
- `git diff --check`: clean.
