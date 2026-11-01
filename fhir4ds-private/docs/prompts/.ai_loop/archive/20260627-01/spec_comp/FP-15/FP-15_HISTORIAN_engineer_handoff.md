# Engineer Handoff - FP-15 HISTORIAN

## Scope

- Chunk: FP-15, FHIRPath §6.3 Types.
- Issue fixed: `QA-001` MEDIUM, empty-input `is` returned empty/NULL instead of false for ordinary non-error empty input.
- Fresh probe: `.temp/qa/fp15_historian_fresh_probe.py`.

## Changes

- Python engine: `fhir4ds/fhirpath/engine/invocations/types.py::is_fn`
  now validates the type specifier and returns `[False]` for ordinary empty
  `is` inputs, while preserving empty results for absent FHIR primitive paths
  such as `Observation.issued is instant` required by the R4 fixture suite.
- Native engine: `extensions/fhirpath/src/fhirpath/evaluator.cpp::fn_isType`
  mirrors the same empty-input boundary and still validates type specifiers
  before short-circuiting.
- DuckDB Python fallback: `fhir4ds/fhirpath/duckdb/udf.py` value[x] assertion
  helpers now use FHIR type hierarchy matching for `is` while preserving exact
  choice-suffix behavior for `as`.
- Regression coverage added to:
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`
  - `extensions/fhirpath/test/sql/fhirpath.test`

## Recovery Gate

The first generic empty-input fix passed the fresh probe but failed adjacent
environment parity for fallback value[x] choice `is(string)` behavior. Per the
recovery rule, deep research was recorded in
`fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md` before
the second fix. Full FHIRPath R4 conformance then exposed the absent FHIR
primitive sentinel, and the final fix preserves that boundary.

## Validation

- `cmake --build extensions/fhirpath/build/release --config Release -j 8`
- `cp extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `sha256sum extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension extensions/fhirpath/build/release/repository/v1.5.2/linux_amd64/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `python3 .temp/qa/fp15_historian_fresh_probe.py`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py -q`
- `extensions/fhirpath/build/release/test/unittest "*fhirpath*"`
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q`
- `python3 conformance/scripts/run_fhirpath_r4.py`
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"`

Full conformance summary: ViewDefinition 134/134, FHIRPath R4 935/935, CQL
1706/1706, DQM 47/47, overall 2822/2822.

## Status

`QA-001` is resolved.

Architect audit found `ARCH-001`: native C++ accepts
`Parameters.parameter[0].value.as(string)` for a concrete `valueUri`, while
forced Python fallback returns empty. Fix native primitive choice `as`
exactness without changing `valueUri.is(string)` hierarchy behavior.
