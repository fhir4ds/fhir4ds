# QA Handoff — CQL-03 EXPLORER

Personality: EXPLORER

Scope: CQL temporal and complex types: Date, DateTime, Time, Quantity, and Ratio. The pass focused on edge combinations after SKEPTIC/HISTORIAN, especially constructor type boundaries, timezone decimal carry/bounds, malformed Quantity/Ratio internals, assertion chains, and native-loaded versus forced Python fallback parity.

Spec basis checked:
- CQL 1.5.3 Appendix B defines Date/DateTime/Time constructor signatures with Integer components and DateTime timezoneOffset as Decimal.
- The Logical Specification says DateTime and Time constructors build values from supplied components, no lower precision component may be specified below an unspecified precision, invalid temporal strings/conversions return null, and Quantity/Ratio values require their required components.

Fresh exploration:
- Direct helper parity for `ConvertsToDateTime`, `ToDateTime`, `ConvertsToTime`, `ConvertsToQuantity`, `ConvertsToRatio`, `ratioValue`, and `ratioNumeratorUnit`.
- Translated CQL for decimal timezone carry, out-of-range timezone offsets, partial DateTime precision, Quantity/Ratio `is`/`as`, and runtime constructor components.
- Native-loaded DuckDB and forced Python fallback were compared for all translated and public helper cases.

Finding:
- `QA-001` HIGH: expression-valued Date/DateTime/Time constructor components bypassed the literal-only type checks. Reproducers included `Date(2024, 1 = 1, 1)` and `DateTime(2024, 1 = 1, 1)` executing as valid dates, and `Time(1 = 1, 0, 0)` emitting invalid SQL. This violates the constructor signatures requiring Integer components and Decimal timezoneOffset.

Validation after remediation:
- `python3 .temp/qa/cql03_explorer_probe.py`: passed.
- Focused temporal/datetime/conversion parity: 30 passed.
- Temporal/Quantity/Ratio focused pytest: 94 passed.
- Native CQL SQL assertions: 782 passed.
- Full conformance: 2822/2822.
