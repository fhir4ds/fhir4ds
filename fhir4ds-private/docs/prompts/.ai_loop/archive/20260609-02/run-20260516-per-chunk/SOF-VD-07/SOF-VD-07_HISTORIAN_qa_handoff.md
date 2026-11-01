# QA Handoff — SOF-VD-07 HISTORIAN

Scope: SQL-on-FHIR ViewDefinition `select.repeat` from active `evolution.json`, using fresh source reads and fresh probes only.

Spec anchors checked:
- SQL-on-FHIR ViewDefinition.select: `repeat` is a 0..* FHIRPath string field and the sql-expressions invariant allows only one of `forEach`, `forEachOrNull`, or `repeat`.
- FHIRPath uses a current context/focus item; FHIR also documents `$this` as a focused element reference in simple FHIRPath contexts.

Fresh probes:
- Parser/direct generator repeat shape and mutual-exclusion boundaries.
- Generated SQL for quoted repeat expressions.
- Native-loaded and forced Python fallback DuckDB execution for recursive repeat traversal, multi-path union behavior, deep nesting, and column evaluation against repeated nodes.

Finding:
- `QA-001` HIGH CONFIRMED: forced Python fallback evaluates a column path `$this.linkId` inside `select.repeat` as NULL, while native/C++ returns the repeated node's `linkId`. Plain `linkId` works in both, so the repeated node is present and the explicit `$this` current-focus path is the divergent behavior.

Reproducer:
- `.temp/qa/sof_vd_07_historian_probe.py 64`
