# Engineer Handoff - FP-20 SKEPTIC - 2026-05-17

All QA issues reached `VERIFIED`.

Fixes implemented:

- Environment-variable validation: removed the fallback evaluator's undefined-variable swallowing so strict/direct evaluation raises and `fhirpath_is_valid()` returns false, while public UDF wrappers still convert row-level errors to empty/NULL.
- Legacy string environment variables: Python `external_constant_term` now handles `%'string'` using the same string-unescape path as literals; native C++ `%` lexing now accepts quoted string variable names via `readString()`.
- BackboneElement type safety: Python model construction adds `BackboneElement` parents for self-aliased backbone paths, `TypeInfo.is_type()` has a cycle guard, and `ResourceNode` normalizes dotted self-type paths to `BackboneElement` for reflection/type checks. Native C++ now treats unknown object-valued FHIR child fields with field metadata as `BackboneElement` for `is`/`as`, matching existing `type()` behavior.
- Added parity coverage in `fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py`, updated the direct evaluator unit expectation in `test_variables.py`, and added native SQL assertions in `extensions/fhirpath/test/sql/fhirpath.test`.
- Rebuilt and copied `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Validation:

- Focused FP-20 parity: 3/3 passed.
- Type/forced-backend guardrails: 7/7 passed.
- Native SQL: 284 assertions passed.
- FHIRPath pytest: 1303 passed, 1 existing warning.
- Full conformance: 2822/2822.
