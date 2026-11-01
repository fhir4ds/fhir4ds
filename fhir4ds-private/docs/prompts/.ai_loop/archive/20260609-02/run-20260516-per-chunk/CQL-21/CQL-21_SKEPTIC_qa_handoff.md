# QA Handoff - CQL-21 SKEPTIC

## Scope

Fresh source/spec-driven probes for CQL clinical operators:
Age/AgeAt/CalculateAge/CalculateAgeAt, Code/Concept equality and equivalence,
CodeSystem membership, ValueSet membership, and ExpandValueSet.

Normative source consulted: CQL v1.5.3 Appendix B, Clinical Operators:
Age/AgeAt/CalculateAge/CalculateAgeAt, Equal, Equivalent, In (Codesystem),
ExpandValueSet, and In (Valueset).

## Findings

- QA-001 HIGH: Age precision coverage is incomplete. Patient-context
  `AgeInWeeks()` translates to a no-argument UDF call and binder-fails.
  `AgeInHoursAt`, `AgeInMinutesAt`, and `AgeInSecondsAt` are not registered on
  either Python fallback or native/C++ DuckDB surfaces. Python fallback
  `CalculateAgeInHoursAt` truncates DateTime birth/asOf values to dates and
  returns `0` for a one-hour interval where native/C++ returns `1`.
- QA-002 HIGH: Static `in CodeSystem` emits invalid SQL of the form
  `'<Code JSON>' IN '<CodeSystem JSON>'` for String, Code, and Concept
  overloads.
- QA-003 HIGH: Static `Code/Concept in ValueSet` routes clinical JSON through
  `in_valueset(..., 'code', ...)` and returns false even when the loaded value
  set contains an equivalent code. `ExpandValueSet(ValueSet)` emits an
  unregistered public function.
- QA-004 MEDIUM: Code equality currently uses raw SQL/JSON equality and returns
  false when one Code has an extra display component. CQL specifies null when
  Code/Concept equality operands have different components specified.

## Fresh Probe Summary

- Python fallback and native/C++ direct public helper comparisons were run for
  age functions and valueset membership.
- Translated CQL SQL was inspected and executed for the failing cases.
- No archived spec-compliance outputs were used as evidence.
