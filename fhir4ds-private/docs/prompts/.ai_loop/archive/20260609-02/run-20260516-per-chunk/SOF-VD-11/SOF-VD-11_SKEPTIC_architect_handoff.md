# Architect Handoff - SOF-VD-11 SKEPTIC

## Structural Health

Healthy after remediation. The fix preserved the intended layer boundary:
ViewDefinition continues to emit runtime type guards through public FHIRPath
DuckDB UDFs, and the native/fallback mismatch was corrected in FHIRPath type
reflection rather than by weakening ViewDefinition validation.

## Golden Standard

Written to:
`.temp/architect/golden_standard.md`

Key invariant confirmed: generated ViewDefinition SQL may rely on FHIRPath
`type()` as a contract, but parity failures belong in the FHIRPath layer.

## QA Audit

QA was sufficient. It tested the Domain 5 row-preservation concern with
`forEachOrNull`, covered simple Patient rows, Patient.address unrolling,
filtered Observation rows, declared column type coercion, shared-table resource
filtering, and native C++ versus forced Python fallback. The probe found a
real non-happy-path runner bug instead of only confirming official fixtures.
No `RETRY_QA` veto.

## Findings

No new architectural findings.

Resolved issue count:
- SPEC_VIOLATION: 1 resolved (`QA-001`)

Open issue count:
- CRITICAL/HIGH/MEDIUM: 0

## Compressed Handoffs

SKEPTIC QA found that a valid filtered Observation ViewDefinition projecting
`valueQuantity.value` as explicit `decimal` raised a ViewDefinition type guard
error only under forced Python fallback, while native C++ returned the expected
row. Remediation fixed fallback FHIRPath type reflection so numeric/Boolean
value shape wins before broad suffix fallbacks when exact metadata is
unavailable, added FHIRPath native/fallback parity coverage, added a
ViewDefinition Observation decimal execution regression, and validated with
focused tests, full ViewDefinition pytest, FHIRPath focused pytest, and full
conformance.

## Recommended Fix Order

No further fixes required for this launch.

