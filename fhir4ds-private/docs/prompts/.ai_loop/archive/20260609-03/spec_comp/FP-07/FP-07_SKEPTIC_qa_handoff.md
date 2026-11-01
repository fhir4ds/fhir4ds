# QA Handoff - FP-07 SKEPTIC

## Scope

FHIRPath N1 Section 5.5.4 Date Conversion, 5.5.5 DateTime Conversion, and
5.5.6 Decimal Conversion. Personality: SKEPTIC.

Spec source checked directly: https://hl7.org/fhirpath/N1/ lines 1015-1111.
The relevant functions have zero-argument signatures, accept empty input as
empty, signal errors for multi-item input, and restrict decimal string
conversion to `(+|-)?\d+(\.\d+)?`.

## Source-First Hypotheses

1. Native conversion dispatch still ignores arguments for FP-07 converters.
2. Forced fallback registry still allows old one-argument `convertsToX(value)`
   forms for Date, DateTime, and Decimal.
3. Native `toDecimal()` falls through to `toString()` for unsupported temporal
   values.
4. Forced fallback temporal conversion helpers do not recognize FP_Date and
   FP_DateTime literal objects.
5. Forced fallback `toDecimal()` returns empty instead of raising on multi-item
   input, causing `fhirpath_is_valid()` drift.

## Probe

Created and ran `.temp/qa/fp07_skeptic_probe.py`.

Coverage included native C++ extension and forced Python fallback for:

- valid Date, DateTime, Decimal conversion shapes
- invalid calendar dates and malformed DateTime components
- timezone offset hour/minute boundaries
- decimal grammar edges: exponent, trailing dot, leading dot, whitespace, NaN
- empty input, multi-item input, extra arguments, and global argument forms

Probe result: 59 cases, 10 native/fallback mismatches.

## Findings

`QA-001` MEDIUM: FP-07 zero-argument converters accept invalid arguments or
global argument forms. Native accepted extra arguments for `toDecimal`,
`toDate`, `toDateTime`, and `convertsToDecimal`; fallback accepted
`convertsToDecimal(2)` and global forms such as `convertsToDate(validDate)`.

`QA-002` MEDIUM: native `@2015.toDecimal()` returns `2015.0`; Date is not a
valid `toDecimal()` source type.

`QA-003` MEDIUM: forced fallback returns empty for Date/DateTime literal
conversions such as `@2015.toDate()` and `@2015-02-04.toDateTime()`.

`QA-004` MEDIUM: forced fallback reports
`fhirpath_is_valid('(1|2).toDecimal()') == true` instead of surfacing the
spec-mandated multi-item singleton error.

## Artifacts

- Probe: `.temp/qa/fp07_skeptic_probe.py`
- Log: `.temp/qa/fp07_skeptic_probe.log`
