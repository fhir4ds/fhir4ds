# QA Handoff: SOF-VD-07 EXPLORER

Scope: SQL-on-FHIR ViewDefinition `select.repeat` with EXPLORER personality.

Spec basis:
- SQL-on-FHIR latest ViewDefinition defines `repeat` as a list of FHIRPath expressions that recursively traverse from the current context node, apply each path at every depth, and union all results from all paths and levels.
- SQL-on-FHIR definitions list `ViewDefinition.select.repeat` as `0..* string` and the `sql-expressions` invariant allows at most one of `forEach`, `forEachOrNull`, or `repeat` at a single select level.

Fresh probes:
- `.temp/qa/sof_vd07_explorer_probe.py`
- Parser/serializer/generator malformed repeat boundaries: present null, empty array, scalar string, object, empty path item, and non-string item.
- Nested execution: repeat with overlapping paths, repeated-node `where`, child `forEachOrNull`, `$this` column context, `%rowIndex`, `$this` self-traversal, direct `fhirpath_repeat` malformed path arrays, and deep raw JSON.
- Native-loaded DuckDB and forced Python fallback were both exercised where available.

Result:
- No product defects found.
- One intentional behavior noted: physical SQL row order after a repeat-level filter is not a conformance signal by itself; `%rowIndex` is the stable traversal-position output.

Validation:
- Fresh probe: PASS.
- Focused repeat/parser/generator pytest: 20 passed.
- Full ViewDefinition pytest: 952 passed.
- ViewDefinition conformance: 134/134.
- Full conformance: 2822/2822.
