# QA Handoff — CQL-08 HISTORIAN

## Verdict: CLEAN — normative walk from the same SKEPTIC evidence base + fixture checks

Coalesce variadic no-upper-bound (the <2-arg single-List overload is the
Appendix B form); null is null / X is not null operator rows; IsTrue/IsFalse
return false (never null) on non-Boolean operands; population surface collapses
null to False per pinned doctrine. All rows identical native vs fallback.

Evidence: .temp/qa/speccomp2/cql08_skeptic_probe1.py (shared battery)
