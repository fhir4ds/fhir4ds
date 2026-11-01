# QA Handoff: FP-01 EXPLORER

Iteration: 1
Personality: EXPLORER
Scope: FHIRPath N1 §4.1 literals across DuckDB native C++ and forced Python fallback.

## Spec Grounding

- FHIRPath N1 §4.1 defines Boolean, String, Integer, Decimal, Date, Time, DateTime, and Quantity literal forms.
- §4.1.5/§4.1.7 temporal literal ranges start at year 0001; year 0000 is outside the supported Date/DateTime domain.
- §4.1.2 string escape rules apply to single-quoted string tokens. Quantity units in §4.1.8 use single-quoted string unit tokens or calendar duration keywords, so quoted units must unescape the same way ordinary strings do.
- §4 expressions allow literals, operators, and invocations to be chained; literal collection de-duplication must not crash on mixed temporal and non-temporal items.

Spec reference used: https://hl7.org/fhirpath/N1/

## Probe

Scratch probe: `.temp/qa/fp01_explorer_literal_probe.py`

The probe compared all public DuckDB FHIRPath wrappers on native C++ and forced Python fallback:
`fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_number`,
`fhirpath_date`, `fhirpath_timestamp`, `fhirpath_quantity`, and `fhirpath_is_valid`.

## Findings

- `QA-FP01-EXPLORER-001` MEDIUM: both backends accepted year-zero temporal literals such as `@0000-01-01`.
- `QA-FP01-EXPLORER-002` MEDIUM: forced Python fallback did not unescape quoted Quantity unit strings such as `10'\u006Dg'`.
- `QA-FP01-EXPLORER-003` MEDIUM: both backends accepted empty quoted Quantity units such as `1 ''`.
- `QA-FP01-EXPLORER-004` MEDIUM: forced Python fallback crashed/returned empty for a valid mixed literal chain using `|`, `select($this.toString())`, and `count()`.

Post-fix probe result: 23 cases, 0 native/fallback mismatches, 0 spec failures.
