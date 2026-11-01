# QA Handoff — SOF-SQ-01 HISTORIAN/EXPLORER (combined battery)

## Verdict: CLEAN — 8/8 checks (flagged=0 after 1 harness fix)

H1 hl7.org canonical form ALSO dispatches (dual-form doctrine);
H2 profile|version suffix dispatches; H3 SQLView+sql-query code mismatch
rejected; H4 to_dict round-trip (name/version/relatedArtifact/resourceType).
E1 whitespace-only data rejected; E2 true non-UTF8 decoded bytes rejected
('utf-8' codec error surfaced as typed SQLQueryParseError); E3 non-SQL
body parses (execution-time validation only); E4 extra fields (publisher/
description) retained.

Harness fix: E2 initially b64'd a literal backslash string (double-escape)
— replaced with real invalid bytes.

Evidence: .temp/qa/speccomp2/sofsq01_historian_explorer_probe1.py
