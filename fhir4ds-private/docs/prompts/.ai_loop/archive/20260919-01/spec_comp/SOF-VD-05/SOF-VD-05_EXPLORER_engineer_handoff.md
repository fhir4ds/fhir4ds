# Engineer Handoff — SOF-VD-05 EXPLORER (iteration 1, 2026-08-23)

## Issues assigned
- QA-001 (LOW, INTENDED): backtick constant-reference form `%\`name\`` errors as an
  undefined FHIRPath environment variable. Verified against spec: SQL-on-FHIR v2 defines
  constant substitution only via `%[name]` placeholders ("Using Constants", ViewDefinition
  notes). The FHIRPath engine behavior is correct. No fix required; status INTENDED.

## Actions
No code changes. No open CRITICAL/HIGH/MEDIUM issues existed to remediate.

## Post-build verification (fresh runs against final tree, PYTHONPATH=/mnt/d/fhir4ds)
- ViewDefinition conformance: 144/144 (100%).
- Master gate (`conformance/scripts/run_all.py`): 2832/2832, 100% — baseline held, no regression.
- `pytest fhir4ds/viewdef/tests`: 1185 passed.
- Native binary integrity (no C++ changes this launch): repo bundle and site-packages
  fhirpath.duckdb_extension md5 = 57d0634b6ee6eddee9fc06a1355bef5a (identical).

## Reproducers
Probe scripts retained at /mnt/d/fhir4ds/.temp/qa/sof_vd05_explorer/probe1.py and inline
batches (documented in qa_handoff.md).
