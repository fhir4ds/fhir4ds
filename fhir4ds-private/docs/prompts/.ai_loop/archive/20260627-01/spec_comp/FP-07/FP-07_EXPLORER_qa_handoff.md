# QA Handoff - FP-07 EXPLORER Fresh

Date: 2026-06-12

Chunk: FP-07 - FHIRPath §5.5.4 Date Conversion, §5.5.5 DateTime Conversion,
and §5.5.6 Decimal Conversion.

Personality: EXPLORER

Spec source checked: official HL7 FHIRPath continuous-build source,
`input/pages/index.md`, §4.1 Long literals, §5 function parameters,
§5.5.4, §5.5.5, and §5.5.6.

## Probe

Created fresh probe:

```bash
python3 .temp/qa/fp07_explorer_fresh_probe.py
```

The probe isolates native DuckDB/C++ and forced Python fallback registrations
in subprocesses and compares `fhirpath`, `fhirpath_text`, `fhirpath_json`,
`fhirpath_bool`, `fhirpath_date`, `fhirpath_timestamp`,
`fhirpath_number`, and `fhirpath_is_valid`.

## Issues Found

### QA-001 - MEDIUM - Native dynamic Date/DateTime format argument focus

Native DuckDB/C++ evaluates `toDate([format])`,
`convertsToDate([format])`, `toDateTime([format])`, and
`convertsToDateTime([format])` format arguments against the converted source
string instead of the outer invocation focus. Forced Python fallback returns
the expected formatted Date/DateTime values.

Examples:

```fhirpath
rawDate.toDate(dateFmt)
rawDateTime.toDateTime(dateTimeFmt)
items.select(rawDate.toDate(dateFmt))
@2015-02-04.toDateTime(bogusFmt)
```

Expected: the dynamic format expression is evaluated as a normal FHIRPath
argument expression, and non-String Date/DateTime inputs ignore the format
parameter.

Actual native result: empty public result with `fhirpath_is_valid=true`.

### QA-002 - MEDIUM - Long boundary parity in Decimal conversion

Forced Python fallback accepts out-of-range positive Long literal
`9223372036854775808L.toDecimal()` as valid. Native rejects that positive
out-of-range value, but also rejects the valid signed minimum
`(-9223372036854775808L).toDecimal()`. Native max-Long Decimal conversion
also exposes binary double/scientific text instead of exact Decimal text.

Spec basis: §4.1 defines Long as `-2^63` through `2^63-1`; §5.5.6 allows
Integer, Long, and Decimal input to `toDecimal()` and
`convertsToDecimal()`.

## Handoff

`evolution.json` has two open MEDIUM issues and `phase` is now `FIX`.
