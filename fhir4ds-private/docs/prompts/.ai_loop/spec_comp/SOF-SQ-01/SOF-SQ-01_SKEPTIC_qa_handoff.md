# QA Handoff — SOF-SQ-01 SKEPTIC (Library parsing)

## Verdict: CLEAN — 16/16 fresh cases (flagged=0 after 2 adjudications)

Verified: meta.profile dispatch SQLQuery vs SQLView (canonical
sql-on-fhir.org forms); BOTH declared -> ambiguous typed rejection; NO
profile -> typed rejection (profile REQUIRED for dispatch — strictness
verified correct); type.coding must carry sql-query/sql-view code from the
LibraryTypesCodes system (sql-on-fhir canonical); wrong code rejected;
content 1..* cardinality (empty array rejected); per-entry contentType
non-empty + data valid base64-UTF-8 (missing/empty/garbage rejected);
sql-must-be-sql-expressions: every contentType must start with
'application/sql' (text/plain + mixed second-entry rejected;
application/sql;dialect=duckdb OK); unknown meta.profile entries do not
affect dispatch; parse_sqlquery/parse_sqlview direct forms discriminate.

Adjudications: (1) LibraryTypesCodes system URL is
http://hl7.org/fhir/uv/sql-on-fhir/CodeSystem/LibraryTypesCodes (probe
initially used terminology.hl7.org); (2) NO-profile -> typed error is
intended strictness (q4).

Evidence: .temp/qa/speccomp2/sofsq01_skeptic_probe1.py
