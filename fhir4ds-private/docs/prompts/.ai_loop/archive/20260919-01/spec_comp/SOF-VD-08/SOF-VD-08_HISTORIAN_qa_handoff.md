# QA Handoff — SOF-VD-08 (select.unionAll), HISTORIAN, iteration 1

Probes: /mnt/d/fhir4ds/.temp/qa/sof_vd08_historian/probe.py (+ harness.py reused from SKEPTIC).

## Approach
Used institutional memory (SKEPTIC handoffs, AGENTS.md pins) to attack the boundary the SKEPTIC fix did NOT cover: the null-row suppression bookkeeping (`_collect_union_wrapper_ids` + `collected_aliases` zip) only walked the TOP-LEVEL select list, while `_process_selects` collected forEachOrNull aliases "at this level (not recursed)". Hypothesis: nested forEachOrNull+unionAll wrappers escape suppression entirely.

## QA-001 (HIGH, CONFIRMED): nested forEachOrNull+unionAll wrapper emitted one null row PER UNION BRANCH
- P1: `{forEach: contact, select: [col, {forEachOrNull: telecom, unionAll:[2 branches]}]}` with telecom absent -> 2 null rows per contact (expected exactly 1 per focus).
- P1b: 2 contacts -> 4 rows (expected 2). P2: wrapper nested under an empty outer forEachOrNull -> 2 all-null rows (expected 1). P4: wrappers nested inside unionAll branches -> 4 rows (expected 2).
- Spec: Process(S,N) step 3 — exactly ONE null row per selection structure across its unionAll branches (identical rationale to the SKEPTIC fix, which only handled top-level wrappers).
- Populated foci (P5) unaffected; SKEPTIC fix cases (P3 sibling null row) re-verified intact.

## Probed and PASSED (re-verified + new)
- SKEPTIC QA-001 fix: sibling forEachOrNull null rows kept across alternatives; wrapper+same-path sibling single cross-joined null row; wrapper-alone single null row.
- Nested wrapper with populated foci: per-focus x per-branch cross join (4 rows for 2 telecom x 2 branches), no spurious suppression.
- Fixture-invisible bug class confirmed again: official union.json never nests forEachOrNull+unionAll wrappers — only hand-derived Process(S,N) probes catch this.
