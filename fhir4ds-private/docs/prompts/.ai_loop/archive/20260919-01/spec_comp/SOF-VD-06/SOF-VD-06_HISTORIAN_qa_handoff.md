# QA Handoff — SOF-VD-06 (select.forEach / forEachOrNull), HISTORIAN iter 1

## Approach
Institutional-memory-driven: read SKEPTIC prior handoff + canonical SD (ViewDefinition v2 snapshot) + spec IG notes (Process semantics, union examples), then hunted NEW divergences not covered by the SKEPTIC pass. Harness: /mnt/d/fhir4ds/.temp/qa/sof_vd06_historian/ (p1-p10).

## Probed (new ground vs SKEPTIC)
- column+forEach on same select: WORKS and is the canonical spec usage (SD definition text: "columns defined in the corresponding column structure"); parent refs via %resource.id correct.
- column.constant field: correctly rejected (SD Column has no `constant`; constants are top-level `constant` array; singular-vs-plural mispell also rejected with helpful message).
- forEach over mixed primitive collection (name.family | identifier.value): correct flatten.
- forEach over explicitly empty JSON array element (name[1].given=[]): correct — contributes 0 items.
- Key/%rowIndex typed integer column under forEach; getResourceKey() under forEach (Patient/p1): correct.
- collection=true column under forEach: [] on real focus vs SQL NULL on preserved forEachOrNull row — both Process-correct.
- forEach inside unionAll branch (canonical spec example patient-addr vs contact-addr, incl. `true`/`false` literal columns): exact expected output.
- unionAll nested UNDER a forEach select (columns + unionAll branch): cartesian per iterated focus, correct.
- unionAll branch column-name mismatch: rejected with clear error.
- Duplicate column names across forEach select tree: rejected.
- column.tag under forEach: accepted, ignored for output.
- Nested forEach x forEach (address.line): correct row multiplication and values; %rowIndex resets per parent; %rootResource.id correct from depth 2.
- Sibling iterators cross join: correct.
- %parent: NOT a v2 builtin (constants.py = rowIndex/context/resource/rootResource/ucum) — correctly rejected as undefined constant.
- resourceType extraction under iteration of heterogeneous contained: correct (initial suspicion was my harness bug: stray `contained` key inside view dict is ignored by parser).
- fhirpath vs fhirpath_json UDF agreement on iteration inputs (len/alignment for unnest json_extract): consistent.

## False alarms during probing (recorded to save future time)
- Harness norm() json.loads numeric strings ("11111" -> 11111) — don't trust raw types through it.
- View dict keys like `contained` inside the VIEW are silently ignored by parser — fixtures must go in the resource.

## Issues
Zero CRITICAL/HIGH/MEDIUM. Two LOW spec observations logged (QA-001 forEach+unionAll same select spec-silent combo, INTENDED; QA-002 no normative row ordering under nested laterals, INTENDED). Prior SKEPTIC LOW pins unchanged.

## Gates (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- pytest fhir4ds/viewdef/tests: 1185 passed.
- run_viewdef.py: 144/144 (100%).
- Master gate run_all.py: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## Verdict
Clean-exit eligible at min_iterations=1. No code changes required.
