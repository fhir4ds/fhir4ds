# DESIGN HANDOFF — v0.0.16 CQL Type System

Pipeline: feature_design (COMPLETE) → feature_implementation → code_review
→ pre_release → docs_audit → scribe.

## Deliverables

- Final FDD: `docs/architecture/plans/FEATURE_CQL_TYPE_SYSTEM.md`
  (draft + self-audit + second-opinion amendments incorporated).
- Self-audit: `.ai_loop/ARCHITECT_REVIEW.md` (8 findings, all resolved in v2).
- Independent second opinion (premium reviewer, repo-grounded): APPROVED
  WITH AMENDMENTS — all P0/P1/P2 amendments incorporated.

## Plan summary

Post-translation TypeMapBuilder in new `fhir4ds/cql/translator/type_map.py`
walks definition ASTs (own topo order w/ cycle cutoff; declaration-order
definition_meta is an INPUT) producing Dict[name, CQLTypeRef]; attaches via
one additive `DefinitionMeta.cql_type_ref` field — NO `cql_type` back-fill,
guaranteeing byte-identical SQL. CQLTypeRef relocates to
`fhir4ds/cql/types/typeref.py` (dead stubs deleted; facade re-export kept).
Facade serializer flips to metadata-first: known types trusted outright;
runtime inference only on metadata-Any (silent, sanctioned) or
serialization-would-crash (rescue + WARNING log = gap signal); per-level
recursive semantics. Consolidation bounded: lowering-consumed classifiers
frozen (wrap-only) with three drift guardrails (shared tables in
type_map.py, `test_type_map_differential_drift_tripwire` CI test, REV-002
sunset ledger entry). Unknown/Any first-class: age-uncertainty family and
uncast choice disjunctions → Any by policy; sql_result_type demoted to
builder input. 7 implementation units, gates per unit: byte-identical SQL
(DQM 47 + facade synthetic path), conformance 2832/2832, full cql pytest
tree, facade metadata-first tests, runner hold-or-improve vs 1667/24/40,
<5% per-library translation overhead.

## Approval gate

Per the human's 2026-09-20 chat override of the USER_DIRECTIVES approval
gate: the WAIT_FOR_USER_APPROVAL stop is REPLACED by the completed second
opinion (above); auto-advancing to feature_implementation without stopping
for human feedback.
