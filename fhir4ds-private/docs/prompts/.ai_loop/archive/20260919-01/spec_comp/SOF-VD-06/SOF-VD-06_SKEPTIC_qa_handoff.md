# QA Handoff — SOF-VD-06 (select.forEach / select.forEachOrNull), iter 1, SKEPTIC

## Probed (behavioral, DuckDB execution via generated SQL; harness in /mnt/d/fhir4ds/.temp/qa/harness.py)
- Parser validation: forEach+forEachOrNull / forEach+repeat on same select rejected (ParseError); forEach non-string / empty / whitespace-only rejected; invalid FHIRPath in forEach rejected at validation. Duplicate `forEach` JSON keys accepted via JSON last-wins (matches reference JSON.parse) — NOT A BUG (QA-001).
- Row multiplication: 0 items → 0 rows; 1 item (singleton incl. `gender`, `count()`, boolean) → 1 row; N items → N rows. Primitives (name.given strings) iterate fine; contained resources iterate fine.
- forEachOrNull empty → exactly ONE row; parent columns preserved; nested columns null (incl. collection=true columns → SQL NULL, per Process step 3); %rowIndex bound to 0 (per Process step 3.1).
- collection=true column with empty result on a REAL iterated row → [] (Process step 2), vs null on preserved row — both correct.
- Nested forEach under forEachOrNull when outer foci empty → single null row preserved (QA-005 fix still holds); when outer non-empty and child empty → row dropped (Process step 2) — correct.
- Nested forEachOrNull under forEach with empty child → null row preserved.
- %rowIndex: 0-based; independent per nesting level; resets per parent; top-level = 0; sibling iterators have independent sequences (cartesian product semantics).
- %context in iterated contexts tracks the iterated item (matches Process: `fhirpath(col.path, f)`; consistent with reference impl envVars). %resource / %rootResource resolve to the root resource under iteration. Mixed-context expressions correctly rejected per existing doctrine.
- select.where + forEach on same select: where evaluated per iterated item (QA-002, doctrine note; v2 removed select.where so no normative conflict; reference impl drops where on forEach selects entirely).
- Fixtures: local spec_tests/{foreach,row_index,where}.json byte-identical to upstream FHIR/sql-on-fhir.js tests (13+9+8 cases, no missing).
- Formal semantics verified against canonical ViewDefinition-notes Process(S,N) (fetched from FHIR/sql-on-fhir-v2 main): no divergence found.

## Gates
- pytest fhir4ds/viewdef/tests: 1185 passed.
- run_viewdef.py: 144/144 (100%).
- Master gate run_all.py: launched; result recorded in architect_handoff.

## Verdict
Zero CRITICAL/HIGH/MEDIUM issues. Two LOW spec observations (QA-001, QA-002) documented, no code change required. Clean-exit eligible at min_iterations=1.
