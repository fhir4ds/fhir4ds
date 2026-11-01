# QA Handoff — CQL-22 SKEPTIC launch (iteration 1)

Chunk: CQL 1.5 Errors and Messaging — Message(source, condition, code, severity, message).

Spec verified against CQL 1.5/2.0 Appendix B "Errors and Messaging — Message" (normative text
fetched live): signature Message(source T, condition Boolean, code String, severity String,
message String) T; source passes through unmodified; condition true -> message generated;
only severity 'Error' stops evaluation; default severity Message when omitted; code is a
token (string or integer).

Probes (all on BOTH python-fallback and C++-backed connections; identical results):
- Source pass-through exact: Message(5, true, 'c', 'error', 'm') raises (Error); Warning/Trace/
  unknown severity/4-arg form return 5; null source passes through as null (null+Error raises).
- Case-insensitive 'ERROR' raises; 'Fatal' passes through (spec: only Error stops evaluation).
- Condition handling: literal false -> folded to source; runtime parameter condition default
  false -> source; parameter overridden true + Error -> raises. Null condition -> no message
  (COALESCE(condition,FALSE)) — matches "if condition is true, generated; otherwise no processing".
- Message in where clause over [Observation]: Error severity raises on non-final rows;
  Warning severity filters correctly (o1 kept, o2 excluded), source rows unaffected.
- Uncertain sources: imprecise birthDate '1980' -> Message passes the uncertainty interval
  {"start":39,"end":40,...} through unchanged; precise birthDate -> 39. List/DateTime/Quantity
  sources pass through with type fidelity (typeof INTEGER preserved, list [1,2,3] preserved).
- Arity/typing guardrails: >5 args rejected; non-Boolean condition, non-String severity/message
  rejected statically; integer code token accepted per spec.

Existing suite: fhir4ds/cql/duckdb/tests/integration/test_message_parity.py 12/12 passed.
Official fixtures: CqlErrorsAndMessagingOperatorsTest.xml 4/4 passed in conformance run.

Findings:
- QA-001 (LOW, INTENDED): informational message channel (Trace/Message/Warning surfacing to the
  calling environment) is unimplemented — inherent to a translate-to-SQL engine with no logging
  channel; official fixtures do not pin it; spec PH-trace note acknowledged. Documented, not forced.
- Zero non-terminal CRITICAL/HIGH/MEDIUM issues.
