# QA Handoff — SOF-VD-05 SKEPTIC (iteration 1, 2026-08-23)

## Scope
Nested select (`select.select` 0..* recursion) and "nested select contentReference".
Spec anchors verified this launch:
- v2 SD 2.0.0 (releases branch `ig/StructureDefinition-ViewDefinition.json`, fetched
  fresh) and 3.0.0-ballot (main XML): `select.select` is a contentReference to
  `ViewDefinition#ViewDefinition.select` — an SD recursion mechanism, NOT a
  user-facing field. No per-element contentReference exists in any v2 version.
- `input/pagecontent/functional-model.md` (fetched fresh): select(rows1, rows2)
  cross-joins rowsets; forEach/forEachOrNull unnest; child select without iterator
  inherits parent context ($this).
- Official validator `FHIR/sql-on-fhir.js sof-js/src/validate.js`: select items
  `additionalProperties: false`; select/column arrays `minItems: 1`.

## What was probed
Probe: `/mnt/d/fhir4ds/.temp/qa/sof_vd05_skeptic/probe.py` — 17 behavioral
hypotheses + 2 native/fallback parity checks, all executed through parser →
SQLGenerator → DuckDB (native C++ and forced Python fallback).

Verified conformant (no action): child context = iterated element under parent
forEach (H1); $this default context when no iterator (H2, H2b); parent columns
constant across child iterator rows / cross-join composition (H3, H11); duplicate
name rejection across parent/child, siblings, and depth-3 nesting (H4, H4b, H10);
empty nested select object `{}` = identity rowset (H5); 4-level mixed nesting
(H6); null-preserved rows under forEachOrNull with collection columns NULL (not
[]) vs existing-row empty-path collections [] (H8); child-local where (H9),
nested where null-guard under forEachOrNull (H16); double unnest (H13, inner
forEach keeps INNER semantics); %rowIndex reset per nesting level (H14); root
where propagates to nested rows (H15); %resource absolute path at depth (H17);
nested unionAll under non-iterator parent (H12); native==fallback parity (P1, P2).

## Issues found
- QA-001 MEDIUM (RESOLVED): select-level unknown fields (e.g. `contentReference`,
  `columns` typo) silently accepted and dropped — official validator rejects
  (additionalProperties:false). Silent-wrong-results hazard.
- QA-002 MEDIUM (RESOLVED): present-empty `column: []` and nested `select: []`
  accepted — official validator requires minItems:1.
- QA-003 LOW (INTENDED): the mandate's "contentReference changes context without
  creating rows" framing is FHIR-SD terminology; SQL-on-FHIR v2 has no such field.
  Behavior is already spec-correct; documented.

## Gate status after QA (pre-fix baseline recorded)
ViewDef pytest suite and conformance run in FIX phase post-fix: 1185/1185,
144/144, 2832/2832.
