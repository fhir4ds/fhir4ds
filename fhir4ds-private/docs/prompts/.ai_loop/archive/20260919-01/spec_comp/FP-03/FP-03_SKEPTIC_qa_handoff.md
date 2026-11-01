# QA Handoff — FP-03 SKEPTIC (iteration 1, 2026-08-16)

## Chunk
FHIRPath §5.1 Existence: `empty()`, `exists([criteria])`, `all(criteria)`,
`allTrue()`, `anyTrue()`, `allFalse()`, `anyFalse()`, `subsetOf(other)`,
`supersetOf(other)`, `count()`, `distinct()`, `isDistinct()`.

## Method
- Spec grounding: fetched the full N1 (v2.0.0) normative HTML from
  hl7.org/fhirpath/N1 (2026-08-16); §5.1.1–§5.1.12 parried against §5.2.1
  (criteria singleton rules), §4.5 (singleton evaluation), §6.1.1 (= for
  membership/distinct), §6.2 (comparison type-error doctrine).
- Official R4 fixture pins extracted from
  `fhir4ds/fhirpath/tests/compliance/r4/tests-fhir-r4.xml` (30 §5.1 cases:
  testExists1-5, testAllTrue1-4, testSubSetOf1-3, testSuperSetOf1-2,
  testDistinct4-6, testCount1-4, testEmpty, testCollectionNotEmpty,
  testLiteralNotOnEmpty). The conformance suite (935/935) covers these; probes
  used them as controls.
- Dual-path probes (native extension connection vs Python fallback UDFs, 5
  result channels + `fhirpath_is_valid`), run with `PYTHONPATH=/mnt/d/fhir4ds`:
  - `probe.py`: 116 pre-registered cases across H1–H8 (allTrue family,
    all/exists criteria, $index, subsetOf/supersetOf corners, distinct/
    isDistinct equality, count, is_valid arity, fixture controls).
  - `probe2.py`: 25-case blast-radius battery for the one parity failure.
  - Two ad-hoc focused batteries (numeric distinct/isDistinct shorthand;
    time-string ordering corners). Battery dir:
  `/mnt/d/fhir4ds/.temp/qa/fp03_skeptic_2026_08_16/`.

## Pre-registered SKEPTIC hypotheses and outcomes
- H1 allTrue-family coercion/empty corners — REJECTED (non-Boolean literal,
  JSON node, and object items error→empty in BOTH; empty-input corners
  allTrue→true / anyTrue→false / allFalse→true / anyFalse→false correct).
- H2 all/exists criteria singleton doctrine — CONFIRMED as QA-001 (see
  below): the native engine converts comparison type errors into "criteria
  false"/"criteria matched differently", producing WRONG Booleans.
- H3 $index in criteria + scope restoration — REJECTED (all()/exists() expose
  correct per-item $index and restore scope in both engines).
- H4 subsetOf/supersetOf §5.1.8/§5.1.9 corners — REJECTED (empty-input→true,
  empty-other→supersetOf true, converse cases false, order-irrelevant
  membership via `=`, root-context `other` evaluation (`$this.name`) all
  correct in both).
- H5 distinct/isDistinct equality — REJECTED as a bug (1=1.0, 'cm'/'mm'
  quantities, key-order-different JSON objects, Date precision mismatch →
  2 items, Integer vs Boolean not equal: all parity-correct and spec-correct;
  `(1.0|1).isDistinct()`=true is CORRECT because `|` union dedups at
  construction — the `combine` forms confirm the §5.1.12 shorthand
  `X.count() = X.distinct().count()` holds).
- H6 count() — REJECTED (empty→0, Integer result, arithmetic chaining,
  JSON-null array elements skipped identically).
- H7 is_valid arity — REJECTED (empty(1), exists(1,2), all(), subsetOf(),
  subsetOf(1,2), count(1), distinct(1), isDistinct(1), all(1,2), allTrue(1)
  all invalid on BOTH surfaces).
- H8 basics/fixtures — REJECTED (all controls match fixtures).

## Issues logged (evolution.json)
1. QA-001 (HIGH, OPEN) — Native comparison type-mismatch swallow inside
   §5.1 iteration functions. `evaluator.cpp` `evalBinaryOp` comparison branch
   returns `{}` at the "One numeric, one not" site (~8662) and the
   incompatible-types catch-all (~8673) instead of signaling the §6.2
   evaluation error. Masked at UDF top level (wrapper error→NULL) but
   decisive inside `all()`/`exists()`/`where()`/`select()`/`iif()` criteria:
   `mixed.all($this > 0)` → native **false** vs fallback empty (spec: error);
   `mixed.exists($this > 0)` → native **true** vs fallback empty;
   `mixed.where($this > 0)` → native **[1]** vs fallback empty;
   `iif('a' > 0, 1, 2)` → native '2' vs fallback empty. Spec-mandated empty
   comparison results (partial temporal precision, calendar-vs-UCUM,
   offset temperatures, incompatible quantity dimensions) are correct and
   MUST stay empty.
2. QA-002 (MEDIUM, OPEN) — Time-literal vs time-shaped plain-string ORDERING
   diverges: fallback coerces (`'10:00' < @T10:30` → true) while native
   returns empty. Python `_compare` typecheck (equality.py ~606-612) includes
   `FP_Time` in the str→temporal coercion branches; this contradicts the
   pinned Time-vs-String equality convention (String→Time is Explicit-only,
   FP-01 QA-003). Date/DateTime string ordering coercion is shared by both
   engines and must be preserved.

## Verified clean (high-value negative results)
- allTrue/anyTrue/allFalse/anyFalse: 21 cases incl. mixed literal+JSON
  booleans, non-bool error paths, all four empty-input corners.
- all/exists: vacuous all() on empty input → true; exists on empty → false;
  constant criteria; boolean-item criteria; empty-criteria-result → false
  (`(@2018|@2018-01).all($this = @2018-01)` → false in both — spec-correct
  because equality-EMPTY is "not true", distinct from a type ERROR).
- subsetOf/supersetOf: 21 cases incl. numeric 1=1.0 membership, quantity
  'cm'/'mm' membership, `(1|true)` membership, duplicates, $this-root args.
- distinct/isDistinct: 21 cases incl. JSON nulls, key-order objects,
  precision-mismatched dates, string/bool dedup, empty→true.
- is_valid: 10 arity cases + all evaluated expressions remain valid=Turue on
  both surfaces (execution-type-error doctrine).
- Top-level type-mismatch comparisons (`'a' < 1`, `1 < t`, `t > f`) stay
  empty in both engines today; `t > f` already throws natively
  ("Comparison operators are not defined for Boolean operands") and is
  accepted by both is_valid classifiers.

## Suggested FIX anchors
- QA-001: `extensions/fhirpath/src/fhirpath/evaluator.cpp` comparison branch
  (~8660-8675): replace the two terminal `return {};` sites with
  `FHIRPathSpecError` using the Python-core message form
  `Type of "X" (T) did not match type of "Y" (T). InequalityExpression`
  (do NOT touch the temporal-precision/quantity-unit empty returns above
  them); add that message prefix to `FhirpathIsValidFunction`'s accepted
  execution-error list (fhirpath_extension.cpp ~1875-1888) mirroring
  udf.py `_is_valid_empty_result_error`. Rebuild + redeploy
  `fhirpath.duckdb_extension`.
- QA-002: `fhir4ds/fhirpath/engine/invocations/equality.py` `_compare`
  typecheck (~604-612): drop `FP_Time` from the two str→temporal coercion
  branches (keep `FP_Date`/`FP_DateTime`), making time-string ordering
  raise InequalityExpression → wrapper empty, matching native and the
  String→Time Explicit-only convention.
