# Architect Handoff — FP-17 EXPLORER

Golden standard:
- Wrote `.temp/architect/golden_standard.md` for FP-17 EXPLORER Boolean logic.
- Core invariants: §4.5 singleton Boolean evaluation before §6.5 truth tables;
  explicit public row resilience for result UDFs; native/fallback/helper parity;
  context-aware parser treatment of `not()`; exact arity validation before
  dispatch; and focused coverage for §6.8 precedence and chained expressions.

Architecture audit result:
- No new architecture findings.
- The current Boolean implementation keeps the relevant responsibilities in
  the expected places: native grammar precedence is in
  `extensions/fhirpath/src/fhirpath/parser.cpp`, native Boolean semantics are
  in `Evaluator::evalBinaryOp()` / `fn_not()`, fallback semantics are in
  `fhir4ds/fhirpath/engine/invocations/logic.py` and direct helper semantics
  in `fhir4ds/fhirpath/duckdb/operators.py`.
- QA was adequate for EXPLORER: it tested backend parity, direct fallback
  parity, precedence-distinguishing chains, filters, empty propagation,
  multi-item row resilience, `not()` chains, and `fhirpath_is_valid()`.
  `RETRY_QA` was not set.

Issue counts:
- New architecture findings: 0.
- Open issues: 0.
- Deferred or needs-context issues: 0.

Validation:
- `.temp/qa/fp17_explorer_probe.py`: OK, 21 expression cases and 9 validity
  cases.
- Focused pytest: 174 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

Recommended fix order:
- None for this personality pass.
