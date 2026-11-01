# QA Handoff — SOF-SQ-01 (SKEPTIC, iteration 1)

## Spec truth pinned (machine-readable artifacts, /mnt/d/sql-on-fhir-v2, branch upstream/sqlquery-view-sources — newest branch containing the SQLView profile; upstream/sqlquery is older)
- IG canonical: `http://hl7.org/fhir/uv/sql-on-fhir` (sushi-config.yaml) → official profile canonicals `http://hl7.org/fhir/uv/sql-on-fhir/StructureDefinition/{SQLQuery,SQLView}`. The mandate's two-host canonical list (sql-on-fhir.org/ig + sql-on-fhir.org) matches NEITHER the official base nor itself consistently; per machine-artifact-outranks-prose rule, recognition must accept official + legacy forms (precedent: viewdef/metadata.py dual-form frozensets).
- `LibraryTypesCodes` defines BOTH `#sql-query` and `#sql-view`; SQLQuery profile fixes type=sql-query, SQLView profile fixes type=sql-view.
- `sql-must-be-sql-expressions`: `content.all(contentType.startsWith('application/sql'))`.
- contentType binding: required mimetypes + extensible AllSQLContentTypeCodes (dialect variants incl. duckdb; out-of-value-set codes permitted) — impl's startswith + UnsupportedDialectError-at-runner is correct.
- SQLView: `parameter 0..0`; SQLQuery: `parameter MS` only — NOT 1..* (mandate prose wrong; impl 0..* correct — NOT A BUG).
- relatedArtifact: type fixed `#depends-on`, resource Canonical(ViewDefinition or SQLView), label obeys `sql-name` = `^[A-Za-z][A-Za-z0-9_]*$` (ASCII).
- parameter.use 1..1 (no defaulting); name/type 1..1.

## Issues found (all reproduced via PYTHONPATH=/mnt/d/fhir4ds probes)
- QA-001 HIGH: official hl7.org/fhir/uv canonicals rejected by _detect_profile.
- QA-002 HIGH: SQLView must use type code 'sql-view'; impl requires 'sql-query' for both → spec-valid SQLView rejected, invalid one accepted.
- QA-003 MEDIUM: base64.b64decode without validate=True; '%%%%' decodes to empty SQL and passes.
- QA-004 MEDIUM: parameter.use missing is defaulted to 'in' instead of rejected (use is 1..1).
- QA-005 MEDIUM: sql-name check uses isalpha() → unicode labels ('éfoo') accepted; regex not enforced.
- QA-006 MEDIUM: no to_dict roundtrip for extra_fields (mandate item).

## Verified-correct (no issue)
Ambiguous both-profiles rejection; versioned canonical `|x` matching; missing/wrong profile, missing content, wrong resourceType, bad JSON, non-dict input → typed SQLQueryParseError; SQLView parameter 0..0 rejection; text/plain rejected by invariant; parse_sqlquery/parse_sqlview strictness; public API exports.
