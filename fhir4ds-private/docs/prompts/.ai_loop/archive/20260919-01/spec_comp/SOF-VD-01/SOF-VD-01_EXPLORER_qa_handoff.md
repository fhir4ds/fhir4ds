# QA Handoff — SOF-VD-01 EXPLORER (iteration 1, 2026-08-23)

Personality: EXPLORER (fuzzer/abuser). Probes at
`fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd01_explorer/` (inline
probes, summarized below).

## Probed
- `ViewDefinition.resource` edge shapes: lowercase ('patient'), whitespace
  (' Patient '), empty string, unicode ('Patiënt'), 300-char, valid control.
  All invalid forms correctly rejected by the required ResourceType binding.
- `fhirVersion`: every natural code form. **QA-001 (HIGH)**: only the 24
  top-level codes ("4.0","5.0","6.0",...) are accepted; full-spec codes
  ("4.0.1","4.3.0","5.0.0","6.0.0","1.0.2", plus "-cibuild"/"-snapshot"/
  "-ballot" variants and 0.0.x codes) are rejected. Verified against
  build.fhir.org ValueSet-FHIR-version (codesystem include, no filter =>
  all concepts) and CodeSystem-FHIR-version concept list.
- `profile`: relative URLs, versioned canonicals with `|`, `urn:uuid:`,
  `#fragment` forms, duplicates, 150 entries — all parsed and executed;
  profile-declared-but-absent data correctly NOT filtered (informative).
- resourceType filtering on shared source_table: contained resources and
  Bundle-entry nested Patients correctly excluded; only top-level matches.
- Zero-output-row VDs through `where` and `forEach` with empty foci: [] rows.
- fhirVersion interaction: VD declaring 4.0 with an R6-only field path
  evaluates to NULL (no filtering) — engine stance consistent with
  informative semantics.
- Multiple VDs (different and same resource types) through one DuckDB
  session and one reused SQLGenerator: `_current_resource_type` re-set per
  generate; correct per-view results; CREATE OR REPLACE VIEW naming clean.
- End-to-end execution for everything above (register_fhirpath native path).

## Findings
- QA-001 HIGH (OPEN): FHIR_VERSION_CODES incomplete — rejects valid
  fhirVersion codes like '4.0.1' / '5.0.0' / '6.0.0'. See evolution.json.

## Baseline
Not yet re-run (QA phase is read-only). Fix must re-run ViewDef 144 + master.
