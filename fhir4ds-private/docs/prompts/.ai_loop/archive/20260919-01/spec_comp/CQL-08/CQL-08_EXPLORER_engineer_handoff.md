# Engineer Handoff — CQL-08 EXPLORER launch (iteration 1)

## Triage
| Issue | Category | Action |
|---|---|---|
| QA-001 MEDIUM (IsNull over query-valued lists) | SPEC_VIOLATION (candidate) | Implemented strict-spec fix → DQM regression 47→41 → **reverted; reclassified INTENDED by fixture authority** |
| QA-002 LOW (Date-first Coalesce temporal mix) | Observation | INTENDED (unified partial-precision temporal string space; ToDateTime(Date) is identity) |
| QA-003 MEDIUM (new, discovered during fix validation) | SPEC_VIOLATION (query alias/define shadowing) | DEFERRED to query chunk |

## QA-001 narrative (important institutional lesson)
- Implemented the strict Appendix B §IsNull behavior in all three null-test surfaces (prefix IsNull in `_translate_function_ref`, infix/postfix unary in `_operators.py`, `.isNull()` MethodInvocation in `_lists.py`): query/retrieve operands fold to constants (list never null). All 9 reproducer cases passed, parity held.
- **Recovery Gate fired**: full conformance dropped to 2826/2832 — DQM 41/47 (CMS2, CMS771, CMS122, CMS125, CMS130, CMS165). Root cause: official eCQM content uses `( "Most Recent X" Q where ... ) is not null` as a **non-emptiness test**; constant-folding breaks it. GLOBAL_RULES: fixtures outrank spec prose → revert (verified: isolated by temporarily removing the three inserted blocks; DQM 47/47 without them).
- Final state: source files back to pre-fix (verified zero fix sentinels remain; backups removed). Behavior pinned by a new regression test `test_cql_is_null_over_query_valued_lists_fixture_semantics_cql08_explorer` in `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py` (16/16 pass), documenting both the fixture-governed query path (existential) and the strict-spec literal-list path.

## Files changed (net)
- `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py` (+1 test: fixture-semantics pin)
- No translator source changes remain (fix fully reverted).

## Validation
- Nullological parity suite: 16/16.
- Full gate `run_all.py`: ViewDef 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47 — **2832/2832** (baseline held).

## QA-003 (new, deferred)
Any library define whose name equals a query alias makes the alias resolve as the define (`define D: 1+1` + `from {} D return D` → SQL `FROM "D" AS sub WHERE sub.patient_id = D.patient_id`, Catalog Error). Independent of nullological operators; belongs to the query-translation chunk. Reproducer in `.temp/qa/cql08_explorer3_2026_08_21/`.
