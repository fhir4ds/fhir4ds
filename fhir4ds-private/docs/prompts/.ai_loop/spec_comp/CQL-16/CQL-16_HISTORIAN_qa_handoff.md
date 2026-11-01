# QA Handoff — CQL-16 HISTORIAN

## Verdict: CLEAN — normative-walk rows from the SKEPTIC evidence base

Covered: meets precision forms + both directions; on-or-after/before inclusive
boundaries + null-bound sentinels (closed null -> point min/max, open null ->
unknown); overlaps family incl. NULL-propagation; included-in precise; intersect
always-closed effective bounds; not-equal/not-equivalent effective-bounds equality.

(Evidence base: cql16_skeptic_probe1.py fresh dual-path run — see SKEPTIC handoff.)
