# Engineer Handoff — SOF-VD-09 HISTORIAN (2026-08-23, iteration 1)

Triage: QA-001 HIGH SPEC_VIOLATION — CONFIRMED (reproduced via probe NH9 and
inline matrix; silent wrong-scope evaluation on BOTH engines).

Root cause: `fhir4ds/viewdef/generator.py:_resolve_environment_path_context`
routes any expression prefixed with `%resource.`/`%rootResource.`/`%context.`
wholesale to the root-resource JSON input inside iterators. The prefix branch's
mixed-context guard checked only for NESTED builtin refs in the tail; a
binary-operator operand (a new evaluation rooted at the CURRENT FOCUS, e.g.
`%rootResource.gender & given.first()`) was silently evaluated against the root
— producing wrong/null data — while the reverse ordering
(`given.first() & %rootResource.gender`) correctly raised the typed
"mixes built-in ViewDefinition contexts" ValidationError. The guard was
order-dependent.

Spec grounding: SQL-on-FHIR v2 ViewDefinition-notes Process(S,N) step 2.2 —
columns evaluate as `fhirpath(col.path, f)` with `f` the iterated focus;
`%rootResource`/`%resource` track the root resource. Both are legal in one
expression; the single-input DuckDB UDF surface cannot lower that mix, and the
established doctrine (comment already in the file) is to fail loud rather than
evaluate against the wrong JSON input.

Fix (surgical, generator.py only):
- Extracted the focus-detection walk into `_ast_uses_current_focus(node)`
  (shared node walker); `_expression_uses_current_focus` now parses then
  delegates.
- New `_prefix_tail_has_focus_operand(tail)`: AST spine walk — the first child
  of any `*Expression` (except `InvocationExpression`) continues the builtin
  variable's continuation spine; remaining operands are focus-rooted and trip
  the guard. Function arguments (lambda `$this` scope) and literals do NOT
  trip it, so `%rootResource.name.where(use='official')` and
  `%rootResource.gender = 'female'` keep working.
- Prefix branch raises the same ValidationError when the focus operand is
  detected inside an iterator (current != root), for %resource/%resource
  prefixes only (%context targets the focus itself, no mix possible).

Tests: new class `TestPrefixMixedFocusOperandSpecSofVd09Historian`
(fhir4ds/viewdef/tests/integration/test_duckdb.py) — 4 fail-loud parametrized
cases (both prefixes, `&`, `=`, `and`-composition, extension select.where),
6 still-works cases with native==fallback execution parity, 1 extension-where
fail-loud case. 11/11 pass.

Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds):
- viewdef pytest: 1227/1227
- ViewDefinition conformance: 144/144 (where.json 8/8)
- QA probe: 25/25 on native AND forced fallback
- Master gate: ViewDef 144/144 confirmed within run; full 2832/2832 result
  recorded in architect handoff
- Binary md5 57d0634b6ee6eddee9fc06a1355bef5a identical across repo bundle and
  ~/.local site-packages (no native changes; Python-only fix).

Status: QA-001 RESOLVED.
