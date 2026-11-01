# QA Handoff — SOF-VD-08 (select.unionAll), SKEPTIC, iteration 1

Probes: /mnt/d/fhir4ds/.temp/qa/sof_vd08_skeptic/ (p1.py, p2.py, p3.py + harness.py)

## Probed and PASSED (spec-conformant)
- UNION ALL duplicate preservation: two identical branches on same resource -> 2 identical rows (not deduped).
- Branch missing a column entirely -> ValidationError (names+order check). Column ORDER mismatch -> rejected. Column TYPE mismatch -> rejected (stricter pin, SOF-VD-03).
- Empty unionAll array -> ParseError ("must contain at least one JSON object").
- Single-branch unionAll works.
- Nested unionAll (unionAll inside a unionAll branch) -> correct 3-row expansion.
- forEach + unionAll on same select: arm model (enclosing columns carried on branch rows), branch column per focus; Cartesian semantics vs nested selects (2x2 = 4 rows); enclosing where filters union rows; branch-level where scopes to branch only; all-empty branches suppress parent (empty Cartesian part); one-empty-branch keeps others.
- repeat inside unionAll branch works (plain select wrapper); %rowIndex resets per branch (0,1 / 0,1).
- forEachOrNull INSIDE unionAll branches: per-branch null rows emitted (matches official fixture "empty with forEachOrNull").
- Wrapper forEachOrNull + unionAll alone: exactly ONE all-null row per Process(S,N) step 3 (correct; suppression of non-first alternatives is the right idea).
- Focus-relative column paths inside branches under iterators (repeat/forEach relative to iterated focus) — several of my initial "expected" values were wrong, engine was right; re-derived from Process(S,N) step 2.
- P1 (union rows present, sibling forEachOrNull populated) cross join correct.

## QA-001 (HIGH, OPEN): sibling forEachOrNull null row wrongly suppressed across unionAll alternatives
- View select=[{unionAll:[...]}, {forEachOrNull: telecom, ...}], telecom absent: expected 2 rows (s1's 2 union rows x s2's 1 null row), got 1 (second alternative loses sibling null row).
- Worse: select=[{forEachOrNull: telecom, unionAll:[a,b]}, {forEachOrNull: telecom, ...}] absent: expected 1 row, got 0.
- Root cause: _generate_single_resource tracks seen forEachOrNull paths by string across alternatives and suppresses any top-level select whose path repeats — including independent siblings that are not union wrapper copies. Per Process(S,N), each S.select part emits its own null row; only the union-expansion wrapper copies should be suppressed (one null row per wrapper across the entire structure).
- Engine-independent (reproduced under native fhirpath extension).

## Not-a-bug pins re-confirmed
- Identical-row dedup does NOT occur across branches (UNION ALL); value-dedup only inside FHIRPath `|` unions (SOF-VD-07 pin).
- Branch schema = same names AND types AND order (models.fsh invariant, stricter than fixtures).
- unionAll row order across branches: implementation emits branch order; never order-assert (SOF-VD-05 pin).
