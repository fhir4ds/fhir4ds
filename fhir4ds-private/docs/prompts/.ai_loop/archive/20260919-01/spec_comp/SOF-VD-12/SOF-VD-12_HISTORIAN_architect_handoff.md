# Architect Handoff — SOF-VD-12 HISTORIAN launch (iteration 1)

## Golden Standard (profile-enforcement slice)
1. Profile canonical recognition must be data-driven alias sets in
   fhir4ds/viewdef/metadata.py — no ad hoc string matching at enforcement sites.
2. Enforcement rules must mirror the profile SD differentials exactly — no
   invented constraints, no missing constraints.
3. Profile constraints apply at ALL column depths (select.select, unionAll).
4. Metadata not governed by supported profiles must round-trip verbatim
   (extra_fields) — no silent drops.
5. Known-but-unsupported foreign profile canonicals: ignored for enforcement,
   retained for round-trip (matches official validator, which never inspects
   meta.profile).

## Audit result
COMPLIANT. SHAREABLE/TABULAR_*_CANONICALS frozensets live in metadata.py (curated
metadata, allowed); types.py enforcement enumerates exactly the upstream
differential constraints (verified byte-for-byte against both ig/2.0.0 and
HL7/sql-on-fhir HEAD profile SDs, fetched this launch); _iter_select_columns
covers nested select and unionAll; foreign canonicals retained; no silent
fallbacks or test-fixture hacks introduced by the SKEPTIC fix.

## QA Enforcer Gate
QA (HISTORIAN) was rigorous: enumerated every differential constraint from the
ACTUAL upstream profile SDs (both published 2.0.0 and HEAD), probed nested
enforcement both structure forms, versioned canonicals, foreign canonicals,
URI-form column types, status cardinality against the official JS validator
source, official example round-trip + DuckDB execution. No veto; RETRY_QA false.

## Verdict
Zero open issues. Clean exit at iteration 1 (min_iterations=1). Exit CLEAN.
