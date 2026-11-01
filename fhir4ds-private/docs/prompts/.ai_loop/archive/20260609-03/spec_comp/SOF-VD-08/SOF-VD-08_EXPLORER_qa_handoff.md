# QA Handoff: SOF-VD-08 EXPLORER

Scope: SQL-on-FHIR ViewDefinition `select.unionAll`, EXPLORER rerun from fresh
state. Spec anchors: SQL-on-FHIR v2.0.0 ViewDefinition `unionAll` says it
creates a union of all rows in selection structures; union branches must match
column count/name/order/types; duplicate rows are not filtered; parent/child
and sibling selects compose recursively; `forEachOrNull` preserves a row with
null values for an empty collection.

Fresh probe: `.temp/qa/sof_vd08_explorer_probe.py`.

Hypotheses tested:
- Duplicate-preserving `UNION ALL` semantics for identical branch rows.
- Root `where` and branch-local `where` filters stay scoped to their rowsets.
- `forEachOrNull` union branches preserve null-valued child rows while sibling
  branches still emit ordinary rows.
- Nested `unionAll` composes as ordinary rowsets.
- `repeat` branches with branch-local filters behave identically across native
  DuckDB FHIRPath and forced Python fallback.
- Present empty official JSON `unionAll: []` is rejected, while direct
  dataclass `Select.unionAll=[]` remains the omitted/default state.
- Mismatched/missing branch schema and malformed direct dataclass union items
  fail before SQL execution.

Result: no product defects found. Issues logged: 0.

Validation:
- Fresh EXPLORER probe: PASS.
- Focused parser/generator/union/iterator pytest: `82 passed, 258 deselected`.
- ViewDefinition conformance: `134/134`.
- Full conformance: `2822/2822`.
