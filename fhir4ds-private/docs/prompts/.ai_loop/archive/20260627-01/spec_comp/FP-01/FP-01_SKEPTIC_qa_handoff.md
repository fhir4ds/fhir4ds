# QA Handoff - FP-01 SKEPTIC

## Scope
- Chunk: FP-01, FHIRPath §4.1 Literals.
- Personality: SKEPTIC.
- Fresh artifacts only; no archived evidence reused.

## Spec Checked
- FHIRPath literals source: `HL7/FHIRPath` current `input/pages/index.md` and `input/resources/binary-grammar.json`.
- FHIR R4 dateTime primitive source: `https://hl7.org/fhir/R4/datatypes.html`.
- Relevant findings: Time literals have no timezone offset; string non-escape backslash prefixes are ignored; FHIR `dateTime` offsets are bounded to `00:00`-`13:59` or exactly `14:00`.

## Hypotheses Probed
- String escape table and non-escape backslash handling.
- Integer literal upper/lower bounds.
- Leap-day and malformed date validation.
- Time literal timezone rejection.
- DateTime timezone boundary around `+/-14:00`.
- Quantity literals with time-valued units and escaped UCUM units.

## Finding
- `QA-001` MEDIUM OPEN: DateTime literals with offsets beyond `+/-14:00`, such as `@2016-02-29T23:59:59.123+14:01` and `@2016-02-29T23:59:59.123-14:01`, are accepted by both native DuckDB and forced Python fallback `fhirpath_is_valid()`.

## Validation Run
- `python3 .temp/qa/fp01_skeptic_probe.py` currently fails only on `QA-001`.
