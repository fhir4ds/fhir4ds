# QA Handoff - FP-11 HISTORIAN

## Scope

SPEC COMPLIANCE CHUNK FP-11: FHIRPath continuous-build §5.7 Math (STU).
Personality: HISTORIAN. This pass used fresh probes only; prior FP-11 artifacts
were not used as proof.

Spec source: https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

Normative oracle used:
- Math functions accept singleton input collections; empty input returns empty.
- `abs()` accepts Integer, Long, Decimal, and Quantity and returns the absolute
  value in the same type. Quantity units are unchanged.
- `ceiling()`, `floor()`, `round([precision])`, and `truncate()` accept Quantity
  and return Quantity preserving the same unit.
- `exp()`, `ln()`, `log(base)`, `power(exponent)`, and `sqrt()` accept numeric
  inputs only. Undefined mathematical results return empty.
- `power()` always returns Decimal.
- Decimal `toString()` uses the `(-)?#0.0#` representation.

## Fresh Probe

Created `.temp/qa/fp11_historian_fresh_probe.py` with native DuckDB/C++ and
forced Python fallback checks for:
- all FP-11 functions named in the chunk notes;
- empty input, multi-item input, incompatible String/Boolean/Quantity cases;
- dynamic resource values and dynamic math arguments;
- Quantity unit preservation for `abs()`, `ceiling()`, `floor()`, `round()`,
  and `truncate()`;
- Decimal-shaped `power()` results and explicit `toString()` formatting.

Current failing command:

```bash
python3 .temp/qa/fp11_historian_fresh_probe.py
```

Observed first failure:

```text
native 9223372036854775807L.abs():
(['-9223372036854775808'], '-9223372036854775808',
 '[-9223372036854775808]', -9.223372036854776e+18, None, True)
```

## Issues Opened

- `QA-001` MEDIUM: native C++ Long `abs()` overflows/rounds at 64-bit boundary.
- `QA-002` MEDIUM: forced Python fallback does not treat resource-backed FHIR
  Quantity JSON as Quantity for current §5.7 Quantity-capable math functions.
- `QA-003` MEDIUM: forced Python fallback `2.power(3).toString()` returns
  `"8"` instead of Decimal-shaped `"8.0"`.

## Suggested Fix Targets

- Native `extensions/fhirpath/src/fhirpath/evaluator.cpp::fn_abs()` should not
  compute integer absolute values through `double`.
- Python fallback `fhir4ds/fhirpath/engine/invocations/math.py` should route
  Quantity singleton detection through `util.parse_value(...)`.
- Python fallback `fhir4ds/fhirpath/engine/invocations/misc.py::to_string()`
  should format Decimal values with at least one fractional digit.
