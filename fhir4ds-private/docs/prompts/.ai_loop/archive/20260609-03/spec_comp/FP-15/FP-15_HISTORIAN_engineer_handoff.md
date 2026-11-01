# Engineer Handoff - FP-15 HISTORIAN

## Triage

| Issue | Category | Severity | Status |
| --- | --- | --- | --- |
| QA-001 | SPEC_VIOLATION | MEDIUM | RESOLVED |

## Fix

`QA-001` was reproduced with `.temp/qa/fp15_historian_probe.py`.

Root cause:

- Forced Python fallback `filtering.of_type_fn()` only used generic `TypeInfo` equality/subtype checks.
- It did not share the `System.Any` root-type predicate or unqualified choice primitive predicate already used by `types.is_fn()` / `types.as_fn()`.

Change:

- Updated `fhir4ds/fhirpath/engine/invocations/filtering.py` so `ofType()` retains all items for `Any` / `System.Any` and preserves unqualified choice primitive matches such as `component.value.ofType(Integer)`.
- Added native/fallback parity coverage in `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`.

Spec grounding:

- FHIRPath §3.2 describes filtering polymorphic nodes by type before navigation.
- FHIRPath §4.1 defines `System.Any` as the ultimate root type.
- FHIRPath §5.2.4 defines `ofType(type)` as type filtering.
- FHIRPath §6.3 defines type specifier resolution for type operations.

## Validation

- FP-15 probe after fix: `70` cases, `0` mismatches, `0` expectation failures.
- Focused parity: `test_type_parity.py` passed, `12 passed`.
- Related focused suites: `test_conformance_regressions.py` and `test_filter_projection_parity.py` passed, `23 passed`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.

No native C++ code changed, so no extension rebuild was required.
