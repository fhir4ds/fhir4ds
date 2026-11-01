# QA Handoff - FP-11 SKEPTIC

## Scope

Fresh spec-compliance pass for FHIRPath §5.7 Math (STU), using the current source tree and current `evolution.json` only.

Official spec source checked: HL7 FHIRPath continuous-build source, §5.7 Math.

## Hypotheses Probed

1. Quantity-capable math functions may still reflect older behavior that only allowed `abs()` on Quantity.
2. `power()` may preserve Integer type for integer inputs even though current §5.7 declares Decimal.
3. Argument expressions for `log(base)`, `power(exponent)`, and `round(precision)` may bind to the wrong focus.
4. Empty/domain-error cases may diverge between native C++ and forced Python fallback public UDFs.
5. Existing tests may encode prior STU wording and need updating rather than being treated as authoritative.

## Findings

### QA-001 - MEDIUM - OPEN

Current FHIRPath §5.7 says `ceiling()`, `floor()`, `round([precision])`, and `truncate()` accept Quantity inputs and return a Quantity with the same units. Fresh native and forced Python fallback probing found all four functions reject Quantity input and mark the expressions invalid.

Representative failures:

- `(1.1 'mg').ceiling()` returned empty/NULL and `fhirpath_is_valid=false`; expected `2 'mg'`.
- `(-1.1 'mg').floor()` returned empty/NULL and `fhirpath_is_valid=false`; expected `-2 'mg'`.
- `(1.56 'mg').truncate()` returned empty/NULL and `fhirpath_is_valid=false`; expected `1 'mg'`.
- `(1.55 'mg').round(1)` returned empty/NULL and `fhirpath_is_valid=false`; expected `1.6 'mg'`.

### QA-002 - MEDIUM - OPEN

Current FHIRPath §5.7 declares `power(exponent : Integer | Decimal) : Decimal` and states the result is always Decimal. Fresh native and forced Python fallback probing found `2.power(3)` and `p.power(exp)` return Integer type.

Representative failures:

- `2.power(3).type().name` returned `Integer`; expected `Decimal`.
- `2.power(3) is Decimal` returned `false`; expected `true`.
- `2.power(3) is Integer` returned `true`; expected `false`.

## Probe

Created `.temp/qa/fp11_skeptic_fresh_probe.py`.

Initial run:

```bash
python3 .temp/qa/fp11_skeptic_fresh_probe.py
```

Result: failed as expected with QA-001 and QA-002 evidence in both native C++ DuckDB and forced Python fallback paths.

## Handoff to Remediation

Update both the Python evaluator path and native C++ evaluator path. Existing `test_math_parity.py` contains assertions for prior behavior and should be revised to current §5.7 semantics. Rebuild and copy the bundled native extension after native changes.
