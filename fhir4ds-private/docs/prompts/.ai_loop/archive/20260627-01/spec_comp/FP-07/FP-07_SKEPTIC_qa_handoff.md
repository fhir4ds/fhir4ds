# QA Handoff - FP-07 SKEPTIC

Date: 2026-06-12

## Scope

Fresh inner-loop QA for SPEC COMPLIANCE CHUNK FP-07 using only the current source tree and current `evolution.json`.

Focus:
- FHIRPath §5.5.4 Date Conversion: `toDate()`, `convertsToDate()`
- FHIRPath §5.5.5 DateTime Conversion: `toDateTime()`, `convertsToDateTime()`
- FHIRPath §5.5.6 Decimal Conversion: `toDecimal()`, `convertsToDecimal()`
- Native DuckDB/C++ vs forced Python fallback parity where both exist

Spec source:
- Official HL7 FHIRPath source fetched to `.temp/qa/fp07_fhirpath_spec.md`
- URL: `https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`

## SKEPTIC Hypotheses

1. Current source may still enforce older zero-arity signatures for Date and DateTime conversion despite current optional `format : string`.
2. Native and fallback may reject valid formatted date strings before conversion logic sees them.
3. The spec says format is ignored for non-string inputs; arity validation may wrongly reject literal Date/DateTime inputs with a format argument.
4. Decimal conversion likely still has strict zero-arity and should reject arguments.
5. STU Long literal support may be missing even though Decimal Conversion includes Long inputs.
6. Native and fallback may format Decimal string conversion outputs differently for trailing zero precision.

## Fresh Probe

Created and ran:

```bash
python3 .temp/qa/fp07_skeptic_fresh_probe.py
```

Result: failed as expected, opening two issues.

## Findings

### QA-001 - MEDIUM - Date/DateTime converters reject the current optional format argument

Current HL7 FHIRPath defines:
- `toDate([format : string]) : Date`
- `convertsToDate([format : string]) : Boolean`
- `toDateTime([format : string]) : DateTime`
- `convertsToDateTime([format : string]) : Boolean`

The current implementation rejects all one-argument forms as invalid in both native and forced fallback. Examples from the probe:

```text
dateText.toDate('dd-MM-yyyy') -> got empty/invalid, expected 2024-01-15
dateText.convertsToDate('dd-MM-yyyy') -> got empty/invalid, expected true
dtText.toDateTime('dd-MM-yyyy HH:mm:ss.SSS') -> got empty/invalid, expected 2024-01-15T23:30:05.123
dtText.convertsToDateTime('dd-MM-yyyy HH:mm:ss.SSS') -> got empty/invalid, expected true
@2024-01-15.toDate('bogus') -> got empty/invalid, expected 2024-01-15 because format is ignored for non-string input
```

Likely roots:
- `fhir4ds/fhirpath/engine/invocations/__init__.py` has zero-arity metadata for the four functions.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp` rejects those functions when `arg_count != 0`.
- `misc.to_date()` and `misc.to_date_time()` have no format parameter path.

### QA-002 - MEDIUM - Long literal Decimal Conversion support is missing

Current HL7 FHIRPath §4.1 defines STU Long literals such as `42L`, and §5.5.6 Decimal Conversion includes Long inputs and examples:

```text
42L.toDecimal()
42L.convertsToDecimal()
```

Fresh probing showed native reports these expressions invalid/empty and the forced fallback throws through a result UDF path for `42L.toDecimal()`.

Likely roots:
- FHIRPath lexers/parsers do not recognize Long literal suffixes.
- There is no Long value type boundary feeding `toDecimal()` / `convertsToDecimal()`.

## Notes For Remediation

- Do not rely on older local FP-07 notes that describe zero-arity Date/DateTime converters as correct; the current fetched HL7 source now defines optional format parameters.
- Required format codes include at least `yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`, `S[+]`, `a`, and `Z`; optional codes may be deferred if documented.
- Decimal `toDecimal()` / `convertsToDecimal()` remain zero-argument.
- The probe also observed native/fallback public string output differences for `'+1.50'.toDecimal()` (`1.5` vs `1.50`). I did not open this as a spec bug because the primary decimal value is equivalent and this may be a display-normalization issue, but it is worth keeping in mind when adding assertions.
