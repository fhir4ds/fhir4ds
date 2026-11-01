# QA Handoff - FP-07 EXPLORER

Scope: FHIRPath Date, DateTime, and Decimal conversion functions (`toDate()`, `convertsToDate()`, `toDateTime()`, `convertsToDateTime()`, `toDecimal()`, `convertsToDecimal()`).

Spec checked: FHIRPath Normative Release N1 sections 5.5.4, 5.5.5, and 5.5.6. Date/DateTime conversion accepts Date/DateTime/String only, with non-convertible strings returning empty/false; Decimal conversion accepts Integer/Decimal/String/Boolean with string regex `(\+|-)?\d+(\.\d+)?`.

Exploration performed:
- Read native C++ conversion implementation and Python fallback/core conversion paths.
- Created and ran `.temp/qa/fp07_explorer_probe.py`.
- Compared public DuckDB native extension registration against forced Python fallback registration.
- Exercised malformed DateTime-like strings, numeric inputs to Date/DateTime conversions, conversion predicate companions, and multi-item/chained conversion cases.

Findings:
- `QA-FP07-EXPLORER-001` HIGH: native `toDate()` and `toDateTime()` coerce Integer `2015` through `toString()` and return `2015`/`2015T`; forced Python fallback returns empty. `convertsToDate()`/`convertsToDateTime()` return false, so the conversion and convertibility predicate disagree.
- `QA-FP07-EXPLORER-002` HIGH: native `toDate()` truncates malformed DateTime-looking strings such as `2015-02-04T99` and `2015-02-04Tbogus` to `2015-02-04`; forced Python fallback returns empty. Public native `convertsToDate()` also returned true for `2015-02-04Tbogus` in the bundled extension.

No Decimal conversion bug was found in this EXPLORER pass; regex edge cases from prior fixes matched between native and fallback in the focused probe.
