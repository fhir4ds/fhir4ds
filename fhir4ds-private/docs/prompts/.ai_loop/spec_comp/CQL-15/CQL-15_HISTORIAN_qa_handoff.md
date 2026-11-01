# QA Handoff — CQL-15 HISTORIAN

## Verdict: CLEAN — normative-walk rows covered by the SKEPTIC battery + adjudications

The SKEPTIC battery (same evidence base) walked the normative semantics: after/before
strict whole-interval comparisons, closed/open bounds via Contains/In/End-of/Equal/
Equivalent, Ends left-operand rule, Collapse meets/overlap merging, Expand per-grid
with half-open-high exclusion, Includes precision routing, Except null-rule.
All rows native==fallback with spec-correct values after the 9 expectation-form
adjudications documented in the SKEPTIC handoff.

Evidence: .temp/qa/speccomp2/cql15_skeptic_probe1.py + /tmp/opencode/cql15_adj.py
