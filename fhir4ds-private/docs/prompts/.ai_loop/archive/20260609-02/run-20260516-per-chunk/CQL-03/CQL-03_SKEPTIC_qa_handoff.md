# QA Handoff - CQL-03 SKEPTIC

Scope: Fresh CQL temporal and complex type audit for Date, DateTime, Time, Quantity, and Ratio. I did not inspect archived `spec_comp/**` workflow outputs.

SKEPTIC hypotheses tested:
- Regex-only temporal validation may accept invalid calendar/time values.
- DuckDB casts may erase DateTime precision or timezone text at the public SQL surface.
- Quantity conversion may throw on malformed numeric text instead of returning null/false.
- Ratio conversion may not support the spec string form `<quantity>:<quantity>`.
- Native-loaded and forced Python fallback DuckDB registrations may diverge.

Findings:
- `CQL03-SK-001`: Temporal `ConvertsTo*` accepted invalid calendar/time values, and `ToDateTime('2024-01-01T10:00:00+99:99')` returned a timestamp instead of null.
- `CQL03-SK-002`: Malformed quantity string `5..5 'cm'` raised in the Python conversion path instead of returning false/null.
- `CQL03-SK-003`: `ToRatio('1.0 ''mg'':2.0 ''mg''')` returned null, while JSON ratios with empty quantity objects were accepted as convertible.

Spec grounding: CQL v1.5.3 Appendix B states Date/DateTime/Time conversion strings must be correctly formatted and interpretable as valid values; invalid conversion checks return false and invalid conversions return null. Quantity strings use a decimal quantity grammar with optional quoted unit, and Ratio strings use `<quantity>:<quantity>` with valid numerator and denominator quantities.

QA correction from conformance: official CQL ToTime cases accept timezone suffixes (`Z` and `(+|-)hh:mm`) and return the local time-of-day with the offset ignored. The final remediation preserves that behavior while still rejecting invalid local times and malformed offsets.

Focused repros compared native-loaded CQL registration to forced Python fallback registration.
