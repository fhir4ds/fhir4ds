# QA Handoff - CQL-15 HISTORIAN

Scope: CQL Interval Operators Part 1, HISTORIAN personality. The audit used
current source, current tests, active state, global rules/knowledge, and
relevant AGENTS files only; archived `spec_comp/**` outputs were not inspected.

Coverage reconstructed:
- Open/closed endpoint semantics after SKEPTIC for `intervalStart`/`intervalEnd`.
- Partial DateTime marker intervals and millisecond/day precision behavior.
- Integer, Decimal, and Quantity interval direct helpers.
- Interval equality/equivalence, including open interval normalization.
- Collapse/expand adjacency and per-unit behavior.
- Null/empty boundaries and `Starts`/`Ends` same-boundary predicates.
- Precision-qualified before/after/contains/includes/ends behavior.
- Translated scalar execution.
- Native-loaded registration, forced Python fallback, and no-Python C++ direct
  helper checks where functions are registered.

Findings:
- `QA-CQL15-HIST-001` HIGH: translated interval `=` and `~` compared raw
  interval JSON/text shape, so `Interval(1, 6]` did not equal/equivalent
  `Interval[2, 6]` despite equal CQL effective boundaries.
- `QA-CQL15-HIST-002` HIGH: precision-aware interval helpers over partial
  Date/DateTime values returned definite booleans in native/no-Python paths
  where CQL uncertainty requires NULL.
- `QA-CQL15-HIST-003` MEDIUM: no-Python direct C++ `intervalEndsSame` returned
  false for a missing high boundary instead of NULL.

Evidence:
- Probe: `.temp/qa/cql15_historian_probe.py`
- Normative reference: CQL 1.5.3 Appendix B interval operators (`Start`, `End`,
  `Equal`, `Equivalent`, `Before`, `Includes`, `Ends`).

Disposition: issues handed to remediation and later verified.
