# CQL-07 EXPLORER QA Handoff

## Scope

CQL type conversion operators:
ToBoolean, ToConcept, ToDate, ToDateTime, ToDecimal, ToLong, ToInteger,
ToQuantity, ToRatio, ToString, ToTime, and translated `convert ... to ...`
forms.

## Findings

### QA-001: Static definition alias conversions emitted invalid CTE lookups

Status: RESOLVED
Severity: HIGH

Conversion functions over literal/static aliases such as `ToInteger(StringAlias)`
and `ToString(RatioAlias)` generated patient-correlated CTE lookups requiring
`_pt.patient_id`. These expressions are compile-time static and should execute
as standalone scalar SQL.

### QA-002: convert List<Code> to Concept emitted JSON[]

Status: RESOLVED
Severity: HIGH

`convert { Code { code: 'x', system: 's' }, Code { code: 'y', system: 's' } }
to Concept` emitted `ToConceptFromList(JSON[])`, which did not bind to the
registered `VARCHAR[]` UDF.

### QA-003: native ToConcept array handling diverged from Python fallback

Status: RESOLVED
Severity: MEDIUM

Native-loaded `ToConcept('[{"code":"x"},{"code":"y"}]')` double-nested the
array under `codes`, while forced Python fallback flattened it. Primitive JSON
inputs also diverged.

## Verification

- Direct parity matrix: 52 cases passed.
- Focused CQL-07 plus adjacent clinical/structural parity pytest: 31/31 passed.
- Native CQL extension SQL tests: 628 assertions passed.
- Full `python3 -m pytest fhir4ds -q`: 7155 passed, 5 skipped.
- Serial `python3 conformance/scripts/run_all.py`: 2822/2822 passed overall.
