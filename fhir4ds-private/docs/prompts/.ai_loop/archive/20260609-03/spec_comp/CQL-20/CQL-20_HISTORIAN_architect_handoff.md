# Architect Handoff - CQL-20 HISTORIAN

Structural result: pass after one high-severity translator-boundary issue was
fixed and verified.

Golden standard captured in `.temp/architect/golden_standard.md`: CQL aggregate
typing belongs at the translator boundary when element types are statically
known, public aggregate helpers keep list semantics, query/retrieve aggregate
paths preserve correct list folding and patient correlation, and direct helper
surfaces stay aligned across Python fallback, native-loaded, and no-Python
runtimes.

Audit finding resolved:
- `CQL20-HISTORIAN-001` confirmed that aggregate static validation was too
  conservative for simple known element expressions, including constructor
  calls. The remediation is general and scoped to type inference for aggregate
  validation; it does not change dynamic-source runtime behavior or row
  aggregate registration.

QA quality: sufficient. The HISTORIAN pass covered official aggregate
semantics, null/empty/default rules, Quantity unit-aware aggregation,
query-produced list sources, invalid static operands, direct helper behavior,
and three execution surfaces. No `RETRY_QA` needed.

Recommended next step: outer orchestrator should archive CQL-20 HISTORIAN and
launch CQL-20 EXPLORER.
