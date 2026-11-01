# Architect Handoff — SOF-VD-05 HISTORIAN (iteration 1, 2026-08-23)

## Compression of QA + Engineering
HISTORIAN launch on nested-select recursion chunk. 19/19 behavioral probes passed
(`/mnt/d/fhir4ds/.temp/qa/sof_vd05_historian/probe.py`): both prior SKEPTIC fixes
re-verified regression-free at depth-3 and inside unionAll branches; NEW
compositions (forEachOrNull-parent + child-forEach suppression/null-preservation,
per-focus where under forEach, unionAll branch containing nested select+forEach,
%rowIndex reset in nested unionAll branch, nested select under repeat, constants
in depth-3 nested where, duplicate names across nested/unionAll at depth,
25-level nesting, %resource at depth) all conformant with native==fallback parity.
Only issue: QA-001 LOW INTENDED — fhirpath_repeat collects only complex (dict)
elements (primitive-yielding repeat returns empty, both engines); repeat is absent
from the v2 SD and pinned only by legacy fixtures that traverse objects. No code
changes this launch.

## Structural health
Golden standard: `.temp/architect/golden_standard_sof_vd05_historian.md` (8
invariants). No violations; no open Architecture Drift entries for viewdef.
Category counts: SPEC_VIOLATION 0, API_CONTRACT 0, DATA_HANDLING 0,
PERFORMANCE 0, REGRESSION_RISK 0, SPEC_GAP_UNPINNED 1 (INTENDED).

## QA Enforcer Gate
QA was sufficient: probed parser validation, SQL generation, DuckDB execution,
official fixture gate, dual-engine parity, and memory-guided NEW divergences
rather than re-running SKEPTIC probes. RETRY_QA = false.

## Validation (final tree)
ViewDef pytest 1185/1185; conformance gate fresh: ViewDefinition 144/144,
FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832. Binary md5s
(repo == site-packages): fhirpath 57d0634b6ee6eddee9fc06a1355bef5a, cql
c5b22d58310c1eb7bafa17ce7877f989.

## Recommended Fix Order
None — zero non-terminal CRITICAL/HIGH/MEDIUM issues at min_iterations → CLEAN exit.
