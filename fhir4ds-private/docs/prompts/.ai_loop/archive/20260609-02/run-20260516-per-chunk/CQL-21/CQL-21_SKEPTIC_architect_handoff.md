# Architect Handoff - CQL-21 SKEPTIC

## Structural Health

The CQL-21 SKEPTIC remediation is structurally sound. The fixes align with the
clinical-operator golden standard: clinical Code/Concept/terminology semantics
are handled before generic SQL fallback, ValueSet/CodeSystem boundaries remain
on public DuckDB helper surfaces, age precision coverage is explicit, and
`ExpandValueSet` is classified as a list-producing helper. I found no new
architectural findings and no reason to veto QA.

## Issue Summary

- SPEC_VIOLATION: 4 resolved and architect verified (`QA-001` through
  `QA-004`).
- New architect findings: 0.
- Retry QA: false.

## Handoff Compression

QA used fresh source/spec-driven probes against CQL v1.5.3 Appendix B clinical
operators and found four real gaps: incomplete age precision registration and
DateTime handling, invalid static `in CodeSystem` SQL, incorrect static
Code/Concept `in ValueSet` plus missing `ExpandValueSet`, and Code equality
component-mismatch semantics. Engineering remediated these by completing the
age function family, preserving DateTime precision for hour/minute/second
fallback age helpers, adding static clinical CodeSystem/ValueSet membership
lowering, registering `ExpandValueSet`, classifying it as list-returning, and
adding static Code/Concept equality semantics. Focused parity and full-suite
validation passed.

## Recommended Fix Order

No engineer follow-up is required for this inner run. Keep the CQL-21 clinical
operator invariants in `GLOBAL_KNOWLEDGE.md` and preserve the added parity tests
when future terminology or age helper work changes translator lowering.
