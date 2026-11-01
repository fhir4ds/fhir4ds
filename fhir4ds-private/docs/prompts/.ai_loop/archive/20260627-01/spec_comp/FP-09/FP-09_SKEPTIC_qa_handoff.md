# QA Handoff - FP-09 SKEPTIC

## Scope

Fresh pass for SPEC COMPLIANCE CHUNK FP-09: FHIRPath §5.6.1-§5.6.5 String
Manipulation (Search): `indexOf(substring)`, `substring(start[, length])`,
`startsWith(prefix)`, `endsWith(suffix)`, and string-function
`contains(substring)`.

Spec source checked: official HL7 FHIRPath continuous-build source,
`input/pages/index.md`, lines covering String Manipulation. Normative
expectations used: these functions operate on singleton String input; indexes
and substring bounds are measured in Unicode scalar values; empty input or
empty required arguments return empty; `indexOf('')` returns `0`;
`startsWith('')`, `endsWith('')`, and `contains('')` return true; multi-item
or wrong-type runtime inputs signal evaluation errors to the calling
environment.

## SKEPTIC Hypotheses

1. Native search functions might still evaluate dynamic arguments against the
   source String rather than the outer resource focus.
2. Native or fallback might count UTF-8 bytes instead of Unicode scalar values
   for `indexOf()` and `substring()`.
3. Empty required arguments could collapse to false or `-1` rather than empty.
4. Runtime wrong-type arguments might throw through public DuckDB UDFs instead
   of returning row-resilient empty/NULL outputs.
5. Static validation might confuse string-function `contains()` with the
   collection `contains` operator.
6. Duplicate-eliminating literal unions might be classified as multi-item
   arguments even when the effective singleton value is valid.

## Results

No issue opened.

Fresh probe: `.temp/qa/fp09_skeptic_fresh_probe.py`.

Validation run:

```bash
python3 .temp/qa/fp09_skeptic_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py -q
```

Results:

- Fresh native-vs-forced-fallback probe passed, 39 expressions.
- Focused parity pytest passed, 6/6.

## Notes For Remediation

No remediation is required. Dynamic runtime type errors such as
`s.indexOf(badTerm)` should keep `fhirpath_is_valid()` true because that UDF
validates expression form, not a specific sample resource evaluation.
