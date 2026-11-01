# Architect Handoff: FP-17 HISTORIAN

Golden standard: Boolean logic must share one semantic contract across native
C++, forced Python fallback, public DuckDB wrappers, direct helper APIs, and
`fhirpath_is_valid()`. The contract is §4.5 singleton Boolean evaluation,
§6.5 truth-table empty propagation, and §6.8 precedence. Root `not()` is a
valid zero-argument function over current focus; argument-bearing `not(...)`
forms are invalid.

Audit result: structurally sound for this chunk. The existing FP-17 SKEPTIC
remediation generalized correctly: native and fallback paths agree on official
truth tables, precedence, singleton non-Boolean truthiness, multi-item
row-resilient errors, and `not()` arity. No new architecture finding was logged.

QA enforcer gate: no retry. QA covered official examples, edge truth-table
cells, parser precedence, backend parity, direct helpers, invalid arity, and
full conformance.

Issue counts: CRITICAL 0, HIGH 0, MEDIUM 0, LOW 0.

Recommended fix order: none for FP-17 HISTORIAN.
