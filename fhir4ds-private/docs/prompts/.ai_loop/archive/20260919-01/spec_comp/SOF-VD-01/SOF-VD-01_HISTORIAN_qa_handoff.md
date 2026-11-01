# QA Handoff — SOF-VD-01, iteration 1, personality HISTORIAN

## Spec ground truth verified (fetched live)
- ViewDefinition SD (IG 3.0.0-ballot, 2026-08-13): resource 1..1 code, required binding http://hl7.org/fhir/ValueSet/resource-types; profile 0..* canonical; fhirVersion 0..* code, required binding http://hl7.org/fhir/ValueSet/FHIR-version.
- valueset-resource-types.json (build.fhir.org): 120 codes incl. new R6 `DeviceAlert`.
- codesystem-FHIR-version.json: 24 codes — fhir4ds/viewdef/metadata.py:FHIR_VERSION_CODES matches 24/24 (prior SKEPTIC fix verified spec-correct).

## Probes (all fresh, .temp/qa scratch)
- resource: Patient/Observation OK; 'patient'/'Resource' correctly rejected; ChargeItem accepted (superset); **DeviceAlert REJECTED → QA-001 (MEDIUM)**.
- fhirVersion: 6.0/4.0/0.01 OK; 4.0.1 / 6.0.0-ballot5 / 5.0.0-snapshot1 correctly rejected; non-list/non-string/dup handled.
- profile: canonical strings, |version, #fragment accepted; non-list, non-string, JSON null rejected. Non-URL string 'not-a-url' accepted at parse AND generate — matches reference-tool leniency (canonical as plain str); NOT A BUG.
- Execution: source_table mixed Patient+Observation → only Patient rows (resourceType filtering correct); `where: id='none'` → 0 rows (zero-or-more rows per resource correct).
- resourceType root metadata: absent OK; must equal the ViewDefinition canonical URL — implementation convention, spec_tests (no resourceType) pass 144/144; NOT A BUG.
- 39 legacy codes accepted but absent from current value set → QA-002 (LOW, intentional cross-version superset).

## Issues
- QA-001 MEDIUM OPEN: DeviceAlert missing from KNOWN_FHIR_RESOURCE_TYPES.
- QA-002 LOW OPEN (note only).

Fix target: add `DeviceAlert` to fhir4ds/viewdef/metadata.py KNOWN_FHIR_RESOURCE_TYPES + focused unit test.
