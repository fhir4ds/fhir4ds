# CQL-14 SKEPTIC Architect Handoff

Architectural guardrail added:
- CQL current-clock and precision helpers are public compatibility surface. Keep `TimeOfDay()` and `dateTimeTimeOfDay()` as CQL time text with a leading `T`.
- Direct `dateTimeSame*` helpers must not maintain separate semantics from `cqlSame*P`; they should share timezone normalization, uncertainty propagation, and invalid precision handling.
- Invalid precision strings return NULL consistently across forced Python fallback, native-loaded registration, and no-Python/browser-style C++ surfaces.
- Time constructor type validation is a translator boundary for statically known Boolean/Decimal components; runtime range invalidity should remain row-resilient NULL.
- Native C++ date/time quantity helpers must match Python fallback for fractional day/week date-only arithmetic, not just hour-or-finer DateTime values.

Residual risk:
- `week` precision is currently treated as invalid for same/on-or precision helpers and returns NULL consistently. If future CQL support defines week precision semantics, implement it deliberately in both Python and C++ helpers with parity tests.
