# Architect Handoff - SOF-VD-02 SKEPTIC

## Audit Result

PASS. The remediation keeps constant handling structurally aligned with the
SQL-on-FHIR logical model: parser, public constructor, serializer, direct
generator input, and resolver paths now share central metadata/validation
instead of each carrying partial rules.

## Golden Standard

Wrote `.temp/architect/golden_standard.md` with constants-specific invariants.
Key invariants: strict singular logical-model field names, central
`value[x]` allowlist/primitive validation, direct dataclass parity with parsed
JSON, one name to one constant value, lexical FHIRPath constant scanning, and
typed errors for undefined user constants.

## QA Audit

QA was sufficient for the SKEPTIC objective. It attacked plural-vs-singular
fields, missing/multiple/non-primitive `value[x]`, all primitive choices,
invalid primitive shapes, `%name` substitution in paths and where filters,
literal percent text, duplicate names, undefined constants, direct dataclass
generator input, serializer behavior, and DuckDB execution. No `RETRY_QA`
needed.

## Structural Notes

No new architecture findings were logged. `types.py` is now the central
constant validation surface; `constants.py` owns FHIRPath lexical scanning and
resolution; `generator.py` consumes parsed/validated `Constant` objects and
retains a final direct-input guard. `validate_view_definition()` remains a
permissive warning API and was not tightened.

## Validation

- Fresh probe: `.temp/qa/sof_vd02_skeptic_probe.py` PASS
- Focused constants/parser/generator/where/DuckDB pytest: 98 passed
- Full ViewDefinition pytest: 916 passed
- ViewDefinition conformance: 134/134
- Full conformance: 2822/2822
