# QA Handoff - CQL-22 EXPLORER

Spec basis verified against the current CQL reference and logical specification.
`Message(source, condition, code, severity, message)` returns the input source
unchanged, but when condition is true and severity is `Error`, evaluation must
stop with a runtime error. Non-error severities continue.

Fresh probes were written to
`fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/cql22_explorer_probe.py` and
run against both forced Python fallback registration and native/C++ DuckDB
registration.

Finding:
- `QA-001` HIGH: `CQLMessage` returns SQL NULL instead of raising when severity
  is `Error` and `code` or `message` is NULL. Reproduced on both registrations
  with:
  - `SELECT CQLMessage('src', true, NULL, 'Error', 'boom')`
  - `SELECT CQLMessage('src', true, 'E', 'Error', NULL)`
  - `SELECT CQLMessage('src', true, NULL, 'Error', NULL)`

Additional explored cases:
- String/numeric condition inputs behaved consistently between backends, though
  direct SQL accepts DuckDB coercions outside the typed CQL surface.
- Tuple/list source preservation for non-error severities remained intact.
- Case-insensitive `Error` severity still raises; whitespace-padded severity is
  treated as non-error by the current macro.
