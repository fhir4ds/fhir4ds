# Architect Handoff - CQL-09 SKEPTIC

Golden standard written to `.temp/architect/cql09_skeptic/golden_standard.md`.
The remediation stays inside the CQL translation layer and preserves the
existing DuckDB registration boundary: translated SQL is executed unchanged
against native-loaded and forced Python fallback connections. The original
failures were semantic-dispatch bugs, not adapter or DQM concerns.

Structural assessment: healthy after remediation. `between` now delegates to
the same comparison paths as direct `>=`/`<=`, preventing duplicated Quantity or
temporal rules. Generic equivalence now owns the CQL-specific behavior that SQL
cannot provide directly. The mixed primitive literal guard prevents DuckDB
coercion from leaking into CQL list/tuple equivalence.

Issue count: 2 resolved spec violations, 0 open, 0 deferred, 0 architect vetoes.
QA was sufficient for this SKEPTIC pass: it covered adversarial Quantity,
string, list, tuple, temporal, native/fallback parity, and generated SQL
execution. `RETRY_QA` is not required.
