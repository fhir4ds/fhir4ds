# Engineer Handoff — SOF-VD-06 (forEach/forEachOrNull), EXPLORER iter 1

## Triage
Zero issues with status NEW/OPEN/CONFIRMED. QA-001 and QA-002 are LOW spec observations logged INTENDED (terminal) — no remediation required:
- QA-001: FHIRPath evaluation error inside a forEach/forEachOrNull expression degrades uniformly to empty (forEach → 0 rows; forEachOrNull → 1 null-preserved row), identical on native and Python fallback. Process(S,N) defines no error semantics; tolerant-empty matches FHIRPath engine convention. No fix.
- QA-002: forEach over %constant lists is not expressible — the v2 SD limits constant value[x] to primitive singletons; parser rejection ('valueCode must be a JSON string') is spec-correct. No fix.

## Code changes
None. Working tree contains no changes authored by this launch.

## Reproducer/regression
No reproducer needed (no defects). Focused regression coverage already exists via 1185 viewdef tests.

## Gates
- viewdef pytest: 1185 passed.
- ViewDef conformance: 144/144 (100%).
- Master gate result: recorded in architect_handoff.md.
- fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a (repo == site-packages) — no native edits this launch.
