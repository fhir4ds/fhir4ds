# QA Handoff — SOF-VD-03 (Select key elements), iteration 1, personality HISTORIAN

## Spec anchors verified (local IG clone /mnt/d/sql-on-fhir-v2)
- input/fsh/models.fsh: select 1..* BackboneElement; column 0..*; column.path 1..1;
  column.name 1..1 obeys sql-name ^[A-Za-z][A-Za-z0-9_]*$; description 0..1 markdown;
  sql-expressions invariant (forEach xor forEachOrNull).
- input/pagecontent/processing_model.md: ValidateColumns algorithm; Process algorithm
  (Cartesian product of parts; an empty part (nested select, unionAll) yields ZERO rows;
  forEachOrNull null-row rule; per-focus unionAll evaluation).
- input/pagecontent/StructureDefinition-ViewDefinition-notes.md: Multiple Select
  Expressions (parent/child repeat, siblings cross joined); Unions (unionAll last).

## Probes executed (workspace /mnt/d/fhir4ds/.temp/qa/sof_vd_03_historian/)
parser validation + SQL generation + DuckDB execution (Python-fallback registration,
plus forced-native re-run; both engines):

1. Empty nested forEach select part suppresses ALL rows (Cartesian with empty part) —
   matches processing_model step 5. PASS (SKEPTIC did not cover this).
2. unionAll part empty when every branch is empty → 0 rows. PASS.
3. unionAll-only top-level select (no own columns) → union rows only. PASS.
4. forEach + unionAll + column in one select: unionAll evaluated per focus
   (address contexts) → 0 rows + correct ordering (column, forEach, unionAll last). PASS.
5. forEach AND forEachOrNull together → ParseError (sql-expressions). PASS.
6. Bare `{}` select beside sibling with columns → accepted, no spurious columns. PASS.
7. Nested forEachOrNull on absent path → single null row, parent columns kept. PASS.
8. Empty/whitespace/non-string column.path and column.name → ParseError. PASS.
9. Two top-level sibling selects → deterministic column order (first select's columns first). PASS.
10. Column path 'true' literal (IG example pattern). PASS.
11. 3-level forEach chain contexts ($this, family, upper()). PASS.
12. collection=false + genuinely multi-valued path → runtime error raised (spec SHALL). PASS.
13. description non-string / null rejected; markdown retained (SKEPTIC-verified). PASS.
14. Default (non-strict) generator: singleton path emits value; multi path raises at
    runtime only; collection=true returns list. Spec-exact. PASS.
15. Native C++ vs Python-fallback parity: identical outputs on 9 column-style FHIRPath
    paths and on 3 full views (columns+forEach+unionAll cross join, forEachOrNull null
    row, collection lists). PASS. (Note: default register_fhirpath in this env fell back
    to Python UDFs; native verified via explicit LOAD with allow_unsigned_extensions.)
16. IG clone /tests/*.json run raw: 60/94 divergences, ALL traced to stale draft-format
    fixtures (missing ViewDefinition.resource, top-level column, legacy "type" keys,
    integer-valued Quantity in fn_boundary). Not implementation bugs. 'top level column'
    is correctly rejected (select 1..*). Authoritative suite = sql-on-fhir.js snapshot.

## Issues
Zero CRITICAL/HIGH/MEDIUM. Two LOW terminal:
- QA-001 DEFERRED (carried): runtime guard message conflates multi-value with
  missing-type; suite pins fragments. Error IS raised — spec-compliant behavior.
- QA-002 INTENDED (process note): /mnt/d/sql-on-fhir-v2/tests/* are stale draft-format
  fixtures, NOT a conformance source; recorded in AGENTS.md.

SKEPTIC's QA-001 preflight-warning fix re-verified in default mode: warning text now
correctly states the runtime guard will raise.
