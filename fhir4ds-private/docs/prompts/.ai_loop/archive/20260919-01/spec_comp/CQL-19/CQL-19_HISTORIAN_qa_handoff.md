# QA Handoff — CQL-19 HISTORIAN launch, iteration 1

Chunk: CQL 1.5 List Operators Part 2. Personality: HISTORIAN (spec-compliance
verifier using institutional memory).

## Re-verification of SKEPTIC fixes (regression-free)
Fresh rerun of the SKEPTIC probe batteries on the current tree:
.temp/qa/cql19_skeptic/hist_reverify{1,2}.out — 65/65 + 37/37 SAME, zero
DIVERGE, zero ERR. All 5 SKEPTIC fixes hold, including the RetrievePlaceholder
rows-gating DQM recovery shape. DQM-sensitive probe surfaces exercised here:
retrieve unions execute and dedup correctly; Exists over retrieve union works;
Count over single retrieve works.

## New probing (beyond SKEPTIC coverage)
Probe batteries: .temp/qa/cql19_historian/{probe_hist.py,probe_hist.out,
probe_iso.out}. 35 + 14 new cases across py/cpp/no-python including:
retrieve unions + aggregate consumers, union dedup overlap/both-dynamic/
symbolic-|, dynamic (non-literal) and negative Skip/Take counts, method
syntax (skip/take/union), two-dynamic !=/!~/properly-includes, union-typed
define aliases (Tail/Length/Take/SingletonFrom/Count), singleton over
aliases, empty-list Tail/Last/Length. Confirmed conformant: 41 of 49 cases.

Note: prior `CQL-19 HISTORIAN iter 1` code comments in the tree are from the
July 2026 campaign (typed-empty-list union Case 6a fix) — verified still
present and working (UnionStaticIntDecimal promotes int->decimal correctly).

## Issues found (all translator-level; py == cpp == nopy, no engine divergence)
- QA-001 HIGH: `Count([Observation] union [Condition])` / `Count(Obs union Cond)`
  -> BinderException "Subquery returns 2 columns" (COUNT wraps a 2-col union
  subquery). Count over a single retrieve works. Spec-legal aggregate-over-union
  fails hard.
- QA-002 HIGH: `singleton from G` (G = stored-list define alias of
  Patient.name.given, 3 elements) silently returns the whole list; empty ->
  [] not null; static 3-element case correctly errors. Silent wrong answer.
- QA-003 HIGH: `Patient.name.given union (null as List<String>)` (or `union
  null`) returns NESTED list [['Peter','James','Kim']] instead of the other
  list per cqframework #887 adjudication. Static form correct. Case 6a's
  null-as-empty COALESCE arms do not cover promoted dynamic (from_json) list
  operands; falls to jsonConcat fallback which nests.
- QA-004 MEDIUM: navigation after retrieve union, e.g.
  `Last(([Condition] union [Observation]).id)` -> opaque BinderException
  "Referenced column Condition not found"; single-retrieve nav gives the typed
  TranslationError with rewrite guidance. Same opaque error under
  First/exists.
- QA-005 LOW: retrieve-union row ORDER differs across py/cpp/nopy (content and
  dedup conformant; set semantics, order unspecified). Observation only.

## Adjudications (inherited + re-confirmed)
- Union null-operand -> other list (cqframework #887; fixtures outrank prose).
- singleton from >1 -> run-time error; empty -> null (§20.30).
- Count counts non-null elements of a list; retrieve union IS a list.

## Handoff
Phase -> FIX. Root-cause hints: QA-001/QA-004 in aggregate/navigation lowering
of rows-shaped SQLUnion (needs list coercion before COUNT / navigation);
QA-002 in `_apply_singleton_from` rows-branch (counts ROWS of the stored-list
CTE, not ELEMENTS — route stored-list aliases through the array_length branch);
QA-003 in `_translate_union_op` Case 6a eligibility for promoted from_json
lists + fallback jsonConcat nesting.
