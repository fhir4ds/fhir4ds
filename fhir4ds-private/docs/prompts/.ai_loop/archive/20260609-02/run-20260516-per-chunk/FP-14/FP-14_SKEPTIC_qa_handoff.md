# QA Handoff - FP-14 SKEPTIC

## Scope

- Chunk: FP-14
- Spec: FHIRPath §6.2 Comparison
- Operators: `>`, `<`, `<=`, `>=`
- Personality: SKEPTIC

## Spec Grounding

Verified against the official FHIRPath Normative Release v2.0.0:

- §6.2 defines comparison for strings, integers, decimals, quantities, dates, datetimes, and times.
- Empty operands return empty.
- Both operands must be singleton collections; multi-item operands are errors, which public DuckDB wrappers expose as empty/NULL.
- Partial Date/DateTime/Time values with different precision compare to empty.
- §5.5 conversion table allows implicit Integer-to-Decimal and numeric-to-Quantity conversions, but String-to-Integer/Decimal is explicit only.

## Hypotheses Tested

1. Numeric-looking strings may be coerced during comparison instead of staying strings.
2. Native C++ and forced Python fallback may disagree on Boolean ordering (`false < true`, `true > false`).
3. Partial temporal precision may return Boolean instead of empty.
4. Multi-item comparison operands may use the first item instead of singleton enforcement.
5. Quantity comparisons may fail unit conversion or compare incompatible dimensions.

## Findings

### QA-001 - HIGH - Python fallback coerces numeric-looking strings in comparison

Reproducer:

```sql
SELECT fhirpath('{}'::JSON, '''10'' < ''2''');
SELECT fhirpath('{}'::JSON, '''10'' > 2');
```

Observed:

- Native C++: `'10' < '2'` -> `['true']`; `'10' > 2` -> empty/NULL.
- Forced Python fallback: `'10' < '2'` -> `['false']`; `'10' > 2` -> `['true']`.

Expected:

- String-vs-string comparison is lexical, so `'10' < '2'` is true.
- String-vs-number is not implicitly convertible, so comparison returns empty/NULL.

Likely source:

- `fhir4ds/fhirpath/engine/invocations/equality.py::typecheck()` converts numeric-looking strings with `_try_convert_to_number()` before comparison.

## Passing Probes

- Boolean comparison parity: `true > false`, `false < true`.
- Empty operand propagation: `{ } <= 1`, `1 >= { }`, null field comparisons.
- Multi-item operand singleton handling: `1.combine(2) < 3`, `1 < 2.combine(3)`.
- Temporal precision empties: `@2018-03 > @2018-03-01`, `@2018-03-01T10 > @2018-03-01T10:30`, `@T10 > @T10:30`.
- Quantity conversion: `4 'm' > 4 'cm'`, `4 'cm' < 4 'm'`; incompatible `1 'cm2' > 1 'cm'` empty.

## Validation Run

Exploratory native-vs-forced-fallback DuckDB probes were run from `.temp/qa/` using fresh synthetic resources. Full regression/conformance validation is deferred to remediation after the fix.

## Final QA Exit Check

After remediation and architecture audit, all issues are terminal and the focused comparison parity regression was rerun:

- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q` -> 2 passed.

No new FP-14 issues were opened during the final QA state check.
