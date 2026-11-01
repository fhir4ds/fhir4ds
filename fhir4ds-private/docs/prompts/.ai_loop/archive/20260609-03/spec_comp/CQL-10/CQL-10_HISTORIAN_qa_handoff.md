# QA Handoff - CQL-10 HISTORIAN

Scope: CQL Arithmetic Operators Part 1 (`Abs`, `Add`, `Ceiling`, `Divide`, `Floor`, `Exp`, `HighBoundary`, `Log`, `Ln`, `LowBoundary`).

Spec source: CQL Reference v1.5.3 Appendix B, arithmetic operators. `HighBoundary`/`LowBoundary` define omitted precision behavior, and `Log` has the two-argument signature `Log(argument Decimal, base Decimal)` while natural log is `Ln(argument Decimal)`.

Fresh probe: `.temp/qa/cql10_historian_probe.py`.

Findings:

- `QA-001` HIGH: optional-precision `HighBoundary` / `LowBoundary` is missing. Direct DuckDB calls such as `HighBoundary('1.587')` fail with a binder error, and translated CQL emits one-argument `HighBoundary(...)` / `LowBoundary(...)` calls that fail at execution. Expected default behavior is decimal scale 8, Date at authored precision, and DateTime/Time at millisecond precision.
- `QA-002` HIGH: `Log` arity is inverted at the public/translator boundary. Direct `Log(16, 2)` fails because the registered macro only supports one argument, while direct `Log(100)` returns a base-10 value and translated CQL `Log(100)` lowers to `Ln(100)`. The spec requires two arguments for `Log`; one-argument natural log must be spelled `Ln`.

Regression attention:

- Existing historical CQL-10 SKEPTIC Quantity arithmetic edge cases remain in scope; no new failure was observed there before remediation.
