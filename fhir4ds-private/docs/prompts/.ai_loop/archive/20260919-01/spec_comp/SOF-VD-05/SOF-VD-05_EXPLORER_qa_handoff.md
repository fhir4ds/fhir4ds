# QA Handoff — SOF-VD-05 EXPLORER (iteration 1, 2026-08-23)

Personality: EXPLORER. Chunk: nested select recursion (ViewDefinition.select.select).

## Spec ground truth established
Normative row-generation algorithm extracted from the official spec source
(sql-on-fhir-v2 releases branch, `input/pagecontent/StructureDefinition-ViewDefinition-notes.md`,
"Formal Semantics" Process(S,N)):
- Columns in a select are evaluated against the *iterated* focus `f` (so `id` under `forEach: contact` is correctly NULL).
- Sibling selects, nested selects, and unionAll are `parts`; the final row set is the **Cartesian product** of parts — "Sibling selects are effectively cross joined" (explicit in the notes). An empty part (e.g. nested select with no rows) suppresses ALL rows for that focus.
- forEachOrNull with empty foci emits one null row; columns with path `%rowIndex` bind to 0 in that row, others null.
- Constants are referenced via `%[name]` placeholder substitution before evaluation; the backtick form `%\`name\`` is an (undefined) FHIRPath environment variable, not a constant reference.

## Probes executed (all end-to-end DuckDB, native extension path)
- P1 mixed hierarchy forEach(1)>unionAll(2)>forEachOrNull(3)>plain select(4): CONFORMANT (null-preserved telecom row; forEach-suppressed contactless patient).
- P2 columns-only select under 3-level forEachOrNull-null chain: CONFORMANT (single null row, 4 cols, ri=0).
- P3/P5 sibling selects cross-join semantics incl. empty-sibling row suppression: CONFORMANT (initial "mismatch" was my wrong expectation; spec mandates cross join).
- P4 constant in nested where at depth 5: CONFORMANT via `%name` (form `%\`name\`` correctly errors as undefined env var — QA-001 INTENDED).
- P6 heterogeneous unionAll (forEach branch + plain-column branch): CONFORMANT.
- P7 nested forEach with relative complex focus `telecom.where(system='phone').first()`: CONFORMANT.
- P8 name-collision rejection at depth 3 AND depth 10: rejected.
- B1 `%rowIndex` = 0 (not null) in forEachOrNull empty row: CONFORMANT.
- B2 `%rowIndex` independent counters across sibling selects: CONFORMANT.
- B3 unionAll branches with mismatched direct columns: rejected at generate with precise message.
- B4 unionAll where one branch empty: other branch rows survive: CONFORMANT (incl. null-padded plain-column branch).
- B5 10-level identical-path nesting: CONFORMANT; aliases unique/deterministic (B9 two-run SQL identical).
- Cross-branch unionAll schema mismatch discovered only at parse-permissive stage: rejected by `SQLGenerator.generate()` (ValidationError) before execution — documented permissive-parse design, not a defect.

## Issues
- QA-001 (LOW, INTENDED): `%\`constantName\`` backtick form is not a constant reference per spec; engine correctly reports "undefined environment variable". Logged to NOT A BUG registry.

## Validation (fresh, final tree)
- ViewDef conformance: 144/144.
- Master gate: 2832/2832 (100%).
- pytest fhir4ds/viewdef/tests: 1185 passed.
- Binary md5s match repo bundle vs site-packages: 57d0634b6ee6eddee9fc06a1355bef5a.

Zero non-terminal CRITICAL/HIGH/MEDIUM issues. Clean-exit eligible at min_iterations=1.
