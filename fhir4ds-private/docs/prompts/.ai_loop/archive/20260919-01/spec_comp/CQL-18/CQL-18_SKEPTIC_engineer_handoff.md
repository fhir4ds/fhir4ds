# Engineer Handoff — CQL-18 re-launch (SKEPTIC), iteration 1

Triage: QA-001..QA-006 all CONFIRMED, single shared root cause, fixed in-loop.

## Shared root cause
Dynamic multi-valued FHIR property operands (e.g. `Patient.name.given`)
lower to scalar `fhirpath_text(resource, path)` which truncates to the FIRST
matching node. List operators then either compared one node (contains →
substring), tested the wrong shape (exists → `fhirpath_bool(...) IS NOT NULL`
which is NULL for non-boolean collections), or fed VARCHAR into list macros
(binder errors). The `in` operator already had a targeted repair building
`from_json(fhirpath(...), '["VARCHAR"]')`; every other list operator lacked it.

## Fix (translator-only; no engine changes; py and cpp paths share it)
- New helper `_promote_fhirpath_text_list()` in
  `fhir4ds/cql/translator/expressions/_utils.py` rewrites a 2-arg
  `fhirpath_text(...)` call to `from_json(fhirpath(...), '["VARCHAR"]')`
  (mirrors the established `in`-operator repair).
- `expressions/_operators.py`: promotion applied in `_list_contains_call`,
  `_list_has_all_call`, `_list_except_call`, `_list_intersect_call`,
  `_list_equal_call`, `_list_index_of_call` (list operand(s)); the
  Equivalent `CQLListEquivalentEq` dispatch; and a new guard in the Contains
  fallthrough so `contains` over a dynamic FHIR path uses CQL §10.1 equality
  semantics over the full list instead of substring over one node
  (`contains 'Ji'` now false, `contains 'Peter'` now true).
- `expressions/_lists.py`: `exists` promotes a `fhirpath_bool` source to
  `COALESCE(list_count(from_json(fhirpath(...))),0) > 0` (CQL §10.6); the
  Distinct generic fallback promotes its source before the list-returning
  check (fixes the LIST()-aggregate GROUP BY binder error).
- `expressions/_functions.py`: new `_translate_flatten_pre` pre-translate for
  `flatten` promotes fhirpath_text args (and SQLArray elements) so
  `flatten { Patient.name.given }` keeps List<List<T>> nesting; IndexOf
  argument promotion added at its dispatch (QA-004 residual).
- Spec citations: CQL 1.5 Appendix B §10.1 Contains, §10.2 Distinct,
  §10.3/§10.4 Equal/Equivalent, §10.5 Except, §10.6 Exists, §10.7 Flatten,
  §10.10/§10.11 Includes/IncludedIn, §10.13 IndexOf, §10.14 Intersect.

## Verification
- Reproducer `.temp/qa/cql18_skeptic2/probe4.py`: all 17 per-define cases now
  execute and return spec-correct values on py-only and native-cpp engines.
- Static probe1 31/31 unchanged (no static-literal regression).
- New regression test
  `test_cql_list_part1_dynamic_fhir_lists_execute_and_match_cpp_registration`
  in `fhir4ds/cql/duckdb/tests/integration/test_list_part1_parity.py`
  (15 defines, both engines). Suite: 10/10.
- Focused: test_list_part1 (10) + part2 (12) + test_v2_expressions (169) all
  pass.
- Master gate: see architect handoff for final counts incl. DQM final-state
  and extension binary md5s.
