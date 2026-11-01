# Remediation Engineer Handoff

## Scope

Resolved `BUGFIX-001`: CQL type operators rejected valid FHIR R4 named datatype targets such as `FHIR.Coding` and `FHIR.instant`, blocking `E.value as FHIR.Coding` during direct translation and DQM compilation.

## Root Cause

`_is_known_named_type_target()` used a local allowlist plus profile/resource fallbacks. That covered CQL system/clinical types, loaded resource StructureDefinitions, profiles, and a few FHIR datatypes such as `Period`, but not the generated FHIR datatype model. `FHIR.Coding` and `FHIR.instant` were therefore rejected before runtime assertion semantics could run.

Spec basis:
- CQL named type specifiers may name model types used by `is`, nullable `as`, and strict `cast ... as`.
- FHIR R4 defines `Coding` as a complex datatype and `instant` as a primitive datatype.

## Fix

- Added generated FHIR R4 type metadata helpers in `fhir4ds/cql/translator/expressions/_utils.py`.
- Updated `fhir4ds/cql/translator/expressions/_operators.py` so valid generated FHIR R4 primitive, datatype, and resource names are accepted as named type targets while unsupported names still raise `TranslationError`.
- Updated `fhir4ds/cql/translator/expressions/_query.py` so direct FHIRPath values assert generated FHIR types with `type().name` instead of falling through to resourceType probing. For native FHIRPath cases that report `Coding` as an ambiguous complex container such as `BackboneElement`, a narrow Coding JSON shape fallback is used; JSON-looking string values do not satisfy `FHIR.Coding`.
- Added CQL subproject notes in `fhir4ds/cql/AGENTS.md`.

## Regression Coverage

- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`
  - Accepts `Patient.extension E return E.value as FHIR.Coding`.
  - Accepts `Patient.extension E return E.value as FHIR.instant`.
  - Keeps `FHIR.Period` as a success control.
  - Covers `is`, nullable `as`, and strict `cast ... as` for `FHIR.Coding`.
  - Keeps invalid `FHIR.DefinitelyNotAType` rejected.
  - Executes a runtime parity check where a real `Encounter.class` `Coding` passes and a JSON-looking `Observation.valueString` returns null.
- `fhir4ds/dqm/tests/unit/test_evaluator.py`
  - Compiles a synthetic DQM measure through `MeasureEvaluator.compile_measure()` with `E.value as FHIR.Coding`, proving the DQM surface no longer wraps this as `Compilation failed for group`.

## Validation

- Direct reproducer smoke: `translate_cql()` accepts `E.value as FHIR.Coding`.
- Focused regression tests:
  - `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py::test_cql_fhir_datatype_targets_accept_extension_value_assertions fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py::test_cql_structural_type_rejects_unknown_targets fhir4ds/dqm/tests/unit/test_evaluator.py::test_compile_measure_accepts_fhir_coding_extension_assertion --tb=short -q`
  - Result: 3 passed.
- Touched suites:
  - `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py fhir4ds/dqm/tests/unit/test_evaluator.py --tb=short -q`
  - Result: 55 passed, 2 warnings.
- Full conformance:
  - `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM" > fhir4ds-private/docs/prompts/.ai_loop/.temp/validation_summary_cql_fhir_type_targets_final.log && cat fhir4ds-private/docs/prompts/.ai_loop/.temp/validation_summary_cql_fhir_type_targets_final.log`
  - Result: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Full pytest:
  - `python3 -m pytest fhir4ds/ -x --tb=short > fhir4ds-private/docs/prompts/.ai_loop/.temp/pytest_fhir4ds_cql_fhir_type_targets_final.log && tail -n 50 fhir4ds-private/docs/prompts/.ai_loop/.temp/pytest_fhir4ds_cql_fhir_type_targets_final.log`
  - Result: 7925 passed, 7 skipped, 9 warnings.

## Notes

Pre-existing unrelated working-tree changes were left untouched: `conformance/reports/dqm_report.json`, website docs/sidebar files, and the untracked CQL tests runner facade artifacts.
