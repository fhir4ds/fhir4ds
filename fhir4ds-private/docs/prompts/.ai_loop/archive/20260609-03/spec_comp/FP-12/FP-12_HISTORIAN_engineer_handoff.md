# Engineer Handoff — FP-12 HISTORIAN

## Triage

| Issue | Category | Status |
| --- | --- | --- |
| QA-001 | SPEC_VIOLATION | RESOLVED |
| QA-002 | SPEC_VIOLATION | RESOLVED |

## Fixes

`QA-001`: Fallback `descendants()` used a different child collector than
`children()`, so split JSON primitive-extension fields such as `_birthDate`
could appear as descendants even though `children()` hides that JSON
representation detail. `descendants()` now recurses through the same child
projection as `children()`.

`QA-002`: Native `trace(name, projection)` evaluated the `name` argument with
the traced source collection as focus. It now evaluates the ordinary `name`
argument in the outer invocation focus for sourced calls, while still evaluating
the optional projection over the traced input.

## Validation

- Fresh probe: `.temp/qa/fp12_historian_probe_after_fix.log` passed with 24
  parity cases, 11 expected cases, and 9 invalid-signature cases.
- Focused pytest: `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`
  passed, `6 passed`.
- Native FHIRPath sqllogictest: `528 assertions` passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

## Files

- `fhir4ds/fhirpath/engine/invocations/navigation.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
