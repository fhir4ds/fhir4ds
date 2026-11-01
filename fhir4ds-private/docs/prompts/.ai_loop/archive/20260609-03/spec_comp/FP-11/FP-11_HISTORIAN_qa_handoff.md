# QA Handoff — FP-11 HISTORIAN

Phase: QA
Personality: HISTORIAN
Spec focus: FHIRPath §5.7 Math (STU)
Spec source: https://hl7.org/fhirpath/N1/#math

## Probe

Created and ran `.temp/qa/fp11_historian_probe.py` against both the bundled
native C++ DuckDB extension and a forced Python fallback connection. The probe
walked all required §5.7 functions:

- `abs()`, `ceiling()`, `exp()`, `floor()`, `ln()`, `log(base)`,
  `power(exponent)`, `round([precision])`, `sqrt()`, and `truncate()`
- Spec examples and domain-empty cases
- Decimal/Integer result type probes via `type().name`, `is Decimal`, and
  `is Integer`
- Empty input, multi-item input, non-numeric input, Quantity restrictions,
  invalid arity, invalid precision, and dynamic sibling arguments

## Finding

`QA-001` MEDIUM is open. §5.7.8 declares
`round([precision : Integer]) : Decimal` and says omitted precision defaults to
0. Both native C++ and forced Python fallback instead materialize omitted
precision as Integer:

- `1.round().type().name` -> `Integer`
- `1.round() is Decimal` -> `false`
- `1.round() is Integer` -> `true`
- Control: `1.round(0).type().name` -> `Decimal`

No other §5.7 mandatory behavior failed after correcting probe expectations
for public scalar wrappers.

## Handoff

Fix both native `fn_round()` and Python fallback `rround()` so omitted precision
returns Decimal while preserving equality behavior and row-resilient public
UDFs. Add parity coverage for omitted precision result type.
