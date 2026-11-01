# Engineer Handoff — CQL-19 HISTORIAN launch, iteration 1

All four actionable QA issues CONFIRMED and RESOLVED at the translator level
(py == cpp == no-python identical before and after; no native code changed this
launch — extension binaries untouched, md5 repo bundle == site-packages:
cql 3e7d4167143e01907fdd8561db43b7d7, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a).
QA-005 (retrieve-union row order across engine modes) classified INTENDED
(content + dedup conformant; order unspecified under set semantics).

## Fixes (all in fhir4ds/cql/; translator-level, type-directed, no shims)

1. QA-001 `Count(<retrieve> union <retrieve>)` —
   `translator/expressions/_functions.py` `_translate_aggregate_pre`: new
   COUNT-over-union branch. Resolves resource-define alias identifiers to
   their underlying Retrieve ASTs (so heterogeneous CTE columns cannot
   collide), translates the union (rows-shaped SQLUnion of patient_id/resource
   branches), and wraps it in the same patient-correlated `COUNT(*)` subquery
   the single-Retrieve branch uses. `Count(Obs union Cond)` = 3/1,
   self-union dedups = 2/0, single-retrieve control unchanged.
2. QA-002 `singleton from G` (stored-list define alias) — three-part fix:
   `_lists.py` extracted `_apply_singleton_from_list_value` (element-
   cardinality CASE: 0 -> null, 1 -> element, >1 -> typed SingletonFrom
   error); `_functions.py` `_translate_singleton_list_define_pre` pre-hook
   (registered for "singletonfrom") routes stored-list alias references
   through it; `_operators.py` unary `singleton from <alias>` same routing.
   Both syntaxes now raise the §20.30 typed error for >1 element; empty/
   absent -> null; `Take(G,1)` singleton still returns the element.
3. QA-003 `dynamicList union null` nested result — two layers:
   (a) `_operators.py` §20.29 null gate now also treats statically-null
   list operands (`_is_static_null_case`, e.g. `(null as List<T>)` lowering
   `CASE WHEN FALSE THEN NULL END`) like SQLNull, returning the other
   operand; (b) `_temporal_intervals.py` `_is_static_null_case` now accepts
   a missing else_clause (CASE without ELSE evaluates to NULL); (c)
   `translator.py` define-level stored-list union marking now accepts null
   literals and `as`-cast operands in the element-list-union allowlist (a
   null operand can never be a resource CTE, so the DQM resource-union guard
   is preserved) — this stops the PATIENT_MULTI_VALUE wrap from LIST()-
   nesting the per-patient list into [[...]].
4. QA-004 navigation over a retrieve union — `_property.py` guard extended:
   `([A] union [B]).field` now raises the same typed, actionable
   TranslationError as `[Resource].field` instead of an opaque DuckDB binder
   error at execution.

## DQM-sensitivity check (review-35 gate discipline)
Retrieve-union and aggregate-consumer surfaces re-probed end-to-end
(RetrieveUnionRows, ExistsRetrieveUnion, CountRetrieveUnion, CountUnionAlias,
RetrieveUnionSelf) — content, dedup, and counts conformant in all 3 modes.
Master gate run against the FINAL tree state, single pass, no DQM retry needed.

## Validation
- Probes: .temp/qa/cql19_historian/{probe_hist_final.out, probe_fix2.out} —
  all fixes verified; only remaining DIVERGE lines are the QA-005 order
  observation; SingletonFrom errors are the spec-mandated >1-element errors.
- SKEPTIC fix regression: fresh rerun of the prior launch's probe batteries
  (.temp/qa/cql19_skeptic/hist_reverify{1,2}_final.out) — 65/65 + 37/37 SAME.
- Focused suites: test_list_part2_parity.py 33/33 (5 new HISTORIAN regression
  tests appended: count-over-union, singleton-alias cardinality, union-null
  nesting, union-nav typed error, plus Condition fixtures added to the shared
  resources SQL), test_list_part1_parity.py 18/18, test_v2_expressions.py
  147/147.
- Master conformance gate (fresh, final tree): OVERALL 2832/2832 —
  ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47.
  Baseline holds. Log: .temp/qa/cql19_historian/gate_final.log.

Issue statuses: QA-001..QA-004 RESOLVED; QA-005 INTENDED.
