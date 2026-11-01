# QA Handoff - FP-13 HISTORIAN

## Scope

Fresh HISTORIAN pass for FHIRPath §6.1 Equality. I used the current
`evolution.json` and current source tree only, and anchored the probe imports to
`/mnt/d/fhir4ds` so it does not use an installed package copy.

Spec source: HL7 FHIRPath continuous-build source:
`https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`

Normative points checked:
- `=` returns empty if either operand is empty; singleton equality requires same
  or implicitly convertible types; multi-item equality compares ordered pairs.
- Numeric-to-Quantity unit `1` implicit comparison is shown by the official
  examples `23 = 23 '1'` and `23 ~ 23 '1'`.
- Quantity equality returns empty for non-commensurable units and for mixed
  calendar-vs-UCUM years/months.
- Quantity equivalence converts to the least granular unit and returns empty
  when conversion is empty.
- Date/Time equivalence differs from equality by returning false, not empty, on
  precision mismatch.
- String equivalence ignores case and maps Unicode whitespace one-for-one
  without trimming or collapsing repeated whitespace.

## Probe

Created and ran:

```bash
python3 .temp/qa/fp13_historian_fresh_probe.py
```

The probe compares native DuckDB/C++ registration and forced Python fallback
registration for `fhirpath`, `fhirpath_json`, `fhirpath_bool`, and
`fhirpath_is_valid`.

## Findings

### QA-001 - MEDIUM - OPEN

Numeric primitives are not implicitly compared as Quantity unit `1`.

Evidence from fresh probe:
- `23 = 23 '1'`: expected true; native/fallback returned empty/NULL.
- `23 != 23 '1'`: expected false; native/fallback returned empty/NULL.
- `23 ~ 23 '1'`: expected true; native/fallback returned false.
- `23 !~ 23 '1'`: expected false; native/fallback returned true.
- Resource-backed UCUM unit `1` Quantity cases fail the same way, including
  `component[0].value = 23` and `component.value = (23 | 24)`.

Likely location:
- Python: `fhir4ds/fhirpath/engine/invocations/equality.py`
- Native: `extensions/fhirpath/src/fhirpath/evaluator.cpp`

### QA-002 - MEDIUM - OPEN

Quantity equivalence over non-commensurable units returns false/true instead of
empty/NULL.

Evidence from fresh probe:
- `1 'cm' ~ 1 's'`: expected empty/NULL; native/fallback returned false.
- `1 'cm' !~ 1 's'`: expected empty/NULL; native/fallback returned true.

Likely location:
- Python: `fhir4ds/fhirpath/engine/invocations/equality.py`
- Native: `extensions/fhirpath/src/fhirpath/evaluator.cpp`

## Non-Findings

The fresh probe rechecked the current FP-13 SKEPTIC string and duration fixes
against current source imports:
- `'a  b' ~ 'a b'` is false.
- `' a' ~ 'a'` is false.
- `'É' ~ 'é'` is true.
- `1 year = 1 'a'` is empty/NULL.
- `7 days = 1 'wk'` is true.

Review-10 findings do not directly intersect this §6.1 equality chunk, except
that native extension freshness must be verified after any C++ fix.
