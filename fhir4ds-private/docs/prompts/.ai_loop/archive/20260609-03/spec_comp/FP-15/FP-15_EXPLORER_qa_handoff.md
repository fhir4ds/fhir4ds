# QA Handoff - FP-15 EXPLORER

## Scope

- Chunk: FP-15, FHIRPath Section 6.3 Types.
- Personality: EXPLORER.
- Spec source: HL7 FHIRPath Normative Release v2.0.0, Section 6.3 Types.
- Items probed: `is type specifier`, `is(type)`, `as type specifier`, `as(type)`.

## Spec Grounding

- Section 6.3.1 says `is` returns true for a singleton left operand whose type is the requested type or a subtype, false for a singleton non-match, throws for unknown type identifiers and multi-item input, and returns empty otherwise.
- Section 6.3.2 says `is(type)` is the backwards-compatible function form and its argument must be treated as a type specifier, not an ordinary expression.
- Section 6.3.3 says `as` returns the singleton input when it matches the requested type or subtype, throws for unknown type identifiers and multi-item input, and returns empty otherwise.
- Section 6.3.4 says `as(type)` follows the same semantics as the keyword form.
- Section 3.2 and 5.2.4 confirm type specifiers come from the underlying model and may be simple or delimited identifiers, with optional model qualifiers.

## Exploration Performed

Fresh probe: `.temp/qa/fp15_explorer_probe.py`.

The probe compared DuckDB native/C++ registration against forced Python fallback registration across 32 cases:

- `Any` and `System.Any` over literals, complex values, resources, and empty paths.
- Root and nested FHIR choice values, including `value.as(Integer)`, `component.first().value.is(Integer)`, and `component.value.ofType(Integer).as(Integer).is(Integer)`.
- Complex/resource supertypes including `Resource`, `DomainResource`, `Element`, and `HumanName`.
- Qualified and delimited type specifiers such as `FHIR.Patient`, ``FHIR.`Patient``` and `` `Integer` ``.
- Unknown type identifiers and quoted non-type arguments.
- Literal multi-item singleton errors and data-dependent multi-item path errors, confirming public UDF row resilience.
- Duplicate/equivalent union cases before type checks.

## Results

- Probe result: `SUMMARY cases=32 failures=0`.
- Focused parity: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py -q` -> `12 passed`.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Issues

No CRITICAL/HIGH/MEDIUM/LOW issues were found. No remediation is required.
