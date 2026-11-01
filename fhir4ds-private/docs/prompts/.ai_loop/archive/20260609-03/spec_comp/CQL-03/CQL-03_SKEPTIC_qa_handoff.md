# QA Handoff: CQL-03 SKEPTIC

Chunk: CQL — Types - Temporal and Complex
Personality: SKEPTIC
Iteration: 1

## Spec Basis

- CQL 1.5.3 Appendix B defines `Date`, `DateTime`, `Time`, `Quantity`, and `Ratio`; DateTime/Time values are bounded temporal values, Quantity has required Decimal `value`, and Ratio has required Quantity `numerator` and `denominator`.
- CQL language semantics describe timezone offset as a bounded decimal-hour component; offsets beyond the supported upper bound, such as `+14:01`, are invalid.

## Hypotheses Tested

- Temporal conversion helpers might validate timezone shape but not the upper-bound minute component.
- JSON-shaped Quantity and Ratio helpers might treat numeric-looking strings as Decimal values.
- Public Ratio helper UDFs might return partial component data even when the component is not a valid Quantity.
- Translated `is`/`as` over Date, DateTime, Time, Quantity, and Ratio might drift from direct helper behavior.

## Evidence

Fresh probe: `.temp/qa/cql03_skeptic_probe.py`.

Findings logged in `evolution.json`:

- `QA-001` MEDIUM: `ConvertsToDateTime`, `ToDateTime`, `ConvertsToTime`, and `ToTime` accept `+14:01` offsets on both forced Python fallback and native-loaded registrations.
- `QA-002` HIGH: JSON Quantity/Ratio surfaces accept string-valued numeric components, and Ratio unit helpers return units for components missing required Quantity `value`. `ratioValue` also diverges between forced Python fallback and native C++ for numeric-string component values.

Validated non-findings:

- Static translated `is`/`as` checks for Date, DateTime, Time, Quantity, and Ratio matched expected type-assertion behavior across forced Python fallback and native-loaded connections.
- Literal/runtime temporal constructors reject invalid calendar/time component ranges in the tested cases.
