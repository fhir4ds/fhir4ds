# QA Handoff — FP-11 SKEPTIC

## Scope

FHIRPath §5.7 Math (STU): `abs()`, `ceiling()`, `exp()`, `floor()`, `ln()`,
`log(base)`, `power(exponent)`, `round([precision])`, `sqrt()`, and
`truncate()`.

Spec source verified directly: HL7 FHIRPath Normative Release §5.7. The section
states math functions operate on singleton collections; unless otherwise noted,
multi-item input or incompatible item types signal an evaluation error. It also
defines exact function signatures, empty propagation, domain-empty cases, and
`power()` Integer-vs-Decimal result shape.

## SKEPTIC Hypotheses

1. Native C++ may repeat the prior chunk pattern of missing exact arity guards.
2. Sparse `fhirpath_is_valid()` evaluation may hide invalid concrete math
   arguments or non-numeric constants.
3. Domain errors such as negative `sqrt`, non-positive `ln`, bad `log` base,
   and impossible powers may accidentally raise instead of returning empty.
4. Dynamic sibling arguments for `log`, `power`, and `round` may be evaluated
   in the wrong focus, like earlier string-function bugs.
5. Integer/Decimal result shape may be lost because native and fallback both
   route through host floating/Decimal math.

## Probe

Created and ran `.temp/qa/fp11_skeptic_probe.py`.

Initial result:
- Cases: 52
- Native vs forced Python fallback mismatches: 19
- Expectation failures: 6, of which representation-only text expectations were
  folded into `QA-004` only where the spec defines result type.

## Findings

`QA-001` HIGH: native exact arity for FP-11 math is missing or incomplete.
Malformed calls such as `1.abs(2)`, `1.exp(2)`, `10.log()`,
`10.log(2, 3)`, `2.power()`, `2.power(3, 4)`, `2.round(1, 2)`,
`2.sqrt(1)`, and `2.truncate(1)` are accepted or considered valid by the
native extension.

`QA-002` MEDIUM: native math functions return empty and report
`fhirpath_is_valid=true` for concrete incompatible inputs such as
`'2.5'.sqrt()`, `true.abs()`, `5 'mg'.sqrt()`, and `5 'mg'.ceiling()`.
Per §5.7 these should be evaluation errors; public result UDF row resilience can
still convert them to empty/NULL.

`QA-003` MEDIUM: native `p.log(base)` evaluates `base` against the source scalar
instead of the outer invocation focus and returns empty while fallback returns
`1.3219280948873624`.

`QA-004` MEDIUM: `2.power(3)` is materialized as Decimal text/json shape
(`8.0`) in both native and forced fallback, but §5.7.7 says integer power with
integer operands returns an Integer.

## Validation Artifacts

- `.temp/qa/fp11_skeptic_probe_initial.log`
- `evolution.json` updated with `QA-001` through `QA-004` as `OPEN`.
