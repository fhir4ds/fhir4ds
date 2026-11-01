# QA Handoff — SOF-VD-08 SKEPTIC

Scope: SQL-on-FHIR ViewDefinition `select.unionAll`. I started from the active state and current source/tests only; archived prior workflow outputs were not used as evidence.

Spec anchors checked directly:
- SQL-on-FHIR v2.1.0-pre functional model: `select` cross-joins rowsets, `unionAll` concatenates rowsets and preserves duplicates, and `unionAll` does not create a new `%rowIndex` scope.
- SQL-on-FHIR ViewDefinition union/composition text: `unionAll` rows can be used like select rows by containing `select`/`unionAll`; branches must produce matching columns, names, order, and FHIR types.

SKEPTIC hypotheses probed:
1. Multiple sibling `unionAll` groups may be concatenated as independent SQL UNIONs instead of being treated as sibling select rowsets. Confirmed.
2. Nested sibling `unionAll` groups may be lost during hoisting. Related behavior observed when nested union groups under a parent reduced to only parent columns.
3. A branch with direct columns plus nested `unionAll` may have its nested union schema/output ignored. Confirmed.
4. Branch and root `where` filters may bleed across branches. Disproved in the focused probe; root filters applied to every branch and branch filters stayed scoped.
5. SQL `UNION ALL` duplicate preservation may accidentally deduplicate rows. Disproved in the focused probe; duplicates were preserved.

Issues logged:
- QA-001 HIGH OPEN: sibling `unionAll` rowsets are concatenated instead of composed/cross-joined with sibling selects, losing distinct sibling columns.
- QA-002 HIGH OPEN: direct branch columns plus nested `unionAll` silently drop nested union columns.

Reproducer: `.temp/qa/sof_vd_08_probe.py`.
