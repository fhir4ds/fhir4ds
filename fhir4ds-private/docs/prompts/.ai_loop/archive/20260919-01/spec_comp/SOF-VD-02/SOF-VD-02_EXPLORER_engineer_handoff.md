# Engineer Handoff — SOF-VD-02 (EXPLORER), iteration 1

## Triage
| Issue | Category | Action |
|---|---|---|
| QA-001 MEDIUM | SPEC_VIOLATION | FIXED |
| QA-002 LOW | SPEC_AMBIGUITY | DEFERRED (no spec mandate; deterministic behavior; needs human/spec clarification) |

## QA-001 — bare boolean-constant column falsely rejected
- **Spec**: SQL-on-FHIR v2 IG, ViewDefinition.select.column.type — "must be provided if a ViewDefinition returns a non-primitive type"; Boolean is a FHIR primitive, so `column: [{name: flag, path: %Flag}]` with `valueBoolean` must execute without `column.type`.
- **Root cause**: `fhir4ds/viewdef/generator.py::_path_supports_runtime_type_guard` — the FHIRPath boolean literals `true`/`false` lexically match `_SIMPLE_FHIRPATH_NAV_RE`, so literal-only boolean columns were sent down the simple-path runtime type guard, whose type-unset allowed set is lowercase `_PRIMITIVE_TYPE_NAMES` only. The runtime probe reports System name `Boolean` → misclassified as non-primitive → `error()` at execution.
- **Fix**: route bare `true`/`false` resolved paths to the expression complex-guard branch (they are literals, not navigation), which only rejects OBJECT/ARRAY JSON values. Comment cites the spec invariant.
- **Tests**: `fhir4ds/viewdef/tests/integration/test_duckdb.py::test_boolean_constant_column_without_type_native_and_fallback` and `::test_boolean_constant_false_column_without_type_native_and_fallback` (native + forced-Python-fallback, output text 'true'/'false' consistent with boolean-expression columns).

## QA-002 — constants named after FHIRPath builtins (DEFERRED)
Spec (fetched live) imposes only sql-name on constant.name; nothing about %resource/%context/%ucum/%rootResource/%rowIndex collisions. fhir4ds resolves builtins first, so such user constants are silently unreferenceable. Rejection could break VDs other implementations accept; substitution would shadow FHIRPath-defined environment variables. Deferred with recommendation: raise a parse-time warning or error pending upstream clarification (reference validator behavior unknown).

## Validation
- Focused: new integration tests 2/2 pass.
- `pytest fhir4ds/viewdef/tests`: 1170 passed (was 1168 + 2 new).
- `conformance/scripts/run_viewdef.py`: 144/144 (100%).
- Master gate `run_all.py`: see architect handoff (2832/2832 expected; ViewDef 144 primary gate).
- Binary md5s (unchanged, Python-only fix): fhirpath ext repo bundle == site-packages == 57d0634b6ee6eddee9fc06a1355bef5a; cql ext both  c5b22d58310c1eb7bafa17ce7877f989.
- No git commit performed; all changes in working tree.
