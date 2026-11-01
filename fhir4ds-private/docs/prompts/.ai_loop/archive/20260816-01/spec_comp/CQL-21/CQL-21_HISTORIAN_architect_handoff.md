# Architect Handoff - CQL-21 HISTORIAN Iteration 1

## Structural Audit Summary

The HISTORIAN iteration 1 fix to `_code_entries_from_ast` in
`fhir4ds/cql/translator/expressions/_operators.py` is **structurally
sound**. No architectural drift introduced. No silent fallbacks. No
hardcoded resource types or magic strings. No layering violations.

## Golden Standard Invariants (verified)

1. **Generalizability**: The fix recurses via the existing
   `_code_entries_from_ast` recursion, handling any number of Code
   elements in the Concept's `codes` field (not just 1 or 2).
2. **Abstraction Integrity**: The fix stays inside the translator's
   `_translate_in_op` helper. No new layer crossed. The existing
   `_synthetic_code_resource` UDF-input contract is preserved.
3. **Silent Fallbacks**: None introduced. If any item in the
   ListExpression is not a Code the recursion can handle, the function
   returns None (existing behavior), and the translator falls through
   to generic JSON — same as before. The fix only adds a new path
   where Concept literals are now correctly recognized.
4. **Test-Driven Hacks**: No special-cased logic for the test fixture.
   The fix detects the `ListExpression` shape generically.
5. **Coupling**: No new coupling. The fix is local to one nested
   helper.
6. **Performance**: Negligible — the new branch runs once per
   Concept literal at translation time, not per resource.

## State Hygiene

- `evolution.json` pruned: QA-001 marked RESOLVED with verified_in
  proof. No historical evidence lingering in the active state file.
- Full evidence preserved in this handoff and in
  `fhir4ds/cql/AGENTS.md`.

## QA Quality Veto

**QA SUFFICIENT** — No RETRY_QA. The HISTORIAN probe was a systematic
§-by-§ walkthrough covering 57 spec-grounded cases across all 9 chunk
items on both backends with parity comparison. The single bug found
(QA-001) was the only spec violation; all other 56 cases verified
spec-compliant. The methodology (every-overload-form coverage) is
exactly what HISTORIAN should produce.

## Recommended Fix Order

No follow-up engineer work required. The single issue (QA-001) is
RESOLVED and VERIFIED. The remaining pre-existing primitive/string
test failures are unrelated to CQL-21 clinical operators and pre-date
this iteration.

## Compressed Handoff

QA found 1 HIGH spec violation (Concept-in-ValueSet with inline Concept
literals always returned False). Engineer implemented surgical fix to
`_code_entries_from_ast` to handle `ListExpression` in Concept's
`codes` field. Regression test added (4 cases x 2 backends). Full
conformance 2822/2822 unchanged. Pre-existing failures in unrelated
test files remain pre-existing. Issue RESOLVED.

## Clean Exit

Per MASTER ORCHESTRATOR §5 Exit Checks:
- Zero non-terminal CRITICAL/HIGH/MEDIUM issues remain (QA-001 is RESOLVED).
- `iteration` 1 >= `min_iterations` 1.
- `config.exhaustive_mode` is false.

Clean exit is eligible.
