# QA Handoff — SOF-VD-01 SKEPTIC (ViewDefinition basics)

## Verdict: CLEAN — 12 fresh dual-path cases, 0 parity diffs

Basic tabular projection (3 patients, id+gender); missing optional path -> NULL
(not error); forEach on absent path -> 0 rows (zero-or-more rows per resource
instance); multi-select with forEach (no name data -> parent-column rows only);
missing 'resource' field -> typed ParseError (resource 1..1 required binding);
bogus resource type -> ParseError (required ResourceType binding); shared-table
mode ('resources' source_table with 3 Patients + 1 Observation) correctly
filters by resourceType top-level $.resourceType (Observation excluded from the
Patient view AND the Observation view picks only o1); profile 0..* canonical
accepted (informative, rows unchanged); fhirVersion '4.0.1' accepted;
'3.9.9' rejected (required FHIRVersion binding); root where filters rows.

All rows identical native == fallback. 3 EXC rows are the REQUIRED typed
ParseError surface (both engines identical).

Evidence: .temp/qa/speccomp2/sofvd01_skeptic_probe1.py
