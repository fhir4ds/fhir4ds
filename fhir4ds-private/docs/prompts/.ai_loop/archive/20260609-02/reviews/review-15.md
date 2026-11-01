# Code Review Findings - FP-11 through FP-15 Milestone

Review scope: accumulated FHIRPath changes from FP-11 through FP-15, with emphasis on native C++ DuckDB extension parity, forced Python fallback parity, direct helper drift, type/equality/comparison semantics, bundled extension freshness, security/error hygiene, and pytest/conformance regression risk.

## Findings

### REV-001 - MEDIUM - OPEN

`fhirpath_is_valid` drifts between native C++ and the forced Python fallback for valid expressions whose runtime result is empty because operands are incompatible.

Evidence:
- Native SQL probe: `SELECT fhirpath('{}'::JSON, '''10'' > 2'), fhirpath_is_valid('''10'' > 2')` returned `([], true)`.
- Forced Python fallback returned `([], false)` for the same expression.
- The same mismatch reproduced for `'''x'' + 1` and `true < 1`.
- Both backends agree on the public evaluation result (`[]`); only the validity helper drifts.
- Cause is in `fhir4ds/fhirpath/duckdb/udf.py:587-595`: fallback validation compiles and evaluates against a sample Patient resource, catches every exception, and returns `false`. That conflates invalid expressions with spec-valid comparison/arithmetic expressions that evaluate to empty/NULL.

Expected behavior:
- Keep invalid type specifiers and wrong arity invalid, e.g. `1 is NoSuchType`, `(1|2) is Integer`, and `1.is()`.
- Preserve native/fallback parity for syntactically valid empty-result expressions such as `'10' > 2`, `'x' + 1`, and `true < 1`.

Suggested fix:
- Split Python fallback `fhirpath_is_valid_udf()` into parser/type-specifier validation plus narrow semantic checks that are intended to invalidate expressions.
- Do not let sample-resource evaluation errors from incompatible-but-valid comparison/arithmetic expressions turn into `false`.
- Add native-vs-forced-fallback regression coverage that includes `fhirpath_is_valid` in the FP-14 comparison parity suite.

## Non-Findings

- Bundled extension freshness: `sha256sum` matched for `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension` and `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
- FP-11 through FP-15 focused pytest slice passed: 133 tests.
- Additional native/direct fallback probes matched for math guards, tree null serialization/counting, trace projection, current-time determinism, quantity comparison materialization, multi-item equality/equivalence, and type operator supertypes.

## Validation Run

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/unit/test_math.py -q` - 133 passed.
- Custom native-vs-forced-fallback SQL probe for `fhirpath_is_valid` comparison/arithmetic edge cases - reproduced REV-001.
- Custom native-vs-direct-fallback parity probe for FP-11 through FP-15 surfaces - no additional mismatches beyond REV-001.
- `sha256sum` on build and bundled native extension artifacts - hashes matched.
