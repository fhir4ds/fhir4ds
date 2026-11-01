# QA Handoff - CQL-03 EXPLORER

Phase: QA
Personality: EXPLORER
Scope: CQL temporal and complex types: Date, DateTime, Time, Quantity, Ratio.

## Spec Anchors

- CQL v1.5.3 Appendix B defines Date/DateTime/Time partial precision and valid calendar/time ranges.
- `ToDate` and `ToDateTime` string overloads require ISO-formatted strings that represent valid date/datetime values; invalid inputs return null.
- `ToDate` accepts datetime-formatted strings and ignores the time portion.
- `Ratio` requires present numerator and denominator `Quantity` values; `Quantity.value` is Decimal.
- `as<T>` returns null when runtime type does not match; `is<T>` returns false when runtime type does not match.

## Exploration Performed

- Compared native-loaded CQL DuckDB registration with forced Python fallback registration for conversion and Ratio UDFs.
- Translated standalone CQL definitions and executed the generated SQL for `ToDate`, `ToDateTime`, `convert ... to Date`, `convert ... to DateTime`, temporal `is`/`as`, and Quantity `is`/`as`.
- Probed malformed calendar strings, partial precision strings, timezone-partial temporal strings, JSON-shaped Ratio values, malformed Quantity values, and spec string Ratio forms.
- Reproducer: `.temp/qa/cql03_explorer_repro.py`.

## Findings

1. `CQL03-EXPLORER-001` - MEDIUM - RESOLVED
   The translator lowers `ToDate`/`ToDateTime` and `convert ... to Date/DateTime` through local SQLRaw/TRY_CAST logic instead of the spec-aware DuckDB macro surface. Translated CQL returns null for valid partial precision (`ToDate('2014-01')`, `ToDateTime('2014')`) and returns invalid calendar strings unchanged (`ToDate('2024-02-30')`, `ToDateTime('2024-02-30')`). Direct public macros already behave correctly.

2. `CQL03-EXPLORER-002` - MEDIUM - RESOLVED
   Forced Python fallback Ratio UDFs throw for malformed numeric internals, while native-loaded registration returns NULL. `ratioValue` and `ratioNumeratorValue` need Decimal-shape guards so malformed internal JSON does not raise at row execution time.

## Suggested Regression Coverage

- Add translator execution parity tests for partial and invalid temporal conversion definitions, comparing native-loaded and forced Python fallback DuckDB connections.
- Add Ratio fallback/native parity tests for malformed numeric numerator/denominator values returning NULL rather than raising.

Both regressions were implemented during the FIX phase and verified by focused parity tests, broad CQL pytest, official CQL compliance, and full conformance.
