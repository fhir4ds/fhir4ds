# Architect Handoff - SOF-VD-01 HISTORIAN

## Golden Standard

Updated `.temp/architect/golden_standard.md` for the SOF-VD-01 root-field
boundary. The key invariant for this fix is that parser, serializer, and direct
SQLGenerator paths must share root logical-model validation for `resource`,
`profile`, `fhirVersion`, and CanonicalResource metadata.

## Audit Result

The remediation is structurally sound. The new validators live in
`fhir4ds/viewdef/types.py`, where adjacent logical-model primitive/container
guards already live, and are consumed by parser, serializer, and generator
guard paths. This removes validation drift without changing SQL row production
semantics. `profile` and `fhirVersion` remain metadata declarations and do not
alter generated SQL unless supported ViewDefinition profiles explicitly add
constraints.

## QA Enforcement

QA was sufficient for the HISTORIAN assignment. It tested required cardinality,
binding validation, canonical profile declarations, serializer behavior, shared
table resourceType filtering, zero-or-more rows, and native/fallback execution
parity. `RETRY_QA` is not required.

## Issue Status

- `SOF-VD-01-HISTORIAN-001`: VERIFIED.
- New architectural findings: none.

## Validation Reviewed

- `.temp/qa/sof_vd01_historian_probe.py`: PASS.
- Focused root parser/generator serializer tests: 14 passed.
- `python3 -m pytest fhir4ds/viewdef/tests -q`: 906 passed.
- `python3 conformance/scripts/run_viewdef.py`: 134/134.
- `python3 conformance/scripts/run_all.py`: 2822/2822.

## Recommended Fix Order

No further fixes for this pass. Return control to the outer spec compliance
orchestrator for archive/schedule handling.
