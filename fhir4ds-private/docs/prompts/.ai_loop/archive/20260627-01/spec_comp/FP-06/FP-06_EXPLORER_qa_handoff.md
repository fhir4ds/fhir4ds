# QA Handoff: FP-06 EXPLORER

## Scope

Fresh QA targeted FHIRPath §5.5.1 `iif`, §5.5.2 Boolean Conversion, and
§5.5.3 Integer Conversion using only the current `evolution.json` and source
tree. Prior FP-06 artifacts were not used as proof.

## Spec Grounding

Official HL7 FHIRPath continuous-build source was checked for:

- `iif(criterion, true-result, otherwise-result)`: lazy branch evaluation,
  empty criterion selecting otherwise, singleton Boolean evaluation, no
  `iif`-local `$index`, and multi-item input/criterion errors.
- `toBoolean()` / `convertsToBoolean()`: Boolean, Integer 0/1, Decimal
  0.0/1.0 equivalents, documented case-insensitive string forms only, empty
  on failed conversion, false from `convertsToBoolean()` on failed singleton
  conversion, and multi-item errors.
- `toInteger()` / `convertsToInteger()`: Integer/Long passthrough, Boolean
  true/false to 1/0, signed integer string regex `(\+|-)?\d+`, empty/false for
  invalid strings or out-of-range values, and multi-item errors.

## Hypotheses

1. Numeric-zero `iif` criteria might regress to Boolean false in Python
   fallback because Python equates `0 == False`.
2. Native and fallback result UDFs might diverge after the FP-06 invalid
   Integer/result-wrapper row-resilience fixes.
3. Dynamic resource values might bypass strict Boolean/Integer conversion
   shape checks that literal cases already cover.
4. Multi-item dynamic conversion inputs might confuse `fhirpath_is_valid()`
   with data-dependent public row resilience.
5. `iif` branch laziness and `$index` preservation could diverge between
   native C++ and forced Python fallback.

## Execution

Created and ran `.temp/qa/fp06_explorer_fresh_probe.py`.

The probe constructs a bundled native DuckDB/C++ connection and a forced
Python fallback connection, then compares all public outputs:

- `fhirpath`
- `fhirpath_json`
- `fhirpath_text`
- `fhirpath_number`
- `fhirpath_bool`
- `fhirpath_is_valid`

Fresh matrix size: 46 expressions.

## Result

No issue opened.

Native and forced Python fallback outputs matched all 46 expressions, including:

- `iif(0, 'T', (1|2).toInteger())`
- `iif(0.0, 'T', (1|2).toInteger())`
- `letters.select(iif($this = 'b', $index, {}))`
- dynamic `toBoolean()` / `convertsToBoolean()` over string, integer,
  decimal, and multi-item resource values
- dynamic `toInteger()` / `convertsToInteger()` over Boolean, signed string,
  decimal-looking string, out-of-range string, decimal, and multi-item values
- invalid literal/result-wrapper boundaries such as
  `2147483648.toInteger()`, `-2147483649.convertsToInteger()`,
  `-1.convertsToInteger()`, `true.toBoolean(1)`, and `'1'.toInteger(2)`

## Validation

```bash
python3 .temp/qa/fp06_explorer_fresh_probe.py
```

Passed: `FP-06 EXPLORER fresh probe passed: 46 expressions`.

## Handoff

`evolution.json` has no QA issues for this pass. Proceed to FIX as a no-op
verification/bookkeeping phase, then ARCHITECT for final audit and closure.
