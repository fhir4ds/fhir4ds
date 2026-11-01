# Engineer Handoff — FP-12 iteration 1 FIX (2026-08-17)

Scope: QA-001..QA-004 (HISTORIAN, §5.8 Tree Navigation / §5.9 Utility).

## Session context

The launch was interrupted entering FIX. A prior partial FIX session had
already landed (uncommitted, no handoff): native `fn_children` metadata
propagation in `extensions/fhirpath/src/fhirpath/evaluator.cpp` (rebuilt +
redeployed to repo bundle and site-packages at 16:42), the `to_string` None
branch (`misc.py`), and the nested-array list branch in
`engine/invocations/navigation.py::create_reduce_children`. This session
verified all of it against QA's evidence, closed one residual gap, and added
regression coverage.

## Issue dispositions (all terminal)

- **QA-001 (MEDIUM, PARITY) — RESOLVED.** Native fn_children now sets
  `field_name`/`fhir_type` via `infer_fhir_type` (§5.8.1: children must carry
  the same model typing as direct navigation, so §6.3 type operators agree).
  Extension rebuilt + redeployed (repo bundle, site-packages — identical md5;
  no ~/.duckdb cache copies present). Residual fallback gap found during
  verification and fixed at root cause: `create_reduce_children`'s
  choice-suffix propName rewrite used `res.propName` (None at the resource
  root), emitting malformed `None.multipleBirth` propNames that broke
  `_matches_unqualified_choice_primitive` — `children().ofType(Integer/Boolean)`
  returned 0 in the fallback while direct navigation and native matched. Now
  falls back to `res.path`, producing resolvable FHIR paths
  (`Patient.multipleBirth` → `+Integer` ∈ FHIR_PATH_TO_TYPE). Full battery:
  `children().ofType(FHIR.{string,code,id,integer,boolean})`,
  `ofType(Integer/Boolean/Quantity)`, `component.children()[0].ofType(Quantity)`
  — 0 diffs native vs fallback, and each agrees with its engine's direct
  navigation.
- **QA-002 (MEDIUM, PARITY) — RESOLVED** (consequence of QA-001 as predicted).
  `component.children()[0] = component.children()[3]` (Quantity child vs
  Integer) → empty in both engines, consistent with `= 120 '1'` literal
  behavior on the same tree.
- **QA-003 (MEDIUM, PARITY) — RESOLVED.** `misc.to_string` None branch
  (§5.5.2: null → empty, never Python repr). Verified: strict core
  `children().last().toString()` on a preserved JSON null → `[]` in core,
  native, and fallback; non-null sibling still `['Jane']`.
- **QA-004 (LOW, PARITY) — RESOLVED.** Nested-array JSON no longer crashes
  the fallback: `create_reduce_children` treats array items' children as the
  elements themselves (native fn_children parity); `children().count()`=4 /
  `descendants().count()`=11 in both engines.

## Files changed (this session)

- `fhir4ds/fhirpath/engine/invocations/navigation.py` — choice-suffix
  propName base fix (root-level fallback to `res.path`).
- `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py` —
  two new regression tests:
  `test_children_type_operators_match_direct_navigation_fp12_historian2`,
  `test_children_null_child_to_string_and_nested_arrays_fp12_historian2`.

(Inherited from the interrupted session, verified this session: evaluator.cpp
fn_children metadata, rebuilt extension binary, misc.py None branch,
navigation.py nested-array branch.)

## Validation

- test_tree_utility_parity.py: 20/20 passed.
- Full conformance: **2832/2832** — ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47. No regressions.
- Full fhirpath pytest tree: see GLOBAL_KNOWLEDGE stats row.

## New issues discovered

None.
