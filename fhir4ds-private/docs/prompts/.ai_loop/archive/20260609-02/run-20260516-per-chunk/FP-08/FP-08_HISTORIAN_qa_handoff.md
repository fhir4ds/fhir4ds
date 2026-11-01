# QA Handoff - FP-08 HISTORIAN

Scope verified: FHIRPath N1 §5.5.7 Quantity Conversion, §5.5.8 String Conversion, and §5.5.9 Time Conversion.

Spec anchors:
- Quantity conversion is singleton-only and accepts Integer, Decimal, Quantity, convertible String, and Boolean; optional unit conversion may return empty/false if unsupported or incompatible.
- String conversion is singleton-only and covers String, Integer, Decimal, Date, Time, DateTime, Boolean, and Quantity; partial dates/times stringify only to their actual precision.
- Time conversion is singleton-only and accepts Time or convertible String; partial times remain partial.

Exploration performed:
- Reviewed Python fallback conversion implementation in `fhir4ds/fhirpath/engine/invocations/misc.py`.
- Reviewed native conversion implementation in `extensions/fhirpath/src/fhirpath/evaluator.cpp`.
- Built sandbox probe at `.temp/qa/fp08_historian_probe.py`.
- Forced and compared native C++ DuckDB registration and Python fallback registration in separate processes.
- Exercised `toQuantity([unit])`, `convertsToQuantity([unit])`, `toString()`, `convertsToString()`, `toTime()`, and `convertsToTime()` on literal and JSON-field inputs.

Findings:
- `QA-001` MEDIUM OPEN: `toTime()` and `toString()` incorrectly expand minute-precision times. Both native C++ and Python fallback return `14:34:00` for `'14:34'.toTime()` and `@T14:34.toString()`. Per §5.5.9 and §5.5.8, expected output is `14:34` with minute precision preserved.

Non-findings:
- Quantity string parsing and target-unit checks were clean when native and fallback backends were run in isolated processes. The concurrent sandbox probe produced misleading differences because DuckDB extension/Python fallback registration is process-global enough to make simultaneous mixed-backend probing unreliable for this case.
