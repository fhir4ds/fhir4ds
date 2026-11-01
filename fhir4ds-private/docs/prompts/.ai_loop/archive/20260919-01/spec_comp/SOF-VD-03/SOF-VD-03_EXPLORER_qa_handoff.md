# QA Handoff — SOF-VD-03 EXPLORER (launch 3, iteration 1)

Personality: EXPLORER. Chunk: SQL-on-FHIR v2 ViewDefinition — Key Elements: Select
(select 1..*, column 0..*, column.path/name/description, multiple selects + ordering,
root vs select-relative contexts). Probes: .temp/qa/sofvd03_explorer/probe{1,2,4,5}.py
plus two inline corrected probes (.temp/sofvd03_explorer_p3.py and stdin P7/P8/parity).

## Probes executed (all e2e through native C++ extension; parity spot-checks vs forced Python fallback)

1. Deep nesting (5- and 6-level selects/forEach chains): column ordering deterministic
   at depth (L0..L4g exact), SQL byte-identical across two generator instances,
   %resource/%rootResource resolve correctly at depth 4 inside nested forEach.
2. Sibling selects x unionAll x forEach combinations: verified against the official
   fixture model — unionAll arms = enclosing select's columns + branch columns (the
   branch rows CARRY the enclosing columns, and there is NO standalone base row when
   unionAll exists; matches union.json "unionAll + column" fixture). Union rows
   evaluated per focus of the enclosing forEach. unionAll-only selects inside forEach
   emit just union rows; unionAll inside a plain nested select works.
3. Complex FHIRPath in column.path at nested contexts: where(use=...).first().family,
   iif(), substring(), & concatenation, where($this=...) — all evaluate relative to the
   active focus (correct: bare `id`/`gender` inside a forEach contact select are empty;
   authors must use %resource). No guard misfires.
4. NULL propagation: empty columns (absent paths) mixed with populated siblings do
   NOT suppress rows; base/union rows carry NULLs correctly.
5. unionAll branch column-order mismatch: rejected with branch diff (order-sensitive
   comparison). Type mismatch across branches (code vs string/date): rejected — verified
   spec-correct per models.fsh unionAll invariant "must produce the same column names
   and types" (NOT A BUG; stricter than fixture coverage which only tests names/order).
6. Deep name collisions: grandparent-vs-grandchild and grandparent-vs-great-grandchild
   duplicates rejected at PARSE time (ParseError, not just generation); unionAll branch
   column colliding with enclosing select column also rejected.
7. collection=true at depth: aggregates the full list at 2- and 3-deep forEach levels
   (incl. %resource-absolute collection paths); string-focus $this columns guarded
   correctly (complex focus without column.type properly errors).
8. description retention: markdown + unicode + emoji + 5000-char description survives
   to_dict() verbatim and executes; non-string description rejected ("must be a
   markdown string").
9. Native vs forced-Python-fallback parity on a 5-level mixed view (collection +
   %resource + iif at depth): row-for-row identical.

## False alarms resolved (my probe-expectation bugs, behavior is spec-correct)
- "0 rows" cases were empty-part suppression from focus-relative paths (address under
  name focus, name.given on PATIENT without name, root address absent) — correct per
  processing_model.md.
- Earlier launches' semantics re-confirmed: sibling selects CROSS JOIN; unionAll arm
  composition per union.json fixture.

## Issues
NONE. Zero CRITICAL/HIGH/MEDIUM/LOW issues opened. Clean-exit eligible (iteration 1
>= min_iterations=1, zero non-terminal issues).

## Gates (fresh runs, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest: 1171/1171 passed.
- ViewDef conformance: 144/144 (100.0%), report schema validation PASSED.
- Master gate: see architect_handoff.md (run launched from final tree).
- Binaries unchanged: fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a,
  repo bundle == site-packages. No code changes this launch.
