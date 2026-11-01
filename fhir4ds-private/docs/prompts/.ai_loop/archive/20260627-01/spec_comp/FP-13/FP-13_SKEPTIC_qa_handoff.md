# QA Handoff - FP-13 SKEPTIC

## Scope

Fresh QA for SPEC COMPLIANCE CHUNK FP-13, FHIRPath §6.1 Equality:
`=`, `!=`, `~`, `!~`, with emphasis on String equivalence, Quantity equality,
Quantity equivalence, and Date/Time equality/equivalence. Native DuckDB/C++ and
forced Python fallback paths were both exercised.

Official spec source used:
https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md

## Hypotheses Tested

1. String equivalence might collapse/trim whitespace instead of one-for-one
   Unicode White_Space normalization.
2. Native string equivalence might still use ASCII byte case/whitespace logic.
3. Time-valued Quantity equality might still use stale calendar-vs-UCUM rules.
4. `!=` / `!~` might not preserve empty/converse semantics.
5. Date/Time precision equality might have regressed around empty-vs-false.

## Probe

Created and ran:

```bash
python3 .temp/qa/fp13_skeptic_fresh_probe.py
```

Result: failed with two spec issues.

## Issues Opened

### QA-001 - MEDIUM - String Equivalence

`'a  b' ~ 'a b'` and `' a' ~ 'a'` returned true in both native and forced
fallback. §6.1 says String equivalence normalizes whitespace characters but
does not collapse repeated whitespace; leading/trailing whitespace is therefore
observable. Native also returned false while fallback returned true for
NBSP-vs-space and `'É' ~ 'é'`, showing Unicode parity drift.

### QA-002 - MEDIUM - Time-Valued Quantity Equality

The fresh probe found stale calendar-vs-UCUM behavior:

- `1 year = 1 'a'` and `1 month = 1 'mo'` returned false instead of empty.
- `1 week = 1 'wk'`, `7 days = 1 'wk'`, `1 hour = 60 'min'`, and
  `1 minute = 60 's'` returned false in at least one path instead of true.
- Forced fallback returned false while native returned true for
  `1 'a' = 12 'mo'`.

§6.1 says calendar year/month versus UCUM year/month equality is empty, while
week/day/hour/minute/second/millisecond calendar keywords are equal to their
UCUM counterparts by definition/conversion. `~` remained expected for the
sample year/UCUM equivalence case.

## Suggested Focus

Patch `fhir4ds/fhirpath/engine/invocations/equality.py` and native
`extensions/fhirpath/src/fhirpath/evaluator.cpp`. Add permanent regression
coverage to `test_equality_parity.py` and native `fhirpath.test`, then rebuild
and copy the bundled native extension.
