# QA Handoff — FP-08 HISTORIAN (iteration 1, 2026-08-17)

Chunk: FHIRPath §5.5.7 toQuantity/convertsToQuantity, §5.5.8
toString/convertsToString, §5.5.9 toTime/convertsToTime.

## Method
71 + 42 fresh dual-path probe cases (native C++ extension loaded by
absolute path vs forced Python fallback), PYTHONPATH=/mnt/d/fhir4ds.
Probes: /mnt/d/fhir4ds/.temp/qa/fp08_historian_2026_08_17/probe{,2}.py.
Spec tables re-verified against hl7.org/fhirpath N1 §5.5.7-§5.5.9;
official R4 fixtures re-checked (tests-fhir-r4.xml lines 274-414: all
toQuantity fixtures are equality-based, none pin conversion display
text).

## SKEPTIC fix re-verification (all intact, spec-correct, regression-free)
- QA-001 duration table: year->day 365, month->day 30, day->month 1/30,
  year->week 52.14285714285714285714285714, year<->month direct 12,
  plural args, UCUM cross-conversion still rejected, roundtrips stable.
- QA-002 28-sig-digit ROUND_HALF_EVEN rendering confirmed on fresh
  variants ((1 'ms')->'s', 1/3 day->hour, string-input 'day'->week).
- QA-003 toTime T-prefixed partial forms: T14:34, T14, bare 14 all
  convert and compare equal to literals in both engines.

## Verified clean (fresh, zero parity diffs)
- convertsToQuantity(unit-arg) routing incl. the duration table
  (year->day true, year->'s' false, kg->g/g->m, plurals, case-sensitivity,
  incompatible dims, decimal values, no-arg string form).
- Conversion-result equality/arithmetic chaining: (1 year).toQuantity('day')
  = 365 days; + 5 days -> 370 day; inside where/select/all/iif/repeat
  iteration functions; resource-driven valueQuantity/valueString inputs.
- toString/convertsToString: all literal types, empty/multi-item doctrine,
  converted-quantity rendering, Z-suffix DateTime, canonical T-less Time.
- toTime/convertsToTime: full grammar matrix (bare/T-prefix, partial,
  ms fractions, lowercase-t/tz/range rejection), passthrough,
  convertsToTime truth table, field-driven substring().toTime().
- Malformed/wrong-typed unit args (empty string, Integer, Boolean,
  multi-item focus) behave identically (error -> empty in both).
- is_valid parity on 17 expression forms.

## Issues found
- QA-001 (MEDIUM, PARITY): terminating unit conversions render Decimal
  scale artifacts in the fallback (180 'cm'.toQuantity('m') -> "1.80 'm'"
  vs native "1.8 'm'"; also 6.0/1.000/8.000.../roundtrip cases). No
  fixture pins display; native's trimmed exact value is the consistent
  convention (kg->g "1000 'g'" already normalized via the g/mg path).
  Fix: apply FP_Quantity._normalize_quantity_value at the to_quantity
  conversion boundary (engine path).
- QA-002 (MEDIUM, SPEC_VIOLATION): direct helper
  fhir4ds.fhirpath.duckdb.functions.conversion.to_quantity does not use
  the §5.5.7 duration-spec table: to_quantity("1 'year'", "day") -> None
  while the engine returns 365 day. Fix: route _convert_quantity through
  conv_duration_to_spec first.

## Environment notes
- ~/.duckdb extension cache gave "Metadata mismatch" on LOAD even with
  identical md5s; LOAD by absolute path is reliable for probes.
- fhirpath() serializes booleans as strings ("true"/"false") — probe
  expectations must use string form.
