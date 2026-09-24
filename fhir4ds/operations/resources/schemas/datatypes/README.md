# Vendored FHIR R4 datatype StructureDefinitions

Source: https://hl7.org/fhir/R4/<name>.profile.json (R4 v4.0.1 published
snapshots), fetched 2026-09-23 for the CQL Cleanroom recursive resource
builder (FEATURE_CLEANROOM_TEST_DATA_AUTHORING.md).

Scope: 26 complex-type + 19 primitive datatype SDs with FULL `snapshot`
element lists (the translator's `fhir4ds/cql/resources/fhir/r4/` resource
snapshots are trimmed and intentionally NOT touched — the conformance
firewall reads that directory).

Rules:
- Datatype children of these SDs (e.g. HumanName.period, Quantity.code)
  resolve HERE; resource/backbone elements resolve in the resource SDs.
- Choice (`value[x]`) arms are SYNTHESIZED from element `type` lists
  (snapshots do not materialize arms); contentReference is resolved
  against the RESOURCE SD set.
- Refresh wholesale via the fetch loop in git history if FHIR publishes
  new R4 errata; never hand-edit single files.
