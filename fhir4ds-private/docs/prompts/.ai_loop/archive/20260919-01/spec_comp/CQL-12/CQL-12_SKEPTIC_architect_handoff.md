# Architect Handoff — CQL-12 (SKEPTIC), iteration 1

Golden standard (scoped): .temp/architect/golden_standard.md — 8 invariants covering
translator layering, §17-macro lowering, shape-driven indexer dispatch, dual-engine
parity, no silent fallbacks, metadata-driven typing, and baseline protection.

Audit verdict: the QA-001 fix is architecturally sound.
- `_definition_resource_cte_name` now keys on RowShape.RESOURCE_ROWS (invariant 3:
  shape-driven dispatch, not presence-of-retrieve).
- Scalar defines route through the public `Indexer` macro (invariant 2); genuine row-list
  defines keep list_extract; both engines covered by the new parity+e2e regression
  (invariant 5); baseline 2832/2832 held (invariant 8).
- No new hardcoding, no SQLRaw, no silent fallbacks introduced.

Findings: 1 HIGH resolved (QA-001), 1 LOW intended (QA-002), 1 LOW tech-debt opened
(ARCH-001: property-chain type inference gap — modelinfo does not resolve complex-type
subfields such as HumanName.family, leaving scalar defines typed Any and forcing
defensive dispatch downstream). Recommended fix order for a future chunk: land
modelinfo-backed chained-property inference, then tighten `_is_string_index_source`
to String-only scalar dispatch.

QA Enforcer Gate: QA was thorough for this chunk (spec-example matrix incl. every
normative example, boundary/null/case/regex-dialect probes, nested composition,
retrieved-data e2e, where-clause usage, native-vs-Python parity). RETRY_QA = false.

State hygiene: resolved/intended details archived to ARCHIVE_LOG.md; evolution.json
tombstoned. No drift requiring immediate action.
