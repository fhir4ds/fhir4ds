# QA Handoff - FP-06 SKEPTIC

Chunk: FP-06, FHIRPath §5.5.1 iif, §5.5.2 Boolean Conversion, §5.5.3 Integer Conversion.
Personality: SKEPTIC.

Spec source checked: HL7 FHIRPath Normative Release v2.0.0, §5.5. The conversion section says conversion functions operate on single-item input collections, and the target signatures are `iif(criterion, true-result [, otherwise-result])`, `toBoolean()`, `convertsToBoolean()`, `toInteger()`, and `convertsToInteger()`. `iif` must short-circuit; Boolean conversion accepts only the listed Boolean, `0`/`1`, `0.0`/`1.0`, and case-insensitive string representations; Integer string conversion uses `(\\+|-)?\\d+`.

Hypotheses tested:
- Native conversion functions might use the first item of a multi-item collection.
- `iif` might eagerly evaluate unselected branches.
- Boolean conversion might over-accept strings or numeric values.
- Integer conversion might accept decimal-looking strings, whitespace, or overflow.
- `convertsToBoolean`/`convertsToInteger` might ignore invalid arguments because their implementation path had a custom one-parameter convenience mode.

Probe: `.temp/qa/fp06_skeptic_probe.py`, log `.temp/qa/fp06_skeptic_probe.log`.

Results:
- Native C++ and forced Python fallback matched across 30 focused cases.
- `iif` short-circuited evaluation as expected; invalid hidden functions still make `fhirpath_is_valid=false`, matching the existing validation contract.
- `toBoolean()` and `toInteger()` handled valid/invalid scalar conversions and multi-item row resilience consistently.
- Found `QA-001` MEDIUM: both backends accept invalid argument-bearing `convertsToBoolean`/`convertsToInteger` calls. Reproducers:
  - `'true'.convertsToBoolean(2)` returns `['false']` and `is_valid=true`.
  - `'1'.convertsToInteger(2)` returns `['true']` and `is_valid=true`.
  - `convertsToBoolean(strTrue)` returns `['true']` and `is_valid=true`.
  - `convertsToInteger(strInt)` returns `['true']` and `is_valid=true`.

Expected: those expressions should be invalid for FP-06 because `convertsToBoolean()` and `convertsToInteger()` have no parameters. Public result UDFs should return empty/NULL and `fhirpath_is_valid()` should be false.
