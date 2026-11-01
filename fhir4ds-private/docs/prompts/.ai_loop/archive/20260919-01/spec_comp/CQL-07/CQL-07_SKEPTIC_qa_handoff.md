# QA Handoff — CQL-07 master launch (SKEPTIC)

## Probed
- CQL 1.5 Appendix B To-conversion tables via a 60-case dual-backend matrix
  (native C++ loaded vs forced Python fallback): Decimal->Integer/Long
  truncation, cross-numeric overflow (int/long range edges), ToBoolean table
  (numeric 0/1, case-insensitive strings, '1.0' rejected), ToInteger/ToDecimal
  string format strictness ('+42' ok, ' 42'/'4.0'/'1e3'/'.5'/'5.' null),
  ToDate/ToDateTime precision preservation (year-only, year-month, offsets,
  invalid calendar dates), ToTime (partial precision, fractions, tz
  normalization, 24:00 rejection), ToString round-trips (bool/int/decimal/time),
  null->null for all, ToQuantity numeric/string/calendar shapes, ToConcept of
  Code selector (dual-backend), and end-to-end population SQL over retrieved
  FHIR fixtures (where-clause ToInteger((O.value as FHIR.string).value) > 40,
  ToBoolean(O.status.value), Patient-context singleton access).
- Probe workspace: /mnt/d/fhir4ds/.temp/qa/cql07_master/probe.py.

## Findings
- QA-001 HIGH: ToInteger(Decimal) and ToLong(Decimal) return NULL on both
  backends; spec mandates truncation toward zero. ConvertsToInteger/Long also
  reject Decimal (twin inconsistency). Naive fix trap: DuckDB
  CAST(1.9 AS INTEGER) rounds to 2.
- QA-002 HIGH: Patient-context singleton primitive access
  (Patient.birthDate.value) returns NULL in population SQL; retrieve-alias form
  works. Root cause: _resource_type_for_resource_ref does not recognize the
  _pt.patient_resource singleton column, so .value is not stripped.

## Verified clean (no issue)
Partial-precision temporal preservation, tz normalization, format strictness,
overflow -> null, null propagation, calendar-keyword ToQuantity, ToString
round-trips, ToConcept dual-path, native-vs-Python parity everywhere (zero
divergences).
