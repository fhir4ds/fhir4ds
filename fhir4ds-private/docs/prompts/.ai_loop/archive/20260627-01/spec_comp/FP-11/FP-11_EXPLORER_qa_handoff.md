# QA Handoff - FP-11 EXPLORER

## Scope

Fresh launch for SPEC COMPLIANCE CHUNK FP-11, qa_personality `EXPLORER`.
I used the current `evolution.json`, current source tree, and the official HL7
FHIRPath continuous-build source for §5.7 Math (STU). I did not use prior
FP-11 probe artifacts as proof.

Spec baseline paraphrase: §5.7 math functions accept singleton inputs. `abs()`
keeps the same Integer/Long/Decimal/Quantity type and preserves Quantity units.
`ceiling()`, `floor()`, and `truncate()` return the mathematical integral
result for Decimal or Quantity input, preserving Quantity units. `exp()`,
`ln()`, `log(base)`, `power(exponent)`, `round([precision])`, and `sqrt()`
return Decimal where defined; `power()` is always Decimal-shaped, and invalid
domains such as negative square roots or non-integral powers of negative bases
return empty public results.

## Fresh Probe

Added `.temp/qa/fp11_explorer_fresh_probe.py`.

The probe compares native DuckDB/C++ registration with forced Python fallback
registration across:

- Decimal return typing and `toString()` shape for `exp`, `ln`, `log`,
  `power`, `round`, and `sqrt`.
- Quantity unit preservation for `abs`, `ceiling`, `floor`, `round`, and
  `truncate`.
- Empty results for invalid numeric domains.
- FP-11 SKEPTIC/HISTORIAN guardrails: resource-backed Quantity math,
  Decimal-shaped `power()`, Long boundary `abs()`, and Decimal `toString()`.
- New EXPLORER Long/large-Decimal boundaries for integral math functions.

## Finding

`QA-001` MEDIUM `SPEC_VIOLATION` is open.

Native C++ integral math functions still convert Long-sized values through
binary floating point before producing integral outputs. This corrupts valid
Long inputs and nearby Decimal values.

Representative evidence:

```sql
SELECT fhirpath('{"resourceType":"Observation"}'::JSON,
                '9223372036854775807L.ceiling()');
```

Actual native result: `['-9223372036854775808']`

Forced Python fallback result: `['9223372036854775807']`

Additional observed native drift:

- `9223372036854775807L.floor()` -> `-9223372036854775808`
- `9223372036854775807L.truncate()` -> `-9223372036854775808`
- `9223372036854774785L.ceiling()` -> `9223372036854774784`
- `9223372036854775807L.round().toString()` -> `9223372036854775808.0`
- `9223372036854775807L.power(1).toString()` -> `9.2233720368547758e+18`

Likely root cause: native `fn_ceiling`, `fn_floor`, `fn_truncate`,
`fn_round`, and `fn_power` use `getNumericValue()` as `double` for Integer/Long
inputs, losing exactness and wrapping during `int64_t` casts.

## Validation

Ran exploratory native/fallback probes inline. The fresh probe currently fails
on `QA-001` as expected before remediation.
