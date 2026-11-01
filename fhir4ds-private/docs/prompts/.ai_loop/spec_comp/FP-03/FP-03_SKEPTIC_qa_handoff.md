# QA Handoff — FP-03 SKEPTIC (FHIRPath §5.1 Existence)

## Verdict: CLEAN — zero defects (0 issues logged)

~60 fresh dual-path cases across 3 batteries (probe1 35-row matrix,
adjudication battery 10, spec-verbatim battery 20). All PARITY-OK.

## Flagged-row adjudications (11 probe-format + 1 stderr row — all NOT bugs)
1. **Expectation-encoding artifacts (7 rows)**: my expected-strings lacked the
   `["..."]` list-wrapper the fhirpath() UDF returns (n='["false"]' vs exp='false').
   Direct re-verification: values correct on both engines.
2. **`name.all(use = 'official')` → ['false']** — CORRECT per §5.1.3: the Gray
   name has no `use`, so its criteria evaluates empty→false; all() requires
   every item true.
3. **allTrue/anyTrue/allFalse/anyFalse over NON-boolean items → []** — CORRECT:
   §5.1.4-5.1.7 boolean aggregates error on non-Boolean items (row-resilient
   empty at the UDF boundary; one stderr 'scalar evaluation error' row is the
   wrapper's logged-and-swallowed form). Verified on real Boolean collections
   ([true,true,false]→allTrue false/anyTrue true/allFalse false/anyFalse true;
   [true,true]→allTrue true/allFalse FALSE/anyFalse false; vacuous rows
   [f]→allTrue false — wait: all-true of [false,false] is false, all-false true;
   empty input → allTrue true, anyTrue false, allFalse true, anyFalse false —
   all four vacuous cells verified CORRECT per §5.1.4-7 defaults).
4. **subsetOf/supersetOf membership semantics** — `arr.subsetOf(arr.distinct())`
   → true and `arr.distinct().supersetOf(arr)` → true are CORRECT: §5.1.8/§5.1.9
   compare membership, not cardinality; every element of arr IS a member of its
   distinct set and vice versa. My expectations wrongly assumed multiset logic.
5. **`missing.exists(1)` → ['false']** — CORRECT (§5.1.2: exists(criteria) ≡
   where(criteria).exists(); empty input → false).
6. **`missing.all($this > 0)` → ['true']** — CORRECT vacuous truth.

## Evidence
Scripts: .temp/qa/speccomp2/fp03_skeptic_probe1.py (+ inline adjudication
batteries in this run's logs). Dual-path parity held on every case.
