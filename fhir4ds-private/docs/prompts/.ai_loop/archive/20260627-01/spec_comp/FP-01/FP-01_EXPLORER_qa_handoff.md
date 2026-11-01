# QA Handoff - FP-01 EXPLORER

## Scope

SPEC COMPLIANCE CHUNK FP-01: FHIRPath §4.1 literals. EXPLORER pass focused on
pathological literal shapes across native DuckDB and forced Python fallback SQL
registration.

## Spec Grounding

Official FHIRPath §4.1 says DateTime literals combine Date and Time using a
full-date `yyyy-MM-DDT...` shape when time components are present. The same
section allows a bare trailing `T` after a year, year-month, or full date to
mark a partial DateTime. Therefore `@2014T` and `@2014-01T` are valid partial
DateTimes, while `@2014T14` and `@2014-01T14:30` are invalid literal shapes.

Spec source consulted fresh:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

## Hypotheses Tested

- Partial DateTime literals with time components after only year/year-month may
  drift between native and fallback parsers.
- FP-01 string escape fixes may regress escaped quote, slash, and combining
  Unicode scalar handling.
- Quoted/no-whitespace Quantity units and time-valued quantities may diverge
  between `fhirpath`, `fhirpath_json`, typed wrappers, and `fhirpath_is_valid`.

## Fresh Probe

Command:

```bash
python3 .temp/qa/fp01_explorer_fresh_probe.py
```

Result: failed before remediation. Native SQL returned
`fhirpath_is_valid('@2014T14') = false` and `fhirpath(...)=[]`; forced Python
fallback SQL raised `FHIRPathSyntaxError`/DuckDB `InvalidInputException` for the
same invalid literal shape instead of matching native empty/NULL row-resilient
results.

## Issues

- `QA-001` MEDIUM OPEN: forced Python fallback SQL UDFs throw for invalid
  partial DateTime-with-time literal shapes that native DuckDB treats as invalid
  row-resilient literal results.

## Files Updated During QA

- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`
- `fhir4ds-private/docs/prompts/.ai_loop/qa_handoff.md`
- `fhir4ds/fhirpath/AGENTS.md`
- `.temp/qa/fp01_explorer_fresh_probe.py`
