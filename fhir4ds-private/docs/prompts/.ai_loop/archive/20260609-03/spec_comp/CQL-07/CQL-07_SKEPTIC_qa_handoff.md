# QA Handoff — CQL-07 SKEPTIC

## Scope
CQL Type Operators - Conversions: ToBoolean, ToConcept, ToDate, ToDateTime, ToDecimal, ToLong, ToInteger, ToQuantity, ToRatio, ToString, and ToTime. Fresh probe compares native-loaded CQL registration with forced Python fallback registration and translated CQL execution.

## Spec Basis
CQL 1.5.3 Appendix B lists the supported ToString overloads for Boolean, Integer, Long, Decimal, Quantity, Ratio, Date, DateTime, and Time, with String identity treated as a scalar no-op in this implementation. ConvertsToString is tied to whether the corresponding ToString conversion is supported. Interval and Concept are not supported ToString sources.

## Finding
QA-001 HIGH: translated CQL lets unsupported structural/clinical values flow into generic ToString/ConvertsToString because Interval and Concept are transported as VARCHAR JSON. Reproducer: `.temp/qa/cql07_skeptic_probe.py`.

Observed before remediation:
- `ToString(Interval[1, 2])` -> interval JSON text
- `convert Interval[1, 2] to String` -> interval JSON text
- `ConvertsToString(Interval[1, 2])` -> true
- `ToString(ToConcept(Code { code: 'x', system: 's' }))` -> Concept JSON text
- `ConvertsToString(ToConcept(Code { code: 'x', system: 's' }))` -> true

Expected: NULL for conversion results and false for ConvertsToString. Direct scalar conversion probes for Boolean, Integer/Long, Decimal, Date/DateTime/Time, Quantity, Ratio, and direct structural SQL parity passed before this translated-boundary failure.
