# QA Handoff - FP-08 EXPLORER

## Scope

FHIRPath Section 5.5.7 Quantity Conversion, Section 5.5.8 String Conversion,
and Section 5.5.9 Time Conversion for:

- `toQuantity([unit])`
- `convertsToQuantity([unit])`
- `toString()`
- `convertsToString()`
- `toTime()`
- `convertsToTime()`

Personality: EXPLORER.

## Spec Grounding

Source: HL7 FHIRPath Normative Release v2.0.0, https://hl7.org/fhirpath/N1/.

Relevant rules used:

- Section 4.4 says single-input functions passed an empty collection as an
  argument return an empty collection.
- Section 5.5.7 defines `toQuantity([unit : String])` and
  `convertsToQuantity([unit : String])`; the optional `unit` argument is a
  singleton String unit selector, not a signal to ignore empty arguments.
- Sections 5.5.8 and 5.5.9 require singleton input, empty propagation,
  multi-item errors, and partial time precision preservation.

## Probe

Created and ran `.temp/qa/fp08_explorer_probe.py`.

Coverage included:

- escaped quoted Quantity units such as `10 'mg[Hg]'`
- invalid Quantity strings and malformed resource-backed Quantity objects
- resource-backed FHIR `valueQuantity` conversion and stringification
- compatible unit conversion `5 mg -> 0.005 g`
- empty, non-String, and multi-item optional unit arguments
- lazy `iif()` branches with invalid unselected Quantity unit arguments
- object/string `toString()` and `convertsToString()` surfaces
- partial Time precision, invalid time ranges, timezone suffixes, invalid arity,
  and multi-item runtime row resilience

Result before remediation:

- Cases: 35
- Native/fallback mismatches: 2
- Spec expectation failures against native: 0

## Finding

`QA-001` MEDIUM: forced Python fallback treats an empty optional Quantity unit
argument as if no unit argument was supplied.

Reproducer:

- `1.toQuantity({})`
- `1.convertsToQuantity({})`

Actual:

- Native C++: empty / empty
- Forced Python fallback: `1 '1'` / `true`

Expected:

- Both backends return empty. The empty argument is an empty singleton argument,
  so Section 4.4 empty argument propagation applies.

Likely root cause:

- Python `make_param()` returns `[]` for empty arguments.
- `misc.to_quantity()` and `misc.converts_to_quantity()` treat falsey `to_unit`
  values as absent optional arguments.
