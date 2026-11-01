# QA Handoff - FP-15 HISTORIAN

## Scope

- Chunk: FP-15, FHIRPath Section 6.3 Types.
- Personality: HISTORIAN.
- Spec grounding: HL7 FHIRPath Normative Release, especially Sections 3.2, 4.1, 5.2.4, and 6.3.

## Probe

- Created and ran `.temp/qa/fp15_historian_probe.py`.
- Covered `is type specifier`, `is(type)`, `as type specifier`, `as(type)`, primitive literals, FHIR primitives, resources, complex datatypes, `System.Any`, choice values, empty input, multi-item row resilience, invalid type specifiers, wrong arity, and `type()` metadata interactions.
- Compared public DuckDB native C++ registration with forced Python fallback registration on the same expressions and resources.

## Finding

### QA-001 - MEDIUM - Forced fallback `ofType()` misses root `Any` and nested choice primitive typing

Evidence:

- `component.value.ofType(Integer).count() = 1` over an Observation with `component[0].valueInteger`, `component[1].valueString`, and `component[2].valueQuantity` returned `true` in native C++ but `false` in forced Python fallback.
- `arr.ofType(Any).count()` and `arr.ofType(System.Any).count()` returned all items in native C++ but zero items in forced Python fallback.

Expected:

- `System.Any` is the ultimate root type, so `ofType(Any)` / `ofType(System.Any)` should retain typed input items.
- Polymorphic FHIR values should preserve resolved choice type information for type filtering, so `component.value.ofType(Integer)` should retain the `valueInteger` item.

Suggested fix:

- Align the Python fallback `ofType()` implementation with the existing `is`/`as` type helper behavior for `System.Any` and unqualified choice primitive assertions.

## Validation So Far

- Probe before fix: `cases=68`, `mismatch_count=1`, `expectation_failure_count=1`.
