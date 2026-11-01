# CQL-19 EXPLORER — Engineer Handoff (iteration 1)

## Triage
- QA-001 HIGH SPEC_VIOLATION — CONFIRMED, RESOLVED
- QA-002 HIGH SPEC_VIOLATION — CONFIRMED, RESOLVED
- QA-003 MEDIUM SPEC_VIOLATION — INTENDED (gate-forced adjudication)

## Fixes (all translator-only; no native changes)
1. **QA-001** `fhir4ds/cql/translator/translator.py` — stored-list meta now
   propagates through alias defines (`define B: A`): stores_list_value,
   PATIENT_SCALAR shape, List< cql_type. And
   `expressions/_operators.py::_union_operand_as_list` — element-rows
   (PATIENT_MULTI_VALUE) value defines convert to the per-patient element
   LIST for unions, guarded on the PEER operand not being rows-shaped.
2. **QA-002** `expressions/_lists.py` — new
   `_list_operator_full_list_source` +
   `_list_operator_source_is_retrieve_shaped`: materializes bare retrieves,
   resource-define aliases, retrieve unions, query returns, and
   element-rows defines into correlated per-patient element lists for the
   Tail/Skip/Take/Length/SingletonFrom family. Wired into
   `expressions/_functions.py` FunctionRef dispatch (tail/skip/take/length/
   singletonfrom; First/Last keep their window paths) and
   `_translate_skip_expression`/`_translate_take_expression`.
3. **QA-003** kept NULL for >1 on the rows-subquery singleton branch with an
   in-code adjudication comment (see below).

## Recovery-gate events (root-caused, no blind retries)
- First gate run: DQM 43/47. CMS1017/CMS832: my §20.30 typed error on the
  rows-subquery singleton branch fired in guarded CQMCommon fluent-function
  bodies where SQL evaluates eagerly but the reference engine short-circuits
  the enclosing guard -> reverted that branch to NULL (adjudication: gate
  fixtures outrank prose; element-exact paths keep the error).
- CMS117/CMS645: `ltrim(VARCHAR[])` binder — bisected via git-stash
  causality to the union element-rows conversion firing when the peer
  operand was rows-shaped (DQM resource unions); fixed with the peer-shape
  guard.

## Verification (final tree)
- Focused: test_list_part2_parity.py 47/47 (14 new explorer tests x
  py/cpp/nopy); test_list_part1_parity + test_list_udfs 105 total pass;
  clinical_operator + nullological parity 178 pass; CQL unit 1612/1612;
  CQL duckdb tree pass; DQM 47/47 (fresh, incl. retry after fixes).
- Master gate: see architect handoff / report (fresh run on final tree).
- Binaries unchanged (translator-only): cql 3e7d4167143e01907fdd8561db43b7d7,
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a; repo bundle == ~/.local
  site-packages for both.

## Regression tests added
`fhir4ds/cql/duckdb/tests/integration/test_list_part2_parity.py`
(explorer-suffixed): 12-case parametrized retrieve-shaped battery,
singleton-from query >1 NULL pin, `{1,2} !~ null` TRUE pin.
