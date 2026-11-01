# QA Handoff — SOF-SQ-01, HISTORIAN launch (iteration 1)

Personality: HISTORIAN (spec-compliance verifier). Chunk: SQL-on-FHIR v2
Analytics Layer — SQLQuery/SQLView Library profiles + sql-must-be-sql-expressions
invariant. Verified against machine-readable artifacts at
/mnt/d/sql-on-fhir-v2 branch upstream/sqlquery-view-sources
(input/fsh/profiles/library-profiles.fsh, terminology.fsh, models.fsh,
sushi-config.yaml canonical http://hl7.org/fhir/uv/sql-on-fhir).

## What was probed

- Full FSH differential of library-profiles.fsh beyond the SKEPTIC's 6 fixes:
  type coding system fixity, base-Library required elements, parameter.type
  binding, relatedArtifact/parameter/content per-entry extras.
- Round-trip byte/semantic fidelity of parse_library -> to_dict for a fully
  populated Library (all FHIR fields, nested arrays).
- Dispatch edge cases: versioned+both profiles in one array (correctly
  rejected ambiguous), canonical case sensitivity (correctly case-sensitive),
  trailing-garbage canonicals (rejected), |version#fragment (accepted,
  lenient), no-match error path (typed SQLQueryParseError).
- Runner symmetry: execute() accepts dataclasses and to_dict dicts
  identically (both paths verified against DuckDB).
- Re-verified the 6 SKEPTIC fixes are regression-free (all its tests still
  pass; official canonical acceptance, sql-view code, strict base64,
  parameter.use 1..1, ASCII sql-name, extra_fields roundtrip).

## Issues found (all logged in evolution.json)

- QA-001 HIGH: to_dict silently dropped known-but-unmodeled Library fields
  (description, publisher, date, experimental, purpose, usage, copyright,
  language, identifier, contact, useContext, jurisdiction, extension,
  meta.versionId/tag, relatedArtifact[].display, parameter[].documentation,
  content[].extension sqlText). Root cause: _KNOWN_LIBRARY_KEYS excluded them
  from extra_fields while to_dict never emitted them.
- QA-002 MEDIUM: to_dict rewrote meta.profile to the legacy
  sql-on-fhir.org canonical even when the official hl7.org canonical was
  declared; dropped type.coding.system/display/type.text.
- QA-003 LOW: parameter.type accepted any non-empty string; 'not-a-fhir-type'
  and complex types only failed later at runner bind time.
- QA-004 LOW: Library.status (base 1..1 required) not enforced.
- QA-005 LOW: type.coding with a foreign code system satisfied the fixed
  LibraryTypesCodes type.

## Verified-correct (no issue)

- Zero-parameter SQLQuery legal (spec MS 0..*; confirmed prior NOT-A-BUG).
- sql-must-be-sql-expressions enforced via startsWith('application/sql').
- sql-name ASCII regex on relatedArtifact.label.
- SQLView parameter 0..0; both-profiles ambiguity rejection.

Baseline before fixes: sqlquery suite 55/55. Handing off to FIX.
