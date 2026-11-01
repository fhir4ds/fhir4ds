# Milestone Review-20 Code Review Findings - Remediated

Workflow: `code_review`
Date: 2026-05-17

## Findings

### REV-001 - CRITICAL - SQL injection in source adapter SQL construction - VERIFIED

User-controlled strings are interpolated directly into DuckDB SQL without literal/identifier binding or escaping:

- `fhir4ds/sources/filesystem.py:62-68` builds `CREATE SECRET` from `secret_name`, `provider`, credential keys, and credential values.
- `fhir4ds/sources/filesystem.py:165-169` embeds `path_pattern` inside `read_parquet`, `read_json_auto`, and `iceberg_scan`; the expression is executed by `DESCRIBE SELECT * FROM {scan_expr}` at `fhir4ds/sources/filesystem.py:175` and by view creation at `fhir4ds/sources/filesystem.py:271`.
- `fhir4ds/sources/relational.py:189-191` embeds `connection_string` in `ATTACH IF NOT EXISTS '{self._connection_string}'`.

Impact: a crafted file path, cloud credential value, secret name, provider, or Postgres connection string can break out of the intended SQL literal/statement and execute arbitrary SQL in the DuckDB connection.

Resolution: added shared `quote_sql_literal()` for SQL string literals, kept `quote_identifier()` for identifiers, added cloud provider/credential-key allowlists, quoted filesystem scan paths, cloud secret values, patient id literals, and Postgres `ATTACH` connection strings. Added focused filesystem and relational source-adapter tests.

### REV-002 - HIGH - Native C++ and forced Python fallback disagree on environment variables - VERIFIED

The native evaluator fabricates arbitrary ValueSet and StructureDefinition URLs and treats additional names as valid, while the forced Python fallback treats them as undefined:

- Native C++: `extensions/fhirpath/src/fhirpath/evaluator.cpp:1026-1049` returns URLs for any `%vs-*` or `%ext-*`, accepts `%factory`, and exempts `%terminologies`.
- Python fallback defaults only specific variables in `fhir4ds/fhirpath/__init__.py:37-45`, and undefined variables raise at `fhir4ds/fhirpath/engine/evaluators/__init__.py:212-213`.

Fresh probe results:

```text
%`vs-foo`: native (['http://hl7.org/fhir/ValueSet/foo'], ..., true), forced fallback ([], ..., false)
%`ext-foo`: native (['http://hl7.org/fhir/StructureDefinition/foo'], ..., true), forced fallback ([], ..., false)
%`factory`: native (['__fhirpath_factory__'], ..., true), forced fallback ([], ..., false)
%`terminologies`: native ([], ..., true), forced fallback ([], ..., false)
```

Resolution: aligned native C++ to the explicit Python fallback defaults. Arbitrary `%vs-*` and `%ext-*` variables, `%factory`, and `%terminologies` are no longer fabricated as valid natively; known default variables remain valid. Rebuilt the native extension and copied the bundled binary.

### REV-003 - MEDIUM - Native type reflection still embeds hand-maintained FHIR model knowledge - DEFERRED

The native C++ type path contains model/type tables and field heuristics in generic runtime logic:

- `extensions/fhirpath/src/fhirpath/evaluator.cpp:254-345` hardcodes FHIR type hierarchy and known type names.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp:843-879` maps field names such as `gender`, `contentType`, `url`, `reference`, and `birthDate` to FHIR primitive types.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp:1527-1553` and `extensions/fhirpath/src/fhirpath/evaluator.cpp:5300-5313` infer `Reference`, `Attachment`, `HumanName`, and `BackboneElement` from object fields and field names.

Impact: FP-20 type-reflection fixes depend on incomplete hand-maintained model knowledge. New FHIR fields, profiles, or less-common datatypes can drift from the Python generated model and from conformance expectations without a data update path.

Disposition: deferred as known architecture debt, not a remaining public parity failure in the current validated surface. Generate or load a native type registry from the same R4 model metadata used by Python (`path2Type`, `type2Parent`, and choice-type metadata) before broadening this area. Until then, do not extend the native maps without parity tests that prove both backends agree.

## Validations

- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/sources/tests/unit/test_filesystem.py fhir4ds/sources/tests/unit/test_relational.py -q --tb=short` - 56 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/sources/tests/unit -q --tb=short` - 138 passed.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py::test_environment_variable_edges_match_cpp -q --tb=short` - 1 passed after rebuilding/copying the native extension.
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_aggregate_lexical_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py -q --tb=short` - 123 passed.
- `cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*"` - 292 assertions passed.
- Source/binary drift check: bundled `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` and local build `extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension` have matching SHA-256 `3fafdd94db8582c91a9c511153b711bedcbaef25a01d50423a8936f7b06c826e`.
- `PYTHONPATH=/mnt/d/fhir4ds python3 conformance/scripts/run_all.py` - 2822/2822 passed:
  - ViewDefinition 134/134
  - FHIRPath R4 935/935
  - CQL 1706/1706
  - DQM 47/47

## Scope Notes

- Review used current source and active loop instructions only.
- No archived `spec_comp/**` workflow output was inspected.
- Product fixes were made after the review returned DEGRADED; this archived finding file records the remediated state.
