# Architect Handoff — CQL-22 SKEPTIC launch

Architecture review of the Message implementation (translator folding in
fhir4ds/cql/translator/expressions/_functions.py::_translate_message +
_validate_message_signature_args; runtime CQLMessage macro in
fhir4ds/cql/duckdb/macros/math.py + Python UDF cqlMessage in udf/math.py):
- Layering respected: static type guardrails at translation, runtime severity decision in a
  single SQL macro used by both engine modes (no divergence found between paths).
- Constant-folding of literal-false conditions and non-Error literal severities to bare source
  is semantically sound (spec: "performs no processing at all").
- QA-001 (informational message channel) accepted as INTENDED design gap for a SQL-compiled
  engine; fixtures green; documented in AGENTS.md.
No RETRY_QA. Recommend clean exit.
