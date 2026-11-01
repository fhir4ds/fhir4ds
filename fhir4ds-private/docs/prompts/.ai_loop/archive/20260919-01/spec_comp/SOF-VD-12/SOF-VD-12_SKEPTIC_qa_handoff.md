# QA Handoff — SOF-VD-12 SKEPTIC (iteration 1, 2026-08-23)

## Probed (workspace .temp/qa/sof_vd12_skeptic/)
Shareable/Tabular profile enforcement, canonical metadata round-trip
(publisher/experimental/purpose/copyright/contact/useContext/identifier/mapping/
language/text/extension), title/version round-trip, XML rejection, status binding,
versioned meta.profile canonicals, DuckDB end-to-end execution of the official
ShareablePatientDemographics example.

## Verified-good
- All CanonicalResource/DomainResource metadata retained verbatim through
  from_dict/to_dict (extra_fields bag); official field names; no internal leakage.
- XML input explicitly rejected with a clear ParseError (documented stance in
  viewdef/AGENTS.md) — spec has no normative XML syntax for VD; OK.
- status PublicationStatus binding, versioned canonical `url|ver` in meta.profile
  handled (| stripped), DuckDB execution of profiled VD works end-to-end
  (Patient/pat1, male, "John Q", Doe).
- Engine enforces Shareable/Tabular at parse AND to_dict time (runner-level
  enforcement of validator-level profiles — documented stance, consistent).

## Finding
- QA-001 (HIGH, OPEN): profile recognition uses invented canonical URLs
  https://sql-on-fhir.org/ig/StructureDefinition/{Shareable,Tabular}ViewDefinition.
  Every published form of these profiles (upstream repo since their introduction
  2026-08-06, and build.fhir.org/ig/HL7/sql-on-fhir) uses
  http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/... — so official
  examples declaring the profiles get ZERO enforcement (url/name/fhirVersion/
  column.type min-1 and no-collections/primitives-only all skipped).
