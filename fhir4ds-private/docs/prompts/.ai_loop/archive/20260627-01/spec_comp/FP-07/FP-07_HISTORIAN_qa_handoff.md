# QA Handoff - FP-07 HISTORIAN

Date: 2026-06-12

## Scope

Fresh HISTORIAN pass for SPEC COMPLIANCE CHUNK FP-07:
FHIRPath §5.5.4 Date Conversion, §5.5.5 DateTime Conversion, and §5.5.6
Decimal Conversion.

Official spec source consulted:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

Relevant normative/spec-example points:
- `toDate([format : string])` and `convertsToDate([format : string])` accept a
  required subset of date/time format codes, use the format only for string
  inputs, extract Date directly from DateTime without timezone normalization,
  return empty/false for non-convertible singleton values, and signal an error
  for multi-item inputs.
- `toDateTime([format : string])` and `convertsToDateTime([format : string])`
  accept a required subset of format codes, convert Date to a DateTime with
  time components empty, preserve partial DateTime precision, and signal an
  error for multi-item inputs.
- `toDecimal()` and `convertsToDecimal()` accept Integer, Long, Decimal,
  Boolean, and convertible String singleton inputs. The current §5.5.6 examples
  explicitly include `'42L'.toDecimal()` and `'42L'.convertsToDecimal()` as
  successful string conversions.

## Probe

Created `.temp/qa/fp07_historian_fresh_probe.py`.

The probe compares the current bundled native DuckDB extension and a forced
Python fallback registration across public wrappers:
`fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_date`,
`fhirpath_timestamp`, `fhirpath_number`, and `fhirpath_is_valid`.

Covered:
- formatted Date strings: `dd-MM-yyyy`, `yyyyMMdd`, `yyyy-MM`, `yyyy/MM/dd`
- invalid formatted dates such as `31-02-2024`
- formatted DateTime strings with milliseconds, timezone offsets, and AM/PM
- invalid formatted DateTimes such as hour `24`
- Date/DateTime literal conversions with ignored format argument
- Decimal conversion from signed string, Boolean, Long literal, and multi-item
  singleton-error inputs
- spec-example string Long Decimal conversion

## Finding

`QA-001` - MEDIUM - OPEN

FHIRPath §5.5.6 examples require string Long Decimal conversion:
`'42L'.toDecimal()` should return decimal `42`, and
`'42L'.convertsToDecimal()` should return `true`.

Actual public DuckDB behavior in both native and forced fallback:

```text
'42L'.toDecimal() -> empty/NULL, fhirpath_is_valid=true
'42L'.convertsToDecimal() -> false, fhirpath_is_valid=true
```

Reproducer:

```bash
python3 .temp/qa/fp07_historian_fresh_probe.py
```

The probe exits `1` and reports the two §5.5.6 spec failures. All non-failing
matrix cases in the same probe matched native/fallback outputs and expected
behavior.

## Handoff

Move to FIX. The likely fix is to allow a String consisting of an optional sign,
digits, and uppercase `L` to flow through `toDecimal()` /
`convertsToDecimal()` as a Decimal in both Python fallback and native C++.
Keep malformed decimal/Long string forms invalid or false, including `1LL`,
`1.0L`, lowercase `1l`, embedded spaces, and exponent notation.
