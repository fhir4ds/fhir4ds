# QA Handoff - SOF-VD-01 HISTORIAN

## Scope

Fresh HISTORIAN pass for SQL-on-FHIR ViewDefinition root logical-model fields:
`resource`, `profile`, `fhirVersion`, root table filtering, and zero-or-more rows
per resource instance.

## Spec Anchors

- SQL-on-FHIR v2.1.0-pre ViewDefinition logical model: `resource` is required
  `1..1` and bound to ResourceType; `profile` is `0..* canonical(StructureDefinition)`;
  `fhirVersion` is `0..* code` with required FHIRVersion binding.
- SQL-on-FHIR functional model: applying a ViewDefinition transforms FHIR
  resources into rows via `column`, `where`, `forEach`, `select`, and `union`.

## Fresh Probe

Created `.temp/qa/sof_vd01_historian_probe.py`.

Validated parser rejection for missing/array/unknown `resource`, malformed
`profile`, and malformed `fhirVersion`; parser round-trip preservation for valid
profile and fhirVersion; SQLGenerator direct-dataclass rejection for invalid
resource/fhirVersion; and planned native/fallback execution parity for mixed
Patient/Observation resources with `forEachOrNull`.

## Finding

`SOF-VD-01-HISTORIAN-001` (HIGH): `ViewDefinition.to_dict()` can emit invalid
root logical-model JSON for direct dataclass construction. Reproducers:

- `resource=["Patient"]` serializes successfully.
- `resource="DefinitelyNotAResource"` serializes successfully.
- `fhirVersion="4.0.1"` serializes as `["4", ".", "0", ".", "1"]`.
- `fhirVersion=["9.9.9"]` serializes successfully.
- `meta={"profile": "http://example.org/Profile"}` serializes successfully.

Expected: serializer should apply the same root logical-model guards as parser
and direct SQL generation before producing official JSON.

## Handoff

Proceed to FIX. Centralize root `resource` and `fhirVersion` validation in
`types.py`, reuse it from parser, generator, and serializer, and make
`to_dict()` validate root metadata through `validate_root_metadata_fields()`.
