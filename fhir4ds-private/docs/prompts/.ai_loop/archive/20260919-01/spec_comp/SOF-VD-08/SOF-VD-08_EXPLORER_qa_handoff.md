# QA Handoff — SOF-VD-08 EXPLORER (iteration 1, 2026-08-23)

Personality: EXPLORER (chaos/boundary). Chunk: ViewDefinition.select.unionAll.

## Probes executed (.temp/qa/sof_vd08_explorer/probe1.py, native + forced-Python fallback, identical results)

- P1 24-branch unionAll: 24 rows, 12 identical 'p1' duplicates preserved; SQL is a flat 23x UNION ALL chain. PASS
- P2 3-level unionAll-in-unionAll: correct expansion (4 rows incl. both id branches); flattened chain. PASS
- P3 forEachOrNull wrappers at max nesting (branch-level, under forEach under outer forEachOrNull): each branch emits its own null row (HISTORIAN fix holds at depth). PASS (P3a observation: no-contact case emits 2 rows via the outer forEachOrNull wrapper path — wrapper null row carries nested union arms as independent selection structures; consistent with Process(S,N) step 3 + step 4 arm model)
- P4 mixed populated/empty branches: plain column branches emit NULL rows (column-empty != row suppression). PASS
- P5 where at every scope (enclosing select where + branch where + nested select where) with forEach: conforms to pinned doctrine "where on a forEach select filters ITERATED nodes" (consistent with repeat+where pin). %rowIndex resets per branch. PASS
- P6 %constants in unionAll branches: plain %lbl works; **%`lbl` backtick form silently NULL — QA-001 HIGH**
- P7 collection=true across branches: same-element-type OK; mismatched ELEMENT types with column.type unset on BOTH sides accepted — schema check compares declared schemas (name/type/collection), unset==unset; reference impl (sof-js unionAll()) only compares column NAMES, so fhir4ds is stricter, not laxer. INTENDED. Explicit mismatched types rejected (verified). Boolean 'true' string rendering is the pinned column-serialization doctrine, union-independent.
- P8 unionAll sibling to plain nested select in same parent: correct 2x2 cross-join. PASS
- P9 resource-type-mixed contained feeding where-routed branches: PASS
- P10 %rowIndex in nested-union arms inside forEach stacks: resets per arm, duplicates preserved. PASS

## Spec ground truth verified (downloaded IG zip from releases branch, ig/2.0.0)

- StructureDefinition-ViewDefinition 2.0.0 snapshot: `where` exists ONLY at ViewDefinition root (filters resources); select backbone has NO `where` child (children: column, forEach, forEachOrNull, select, unionAll). fhir4ds's select.where is a draft-spec extension; its per-iteration evaluation on forEach selects is fhir4ds doctrine, not 2.0.0-spec-testable.
- Process(S,N): columns evaluate against iterated focus f; unionAll is appended as ONE part (urows) — the arm model pinned by prior launches is correct.
- Official fixtures never combine element-level where with forEach, nor forEachOrNull with unionAll (fixture-invisible bug classes confirmed for a third time).

## Issue

- QA-001 HIGH OPEN: backtick-quoted constant references (%`name`, legal FHIRPath) silently resolve to NULL/empty instead of the constant value, in where and column paths (incl. unionAll branches). Root cause: iter_constant_references skips the backtick region after %. See evolution.json.

Handing to Remediation Engineer.
