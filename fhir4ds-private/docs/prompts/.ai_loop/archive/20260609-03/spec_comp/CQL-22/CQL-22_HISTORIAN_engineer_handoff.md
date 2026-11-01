# Engineer Handoff: CQL-22 HISTORIAN

Issue fixed: `CQL22-HISTORIAN-001` HIGH `SPEC_VIOLATION`. `Message` translation now validates statically known signature operands before lowering to SQL. The condition argument must be Boolean, and severity/message arguments must be String. Unknown runtime expressions and typed nulls continue through the existing helper behavior.

Implementation:
- `fhir4ds/cql/translator/expressions/_functions.py`: added `_validate_message_signature_args()` and invoke it before `Message` argument SQL translation.
- `fhir4ds/cql/duckdb/tests/integration/test_message_parity.py`: added invalid static operand coverage plus runtime parameter severity population-SQL coverage; updated expected typed default parameter behavior.
- `.temp/qa/cql22_historian_probe.py`: fresh pass-specific reproducer covering invalid signatures and valid runtime behavior across Python fallback, native-loaded, and no-Python connections.

Adjacent SKEPTIC work already in the same workspace keeps `CQLMessage` available as a pure SQL macro for no-Python/browser-style runtimes and tolerates native/Python registration ordering.

Validation completed:
- Fresh HISTORIAN probe PASS
- Message parity pytest: 8/8
- Official errors/messaging subset: 4/4
- CQL conformance: 1706/1706
- Full conformance: 2822/2822

No further remediation is needed for this pass.
