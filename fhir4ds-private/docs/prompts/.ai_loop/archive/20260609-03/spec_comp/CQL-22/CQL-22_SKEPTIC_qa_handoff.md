# QA Handoff: CQL-22 SKEPTIC

Scope: CQL Errors and Messaging, focused on `Message(source, condition, code, severity, message)`.

Spec anchor: CQL Reference v1.5.3 Appendix B states `Message` returns the input source unchanged, generates a message only when `condition` is true, and only `Error` severity stops evaluation with a runtime error; `Trace`, `Message`, and `Warning` continue evaluation.

Hypotheses tested:
- `CQLMessage` must exist in Python fallback, native-loaded, and no-Python/browser-style runtimes.
- False and null conditions must return source without evaluating as a runtime error.
- Non-error severities must return source.
- Error severity is case-insensitive in the existing public helper contract and raises.
- Source transport must preserve primitive/list/JSON-shaped Quantity and Interval values.

Finding:
- `CQL22-SKEPTIC-001` HIGH: no-Python/browser-style runtime has no `CQLMessage` function or pure SQL macro. Direct `SELECT CQLMessage('src', false, 'E', 'Error', 'boom')` fails with a catalog error, and translated CQL `Message` expressions that cannot be folded emit `CQLMessage`, so browser-style SQL execution cannot support the CQL Message operator.

Probe:
- `.temp/qa/cql22_skeptic_probe.py`
