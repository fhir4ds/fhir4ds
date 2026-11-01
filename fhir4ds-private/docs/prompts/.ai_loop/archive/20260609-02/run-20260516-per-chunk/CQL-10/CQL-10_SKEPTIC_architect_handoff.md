# CQL-10 SKEPTIC Architect Handoff

## Status

- Audit status: PASSED.
- Exit reason: CLEAN.
- Open issues: 0.
- Formal issues verified: `QA-CQL10-SKEPTIC-001`, `QA-CQL10-SKEPTIC-002`.

## Invariants Preserved

- Dynamic FHIR numeric arithmetic must use typed FHIRPath numeric extraction for `value`/`value.*` paths. Text shape is not numeric evidence.
- CQL string concatenation is valid for string operands, but must not preempt numeric arithmetic when a numeric operand is present.
- Untyped dynamic FHIR Quantity choices must not be silently reduced to scalar numbers. Explicit `as Quantity` remains the path for Quantity arithmetic that preserves units.
- Quantity plus/minus scalar is not date arithmetic. Return NULL for definitely non-temporal scalar peers; preserve date/time plus time-valued Quantity for temporal and aggregate/query-derived peers.
- `TimeOfDay()` comparison should stay on SQL time comparison unless the temporal UDF layer gains consistent offset-time parsing in both Python fallback and native C++.

## Residual Risk

- The CQL temporal comparison UDFs still have inconsistent behavior for offset-bearing time-only strings when called directly. The translated CQL path for `TimeOfDay() = TimeOfDay()` is covered, but direct public UDF hardening belongs in the Date/Time chunk if that surface is in scope.

## Validation Summary

- Full conformance remained at 2822/2822.
- Full `fhir4ds/` pytest passed 7170 tests with 5 skips and 9 warnings.
- Native C++ CQL unittest passed 638 assertions.
