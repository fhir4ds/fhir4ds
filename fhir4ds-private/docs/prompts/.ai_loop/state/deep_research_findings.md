### Deep Research: QA-001

**1. Spec Determination:** CQL 1.5.3 Appendix B, Nullological Operators defines a single-list overload `Coalesce<T>(arguments List<T>) T`; it returns the first non-null value and null when every value is null.

**2. Prior Art:** Existing literal-list handling expands `Coalesce({null, 'x'})` to SQL `COALESCE(NULL, 'x')`. CQL query expressions are list-valued and should enter the same overload class.

**3. Approaches Attempted:** The first fix handled inline `SQLSubquery` arguments after normal argument translation. Focused regression showed a named query-list alias (`define StringQuery: from ...`) lowered to a generated CTE reference (`"StringQuery"`) that does not exist in standalone scalar execution.

**4. Blast Radius:** The fragile path is function argument pre-translation for `Coalesce` only. Static list aliases already inline through the static conversion alias path; query aliases need the same source-AST preservation when used as the single list argument.

**5. Recommended Path:** Before translating `Coalesce` arguments, if there is exactly one argument and it is a definition alias whose source AST is a `Query`, translate that source query directly. Then the existing `SQLSubquery` list-overload lowering can select the first non-null row consistently.

### Deep Research: QA-003

**1. Spec Determination:** CQL Reference Appendix B Predecessor/Successor defines Quantity predecessor/successor using the value's lowest precision; integer-authored Quantity values step by `1`, while Decimal-authored values step by `10^-8`. The same section defines direct predecessor/successor as type-sensitive, so public helper string surfaces must preserve the Quantity JSON numeric spelling until the helper decides the step.

**2. Prior Art:** CQL-11 SKEPTIC fixed direct Quantity literal predecessor/successor by bypassing canonical `parse_quantity()` for the immediate unary literal. Query aliases still went through the normal Quantity literal translator, which emits `parse_quantity('{\"value\": 1, ...}')`.

**3. Approaches Attempted:** A broad fix changed all Quantity literal translation to raw JSON. It fixed the alias reproducer but regressed full conformance to CQL 1666/1706 and DQM 45/47 because many existing translator paths rely on `parse_quantity()` canonicalization and validation for ordinary Quantity literals.

**4. Blast Radius:** The fragile boundary is narrower than Quantity translation as a whole: literal-list query sources (`from { 1 'cm' } Q`) are unnested into query aliases, and native C++ `parse_quantity()` serializes integer JSON values as `1.0`. The alias then reaches `predecessorOf(Q)` / `successorOf(Q)` without the original AST literal.

**5. Recommended Path:** Keep the normal Quantity literal translator unchanged. When a `ListExpression` becomes a query source, replace only Quantity literal SQL array elements with raw Quantity JSON literals before `unnest()`. For `predecessor/successor of singleton from { <single Quantity> }`, bypass the canonicalized singleton list and call the helper with the raw Quantity JSON literal. This preserves authored numeric spelling for alias-sensitive predecessor/successor while leaving canonical Quantity handling intact elsewhere.

### Deep Research: CQL-15-DQM-CMS22

**1. Spec Determination:** CQL Reference Appendix B defines interval membership over a consistent point type `T`, and Quantity comparisons use Quantity semantics. Therefore `Interval<Quantity> contains Decimal` is not valid evidence; the result should be null/unknown rather than coercing the scalar into the interval unit.

**2. Prior Art:** The existing CQL translator already routes static Quantity interval membership through `intervalContains` instead of SQL `BETWEEN`, and existing comparison paths preserve Quantity shape through `parse_quantity`/`quantity_compare` where the operands are known Quantity values.

**3. Approaches Attempted:** The first CQL-15 fix correctly made the public interval helper reject Quantity interval vs scalar point comparisons. Full conformance then regressed CMS22 because translated blood-pressure CQL generated `intervalContains(Interval<Quantity>, fhirpath_number(...valueQuantity.value))`, passing only the numeric component value instead of the FHIR Quantity JSON.

**4. Blast Radius:** The fragile path is CQL interval membership over FHIR `valueQuantity.value` projections, especially singleton component filters such as CMS22 systolic/diastolic BP logic. Direct helper behavior, numeric interval membership, and Quantity comparison operators should remain strict.

**5. Recommended Path:** Keep the helper strict. When translating `in`/`contains` against a static Quantity interval, detect FHIRPath numeric projections that end in `.valueQuantity.value` and pass the sibling `.valueQuantity` object via `fhirpath_text` into `intervalContains`. This preserves Quantity shape at interval boundaries without weakening scalar helper semantics.

### Deep Research: QA-001

**1. Spec Determination:**
CQL Reference 1.5.3 Appendix B interval operators define `overlaps` in terms of interval boundary comparison and state that interval operators return null if either argument is null. The Date/Time precision rules used by precision-qualified interval operators make comparisons at the requested precision uncertain when an operand is authored with less precision. Local official/static coverage already encodes this rule: `Interval[@2014, @2014] overlaps day of Interval[@2014-06-01, @2014-06-02]` returns SQL NULL.

**2. Prior Art:**
Direct public helpers return the expected uncertainty when the scalar partial value is represented as a degenerate interval: `intervalOverlapsPrecise(intervalFromBounds('2014','2014',true,true), intervalFromBounds('2014-06-01','2014-06-02',true,true), 'day')` returns NULL in forced Python fallback and no-Python C++. Static translated CQL uses `_overlap_literal_under_precision(...)` to fold partial temporal interval literals to SQL NULL.

**3. Approaches Attempted:**
First attempted to replace translated precision-qualified `overlaps`, `overlaps before`, and `overlaps after` with `intervalOverlaps*Precise(...)` calls using runtime scalar-to-interval wrapping. This fixed the reproducer and focused interval tests, but full conformance regressed DQM from 47/47 to 42/47. The broad rewrite removed the existing DQM-proven temporal decomposition and changed resource-period population SQL too widely.

**4. Blast Radius:**
The failure is in dynamic/resource overlap decomposition, especially `_try_decompose_interval_overlaps(...)` in `fhir4ds/cql/translator/expressions/_temporal_intervals.py`, which emits lexicographic ISO-date comparisons over extracted resource start/end columns. It currently guards static partial literals but has no runtime guard for partial FHIR scalar values such as `effectiveDateTime: "2014"`. DQM measures rely heavily on the optimized decomposition for concrete Period/DateTime windows, so replacing it wholesale is high risk.

**5. Recommended Path:**
Keep the optimized temporal decomposition. Add a narrow runtime precision guard around decomposed overlap SQL: when a decomposed dynamic bound is a runtime expression and its text is present but has fewer digits than the requested precision requires, return SQL NULL before evaluating the lexicographic comparison. This preserves concrete full-date/full-datetime DQM behavior and only changes partial dynamic scalar points. Cover with a CQL-16 dynamic FHIR regression test across forced Python fallback, native-loaded registration, and no-Python C++.



### Deep Research Update: QA-001 Second Attempt

**1. Additional Finding:**
The first narrow guard was placed in `_try_decompose_interval_overlaps`, but query-return expressions such as `singleton from ([Observation] O return O.effective overlaps day of Target)` route through the precision branch in `_operators.py`. In that branch, `intervalStart(O.effective)` / `intervalEnd(O.effective)` are later optimized to `O.effective_start` / `O.effective_end`, which is the SQL that returned false for partial `2014`.

**2. Failed Attempt:**
Guarding only `_try_decompose_interval_overlaps` did not affect the generated SQL for the reproducer. The fresh probe still returned false/null mismatches across Python/native/no-Python paths.

**3. Revised Path:**
Add the runtime precision guard directly around the precision-qualified `overlaps`, `overlaps before`, and `overlaps after` decomposition in `_operators.py`. For directional overlaps, compute the base overlap from the same decomposed start/end comparisons instead of calling `intervalOverlaps(left, right)`, which diverges for dynamic Period JSON on the no-Python C++ path.

### Deep Research Update: QA-001 Final Fix

**1. Additional Regression Check:**
A broad runtime guard over every decomposed bound fixed `Observation.effectiveDateTime: "2014"` but initially regressed CMS135 denominator exceptions. The regressed allergy paths build active intervals as `Interval[start of AllergyIntolerance.onset.toInterval(), AllergyIntolerance.lastOccurrence]`; `lastOccurrence` is null for active unbounded allergies, and `intervalEnd(...)` later behaves like an effective open end. Guarding the partial year-only start against that effective end converted valid active intervals to SQL NULL.

**2. Final Root Cause:**
The precision guard must know whether a partial endpoint has a real finite peer. The rendered SQL looks like `intervalFromBounds(...)`, but translated interval literals are `SQLInterval` objects until `to_sql()`. The first narrowing only inspected `SQLFunctionCall('intervalFromBounds')`, so it missed `SQLInterval` low/high metadata and still used `intervalEnd(...)` as the peer.

**3. Final Path:**
Keep the DQM-proven overlap decomposition. Extract raw low/high peers from `SQLInterval`, `intervalFromBounds(...)`, and CASE-wrapped interval expressions. Use those raw peers only for the runtime precision guard: partial finite or point intervals return SQL NULL at over-specific precision, but active unbounded intervals with a null high endpoint continue through the ordinary overlap comparison. Directional precision overlaps use the same decomposed base overlap so no-Python C++ remains aligned with forced Python fallback and native-loaded registration.
### Deep Research: QA-001

**1. Spec Determination:**
CQL list operators are defined over `List<T>` values. Query expressions also produce collections, so scalar list operators such as `Last`, `Length`, `Skip`, `Tail`, `Take`, `Union`, and proper inclusion must consume the full query-produced collection rather than a single scalar subquery. `singleton from` returns the single element for a one-item list, returns null for an empty list, and raises at runtime when the list has more than one element.

**2. Prior Art:**
Existing CQL-18/CQL-19 fixes preserve list element semantics for clinical, Quantity, interval, and null elements, but the tested paths mostly used literal lists or already-list-returning helpers. DQM translation still depends on row-shaped, patient-correlated resource queries; those cannot be blindly collapsed to patient-independent scalar lists.

**3. Approaches Attempted:**
Initial fix added a generic row-query-to-list wrapper and changed all subquery-backed `singleton from` multi-row cases to throw. Focused list tests passed, but full conformance regressed DQM to 32/47. Failures included missing `_cql_list_source.patient_id`, missing `_cql_list_source`, timestamp casts over list-string values, and `SingletonFrom` runtime errors in CMS measures. This shows the fix was too broad: retrieve-derived/patient-correlated query rows must keep row shape, and only scalar CQL list values should use strict `SingletonFrom` list error behavior in this compatibility layer.

**4. Blast Radius:**
Affected modules: `fhir4ds/cql/translator/expressions/_functions.py`, `_operators.py`, `_temporal_intervals.py`, `_lists.py`, and DQM population SQL generation. Risky surfaces are list operators over literal/query-produced scalar lists, list-definition identifiers, and resource-backed query returns used by CMS measures.

**5. Recommended Path:**
Restrict query-row folding to scalar list queries whose sources are CQL list values or list-valued aliases, not `Retrieve`/resource-backed query sources. Revert global subquery-backed `singleton from` throwing; instead coerce scalar list queries to a DuckDB list before applying the existing list `SingletonFrom` path so literal/query-list multi-item inputs throw while resource-row subqueries retain current row-level DQM behavior. Rerun focused CQL-19 tests, adjacent list tests, official list subset, and full conformance.

### Deep Research: SOFVD04-HISTORIAN-001

**1. Spec Determination:**
SQL-on-FHIR v2.0.0 `ViewDefinition.select.column.type` defines a FHIR
StructureDefinition URI for a column's type, says relative URIs receive the
FHIR StructureDefinition prefix, and says the field must be provided for
non-primitive returned values. It also says implementations should report an
error when the returned type does not match the declared type or when a
non-primitive value is returned while `type` is unset.

**2. Prior Art:**
Existing SOF-VD-04 fixes enforce type/cardinality for simple navigation paths
by querying `(path).type().name`, and they intentionally skip broad
`type().name` guards for function/expression paths because some supported
official functions report FHIRPath System names or no type name even though the
physical result is a valid primitive value.

**3. Approaches Attempted:**
The first fix made `type().name` guards apply to every expression. It fixed the
filtered `Coding` reproducer but regressed the official `fn_boundary.json`
dateTime/time lowBoundary/highBoundary tests: function result type names were
`DateTime`, `String`, or empty rather than the declared FHIR primitive spelling,
so valid primitive boundary results raised type errors.

**4. Blast Radius:**
Affected module: `fhir4ds/viewdef/generator.py`. Risk surfaces are generated
DuckDB column expressions for non-simple FHIRPath paths, especially paths with
`where(...)`, `ofType(...)`, boundary functions, and string literals that may
physically look like JSON. Parser, serializer, and tag metadata validation are
not implicated.

**5. Recommended Path:**
Keep the existing strict `type().name` guard for simple navigation paths. Add a
narrow expression guard for non-simple paths that only rejects physically
complex JSON object/array results when the expression's runtime type names are
absent or incompatible with the unset/declared column type. Treat FHIRPath
System primitive names such as `String`, `Integer`, `Decimal`, `Boolean`,
`Date`, `DateTime`, and `Time` as primitive evidence in this narrow guard so
official primitive function outputs and primitive strings that look like JSON
do not regress.
### Deep Research: SOFVD04-EXPLORER-001

**1. Spec Determination:** SQL-on-FHIR ViewDefinition `select.column.type`
is a FHIR StructureDefinition URI. The spec says implementations should report
an error when a returned value does not match the declared type, or when a
non-primitive value is returned with no type. The same section permits
primitive temporal column types such as `date`, `dateTime`, and `time` through
relative FHIR type URIs.

**2. Prior Art:** Existing SOF-VD-04 HISTORIAN notes explicitly preserve
official primitive boundary functions such as `lowBoundary()` and
`highBoundary()` for non-simple expressions. The official `fn_boundary.json`
ViewDefinition conformance fixture expects `value.ofType(dateTime).lowBoundary()`
and `value.ofType(time).lowBoundary()` to satisfy declared `dateTime` / `time`
columns.

**3. Approaches Attempted:** First fix enforced incompatible reported
`type().name` values for all non-simple primitive expressions. It resolved the
fresh reproducer (`'abc'` declared as `integer`) but regressed ViewDefinition
conformance to 130/134. The four failures were the official dateTime/time
boundary cases. Under the conformance runner's `resources.resource VARCHAR`
transport, those boundary expressions return valid temporal strings while
`(...).type().name` reports `String`; under a JSON column transport the same
dateTime boundary reports `DateTime`.

**4. Blast Radius:** The affected path is
`fhir4ds/viewdef/generator.py::_expression_runtime_complex_guard_condition`.
It is shared by scalar and collection columns for non-simple FHIRPath
expressions. Existing simple-navigation type guards and complex JSON guards are
not the source of the regression.

**5. Recommended Path:** Keep the new mismatch guard for reported primitive
types, but treat `String`/`string` as compatible transport evidence for
declared temporal primitives (`date`, `dateTime`, `time`, `instant`) at this
ViewDefinition runtime boundary. This preserves official boundary-function
conformance while still rejecting non-temporal mismatches such as `String` as
`integer` and `Integer` as `string`.
### Deep Research: QA-001

**1. Spec Determination:**
HL7 FHIRPath Normative Release v2.0.0 Section 5.1 defines strict signatures
for the existence helpers. `exists([criteria : expression])` accepts zero or
one criteria expression; `all(criteria)`, `subsetOf(other)`, and
`supersetOf(other)` require one argument; `empty()`, `count()`, `distinct()`,
`isDistinct()`, and Boolean aggregate helpers take no arguments.

**2. Prior Art:**
The forced Python fallback already rejects all probed malformed Section 5.1
arities with `fhirpath_is_valid=false` and empty/NULL public results.

**3. Approaches Attempted:**
The first native patch added Section 5.1 arity guards in
`Evaluator::evalFunction()`. That fixed ordinary `FunctionCall` helpers such
as `empty(true)`, `count(true)`, `all()`, `subsetOf()`, and `supersetOf(...)`,
but it did not fix `exists(criteria1, criteria2)`. Diagnostic reproduction
showed native still returned `(true, ['true'], '[true]', true)` for
`name.exists(family = 'Smith', family = 'Jones')`.

**4. Blast Radius:**
`exists()` is parsed as `NodeType::ExistsCall` and dispatched directly from
`Evaluator::eval()` to `Evaluator::evalExists()`, bypassing
`evalFunction()` and its central arity guard. Public DuckDB result UDFs and
`fhirpath_is_valid()` both share this evaluator path.

**5. Recommended Path:**
Add an explicit `node.children.size() > 1` guard to `Evaluator::evalExists()`
before criteria evaluation. Keep the central `evalFunction()` guards for the
ordinary Section 5.1 helpers, rerun the fresh Domain 1 probe, and keep a
focused native/fallback parity regression in `test_existence_parity.py`.

### Deep Research: QA-005

**1. Spec Determination:**
SQL-on-FHIR v2 Process(S, N) algorithm step 3
(https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html):
"If `foci` is an empty list and `S.forEachOrNull` is defined (Note: when this
condition is met, no rows have been emitted so far) 1. Initialize a blank row
`r`. 2. For each Column `c` in `ValidateColumns(V, [])` - Bind the column
`c.name` to `null` in the row `r`. 3. Emit the row `r`." Step 4 (Process
UnionAlls) only runs inside step 2's per-focus loop. So when the wrapper
`forEachOrNull` yields empty foci, the WHOLE selection structure emits exactly
ONE row with all ValidateColumns(V, []) bindings null — including any columns
that would otherwise be produced by `unionAll` branches or nested `forEach`.
The union is NOT independently re-run for each branch in the empty-foci case.

**2. Prior Art:**
`fhir4ds/viewdef/generator.py:_build_union_all_query` (lines 1722-1787)
constructs one wrapper `Select` per `unionAll` branch, where each wrapper
carries a copy of the parent `forEach/forEachOrNull/repeat` context, then
calls `_build_single_query` per branch and concatenates the resulting SQL with
`UNION ALL`. This means each branch independently re-emits the wrapper's
unnest JOIN. `_process_selects` (line 1503) already threads
`null_preserve_var` for WHERE preservation across nested forEachOrNull
contexts (lines 1631-1636, 1644-1647) but does not propagate null-preservation
into nested `forEach` JOIN type. AGENTS.md `SOF-VD-05 HISTORIAN` and
`SOF-VD-05 SKEPTIC` entries confirm the spec row-composition layering:
forEachOrNull is row-preserving for its own expression while descendant
select/forEach/unionAll still follow their normal row-set semantics — but the
spec's step-3 empty-foci case is a global "emit one null row" override that
the per-branch SQL UNION ALL model cannot naturally express.

**3. Approaches Attempted:**
- **Option (a) — Thread `null_preserving` into nested forEach JOIN emission**:
  Added a `null_preserving: bool = False` parameter to
  `generate_foreach_unnest` (unnest.py) that emits `LEFT JOIN LATERAL ... ON
  true` instead of `CROSS JOIN LATERAL`. In `_process_selects`, computed
  `enclosing_null_preserve = in_foreach_or_null or null_preserve_var is not
  None` and passed it down. VERIFIED: QA-005 reproducer (Case B3a) went from 0
  rows to the spec-correct 1 row `{pid='p1', cfamily=NULL, tval=NULL}`, and
  Case B3c (forEachOrNull + nested forEachOrNull) continued to emit 1 null
  row. REGRESSION: `test_unionall_primitive_foreach_where_native_and_fallback`
  (test_duckdb.py:2035) failed because the ViewDefinition
  `forEachOrNull:contact` wrapping `unionAll:[branch1, branch2]` where
  branch2 has `forEach:name.given` — with the fix, BOTH branches emit a null
  row for p2 (no contact), producing 2 rows for p2 instead of the
  spec-mandated 1. The pre-fix behavior passed the test only by accident:
  branch2's CROSS JOIN eliminated p2's null row, leaving branch1's single
  null row, which coincidentally matched the spec-required count of 1. The
  fix is correct for B3a but exposes the latent unionAll+forEachOrNull
  empty-foci bug. REVERTED.

**4. Blast Radius:**
- `fhir4ds/viewdef/generator.py:1553-1576` (`_process_selects` forEach branch)
  — the surgical fix site for Option (a).
- `fhir4ds/viewdef/unnest.py:23-58` (`generate_foreach_unnest`) — JOIN-type
  switch site for Option (a).
- `fhir4ds/viewdef/generator.py:1722-1787` (`_build_union_all_query`) —
  required additional surgery for any complete fix, because per-branch
  wrapping inherently re-runs the wrapper's unnest per branch.
- Pre-existing tests encoding the latent bug:
  `test_duckdb.py::TestUnionAll::test_unionall_primitive_foreach_where_native_and_fallback`
  (1 test). Survey of `fhir4ds/viewdef/tests/` shows ~15 tests touching
  forEachOrNull; only the unionAll+forEachOrNull+nested-forEach combination
  is affected.

**5. Recommended Path:**
Implement Option (a) (LEFT JOIN for nested forEach inside enclosing
forEachOrNull) AS WELL AS a complementary unionAll fix so the spec's
single-null-row-on-empty-foci semantics is preserved across union branches.
Two viable implementation strategies for the unionAll complement:

  Strategy A (preferred): When `_build_union_all_query` is invoked with a
  `union_select` that carries `forEachOrNull`, suppress the null-preserved
  row in all non-first branches by adding a WHERE filter on the wrapper's
  unnest alias. This requires either (i) pre-computing the wrapper's
  forEachOrNull alias before `_process_selects` runs (predictable via
  `_alias_counter` + the path-derived base name) or (ii) extending
  `_process_selects` to return the alias of any forEachOrNull unnest it
  emitted. The first branch naturally emits the single null row via the
  Option (a) LEFT JOIN. Spec-compliant; preserves existing test contracts.

  Strategy B (deeper restructure): Hoist the wrapper's unnest OUTSIDE the
  UNION ALL so it executes once, then build the UNION ALL inside that
  unnest's scope. Requires `_build_union_all_query` to emit the unnest
  manually (using `generate_foreachornull_unnest` / `generate_foreach_unnest`)
  and to pass the unnest alias as the resource context to each branch's
  `_process_selects`, skipping the wrapper unnest emission. Cleaner model
  but a larger blast radius across `_build_union_all_query` and
  `_build_single_query`.

Recommend Strategy A: smaller blast radius, preserves existing test
contracts, and directly addresses the spec's "emit one null row" rule for
the empty-foci case. After implementing, add regression tests for both B3a
(forEachOrNull + nested forEach, outer empty) and the unionAll case
(forEachOrNull wrapping unionAll with a forEach branch, outer empty → 1
null row total).

### QA-016 Second Attempt — Failed (REVERTED)

**What I tried:** Targeted elimination of audit_and/or/not/leaf macros at
specific translation sites that produce WHERE-clause-of-correlated-EXISTS
patterns. The bisect confirmed: the DuckDB binder bug ("Need named argument
for struct pack") is triggered by an OUTER audit_and chain whose children
reference multiple correlation depths (e.g., one leaf referencing the
immediate outer table via intervalContains(Encounter.period, ...), another
wrapping a correlated EXISTS subquery against a third table). The same
audit_and chain evaluated in a flat per-patient JOIN SELECT executes
without binder error (verified by lifting it out of the EXISTS WHERE).

I introduced a new helper `_fully_demote_audit_to_bool(expr)` that
recursively eliminates every audit_and/or/not/leaf macro in a boolean
expression (audit_and(a,b) → fully_demote(a) AND fully_demote(b),
audit_leaf(X) → X). Applied at the with-such-that translation site
(`_query.py:4735`) and at `_demote_audit_struct_to_bool` itself.

**Why it failed:** The change to `_demote_audit_struct_to_bool` was too
broad. CMS71 and CMS996 FULL audit started passing, but CMS165 (which
passed at baseline) started hanging at SQL execution time. The probe3
sweep timed out at 900s on CMS165 alone; the conformance baseline would
regress.

The mechanism: `_demote_audit_struct_to_bool` is called from many
translation sites, including some where the shallow `struct_extract(...)`
form participates in the OUTER audit CTE's `_audit_result` column. Fully
eliminating the macros there changes the audit struct shape and breaks
DuckDB's planner heuristics for large queries (CMS165's SQL is 280k chars;
the planner chokes).

**What I'll try next:** A more surgical fix. Keep
`_demote_audit_struct_to_bool` shallow (preserve current behavior for the
outer audit CTE). Apply `_fully_demote_audit_to_bool` ONLY at sites where
the boolean is going INTO a WHERE clause of a correlated EXISTS subquery
(i.e., the with-such-that site and similar with-clause/retrieve-filter
sites). The audit evidence loss is acceptable at those sites because the
outer definition-level audit CTE re-captures it.

The challenge: identifying all sites where the boolean lives in a
WHERE-of-correlated-EXISTS context. The with-such-that site (CMS71) is
one. The "X is null OR X in {codes}" pattern in CMS996's filtered
retrieves is another. There may be others. Will need to enumerate them
via grep on the emitted SQL for `struct_extract(audit` patterns and
trace back to the call site.

### Deep Research: QA-016 (Partial — FULL audit struct_pack failure)

**1. Spec Determination:**
`fhir4ds/dqm/evaluator.py:140-145` documents `audit_mode='full'` as the public
canonical path for "Full expression wrapping with audit_and/or/leaf macros for
maximum evidence detail". CMS eCQM Logic and Implementation Guidance requires
that any certified CQL evaluator produce causally-correct audit trails.

**2. Prior Art:**
The audit SQL emission path lives in two cooperating modules:
- `fhir4ds/cql/translator/ast_helpers.py::_inject_audit_evidence` builds
  per-CTE evidence subqueries.
- `fhir4ds/cql/translator/cte_manager.py::_flatten_audit_tree` flattens deeply
  nested audit_and/audit_or trees into a single struct_pack to avoid DuckDB
  exponential macro expansion.

The outer patient alias is `_pt` (correlation.py:373); old SQLRaw nodes
referenced `p.patient_id` which was never bound.

**3. Approaches Attempted:**

- **Fix attempt 1 (RESOLVED):** Replaced unbound `p` alias with `_pt` in
  `ast_helpers.py:1698/1712/1725` (3 sites in `_inject_audit_evidence`) and
  `cte_manager.py:614/622` (2 sites in audit CTE pre-compute lookup). After
  this fix, CMS165 FULL audit PASSED (was failing). CMS135/CMS71/CMS996 still
  fail with the second binder error: `Need named argument for struct pack`.

- **Fix attempt 2 (OPEN):** The remaining binder error occurs when the same
  CTE list is reused for a final SELECT targeting "Denominator Exceptions",
  "Numerator", or "Documented Reason For Not Giving Anticoagulant At Discharge"
  in CMS71. Bisecting CTEs and replacing the failing CTE bodies does NOT clear
  the error. Replacing all `audit_xxx(...)` calls with `TRUE` clears the binder
  error (it then fails with a different "struct_extract on BOOLEAN" error,
  confirming the audit macros are the source). However:
    * All `struct_pack(...)` calls in the emitted SQL have named args.
    * `audit_and`/`audit_or`/`audit_leaf` macros in isolation work at any
      depth with mixed NULL/TRUE/EXISTS args.
    * The exact failing pattern, extracted into a standalone DuckDB script,
      executes successfully.
    * The same CTE list works when the final SELECT targets "Denominator"
      (which has the same shape as "Denominator Exceptions").

  This points to a DuckDB binder quirk that emerges only when the optimizer
  inlines a particular chain of CTEs whose predicates contain audit_and
  trees with CQLListContainsEq leaves. Reproduction requires the full CMS71
  fixture data and the exact CTE dependency graph.

**4. Blast Radius:**
- Public API `MeasureEvaluator.evaluate(audit_mode='full')` raises DQMError on
  CMS71/CMS996/CMS135.
- Conformance runner silently falls back (runner.py:201-213); 47/47 baseline
  is preserved but audit is never exercised.
- POPULATION audit mode (audit_mode='population') works for all measures.

**5. Recommended Path:**
- Ship the partial fix (unbound `p` → `_pt`) — this resolves CMS165 and is a
  strict improvement.
- For the remaining struct_pack failure, escalate to NEEDS_CONTEXT. The bug
  requires deeper DuckDB binder introspection or reproduction with a smaller
  fixture to identify the exact trigger. The recommended short-term
  workaround is to wrap the DQMError in an actionable hint directing callers
  to `audit_mode='population'` for affected measures.
- Add a regression test for CMS165 FULL audit (now passing).
- Track the struct_pack binder issue as a follow-up; it does NOT block 0.0.11
  release because POPULATION mode is the recommended path for production
  audit trails.


### QA-016 ROOT CAUSE FOUND

**Structural root cause:** DuckDB's binder fails with "Need named argument
for struct pack" when an `audit_and`/`audit_or`/`audit_not` chain
containing an `audit_leaf` with a complex argument (EXISTS subquery or
non-trivial function call like intervalContains/coding_matches) is emitted
in the WHERE clause of a correlated EXISTS subquery whose children
reference multiple correlation depths. Bisect on CMS71 Numerator CTE
isolated the trigger: an outer audit_and with one leaf referencing the
immediate outer table (e.g., `audit_leaf(intervalContains(Encounter.period,
...))`) and another wrapping a deeper correlated EXISTS (e.g.,
`audit_not(audit_leaf(EXISTS(SELECT FROM Task WHERE ...)))`). Replacing
just the outer audit_and with `audit_leaf(true)` clears the bug; the same
audit_and chain lifted to a flat per-patient JOIN SELECT executes
without binder error. The bug requires the WHERE-of-correlated-EXISTS
context — it does NOT emerge in flat SELECT columns.

**Why audit macros trigger it:** DuckDB's audit macros
(`audit_and`/`audit_or`/`audit_not`/`audit_leaf`) expand textually into
`struct_pack(...)` calls. When the macro argument list contains references
to tables bound at different outer correlation levels, the binder's
name-resolution pass fails to assign positional names to the struct_pack
arguments. The same expression shape with simple column references works
fine; only complex function-call arguments trip the binder.

**Fix approach:** introduced `_fully_demote_audit_to_bool(expr)` in
`fhir4ds/cql/translator/expressions/_query.py:114-235`. The helper
recursively eliminates every audit_and/or/not/leaf macro from a boolean
SQL expression: `audit_and(a,b)` → `fully_demote(a) AND fully_demote(b)`,
`audit_leaf(X)` → `X`, `audit_not(a)` → `NOT fully_demote(a)`. It recurses
into EXISTS subqueries, SQLSelect bodies, SQLBinaryOp, SQLCase, etc. The
existing `_demote_audit_struct_to_bool` now auto-detects the trigger
pattern via `_audit_chain_has_complex_leaf` and delegates to
`_fully_demote_audit_to_bool` when present, preserving its shallow
`struct_extract(...)` behavior otherwise to avoid regressing paths that
rely on the audit struct shape (e.g., CMS165's outer audit CTE which has
audit_comparison leaves, not the trigger pattern).

The audit evidence (the whole point of the macros) is preserved by the
OUTER per-patient audit CTE in cte_manager.py which wraps the entire
definition as `audit_leaf(EXISTS(...))`. The inner WHERE-clause audit
macros were redundant — they would have produced duplicate evidence that
the outer CTE already captures.

### Deep Research: CMS2 Option A — Failed Attempt (BENCH-001)

**1. Spec Determination:** The task asks to hoist `_latN.value` Period-vs-Range
disambiguation CASE expressions AT EMISSION TIME (Option A), NOT via
post-processing. The disambiguation CASEs at `_query.py:3244-3408`
(`_translate_is_type_check`) emit the same ~294-char block 510+ times per
CMS2 CTE, accounting for ~150KB of the 1.55MB noaudit SQL.

**2. Prior Art:** The existing `types.py:SQLFragment.deduplicate_lateral_aliases`
post-processing pass coalesces repeated `fhirpath_text` calls into `_latN.value`
aliases but does NOT touch SQLCase wrappers. A prior Option C attempt that
extended this pass to also dedupe CASEs broke the audit path (reintroduced
unbound `p` alias + struct_pack binder bugs) because it rewrote `_latN.value`
references inside audit_and/audit_or chains.

**3. Approaches Attempted:**

  **Approach 1 — Emission-time LATERAL join memoization (FAILED):**
  Added `_memoize_disambiguation(resource_expr, kind, builder)` in `_query.py`
  that caches the CASE per `(def_name, resource_sql, kind)`, emits it as a
  `CROSS JOIN LATERAL (SELECT <CASE> AS value) AS _disN`, and returns a
  `SQLQualifiedIdentifier(parts=['_disN','value'])` reference. The LATERAL
  joins were recorded on `self.context._disambig_joins[def_name]` and
  attached to the CTE body by a new `_attach_disambiguation_joins` method
  in `cte_manager.py`.

  CMS2 size shrank from 1,552,792 → 1,408,847 bytes (–9.3%). CMS2 executed
  correctly (36 rows). BUT audit_sweep regressed from 4/5 FULL pass to 3/5:
  CMS165 failed with `Binder Error: Referenced table "_dis1" not found!`.

  **Root cause of failure:** The audit emission path (`cte_manager.py`
  `__pre_...` CTE construction) copies fragments of the definition's
  translated expression into pre-compute CTEs. When the definition's
  expression contains `_disN.value` references (the memoized form), those
  references are copied verbatim into the `__pre_...` CTEs, but the
  `_disN` LATERAL join is NOT copied (it lives on the definition's main
  SELECT, not inside the pre-compute CTE's FROM). Result: unbound `_disN`
  alias inside audit pre-compute CTEs.

  This is structurally identical to the prior Option C failure mode: the
  audit path copies expression fragments that reference external aliases,
  and those aliases aren't in scope inside the audit CTEs.

  **Required-alias filtering did NOT help:** Added `_extract_outer_alias` to
  record which FROM-alias each disambiguation CASE depends on, and only
  attached the join to SELECTs providing that alias. CMS2 still worked, but
  CMS165 still failed because the `_dis1` reference was inside a
  `__pre_...` CTE that HAS the alias in its FROM — the problem isn't the
  FROM alias, it's that the `_dis1` LATERAL join itself wasn't attached to
  that specific SELECT.

  **Substring-based attachment did NOT help:** Tried attaching to every
  SELECT whose serialized SQL contains `_disN`. This attached joins too
  broadly (to SELECTs where the reference is actually in a nested
  subquery's scope), causing different binder errors.

**4. Blast Radius:**
  - `_translate_is_type_check` in `_query.py:2996-3500` (the disambiguation
    emission sites).
  - `_build_definition_cte_with_patient_id` and `__pre_...` CTE construction
    in `cte_manager.py` (where expression fragments get copied into audit
    CTEs).
  - Any measure using `is Interval<DateTime>`, `is Period`, `is Range`, or
    `is Interval<Quantity>` — including CMS2, CMS165, CMS135, CMS71, CMS996.

**5. Recommended Path:**

  The LATERAL-join-hoisting approach is FUNDAMENTALLY incompatible with the
  audit path's expression-copying behavior. Any approach that replaces an
  inline self-contained expression with a reference to an externally-defined
  alias will break when the audit path copies the reference into a scope
  where the alias isn't defined.

  **Option A-revised (recommended):** Instead of hoisting into LATERAL
  joins, memoize the disambiguation CASE as a SHAREABLE AST NODE (return the
  SAME `SQLCase` object on cache hit). This does NOT shrink SQL by itself
  (the CASE is serialized at every reference site), but it's safe because
  the CASE is self-contained — no external alias dependency. Then, to
  actually shrink SQL, extend the EXISTING `deduplicate_lateral_aliases`
  pass to recognize SQLCase... but that's BANNED.

  **Alternative (if ban is relaxed):** Add a NEW, narrowly-scoped
  post-processing pass `hoist_disambiguation_cases()` on SQLFragment that
  runs AFTER audit CTE construction (so it sees the final SQL including
  audit pre-compute CTEs) and hoists CASE patterns that appear 3+ times
  within the SAME SELECT scope (not across SELECTs). This would coalesce
  the 510 CASEs in CMS2's definition CTEs without touching audit CTEs (where
  the CASEs don't repeat because audit CTEs use different structures).

  **Status:** ESCALATION to NEEDS_CONTEXT. The ban on post-translation AST
  rewrites makes emission-time hoisting the only path, but emission-time
  hoisting is fundamentally incompatible with the audit path's expression-
  copying behavior. The user must either (a) relax the ban to allow a
  narrowly-scoped post-processing pass that runs after audit construction,
  or (b) accept that the disambiguation CASE bloat (~150KB, 10% of CMS2)
  cannot be safely removed without redesigning how the audit path copies
  expression fragments.
