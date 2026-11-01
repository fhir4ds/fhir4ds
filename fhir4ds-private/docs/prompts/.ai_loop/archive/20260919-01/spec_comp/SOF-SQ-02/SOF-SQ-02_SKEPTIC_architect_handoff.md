# Architect Handoff — SOF-SQ-02 (iteration 1)

Golden standard (8 invariants) written to `/mnt/d/fhir4ds/.temp/architect/golden_standard.md`; audit scoped to `fhir4ds/sqlquery` (runner/validator/types) against the upstream spec artifacts and review-55 doctrine.

## Audit verdict
Post-fix, all 8 invariants hold:
- Coercion is registry-driven and the derived DuckDB type is now actually applied (temporal CAST through prepared statements; the only f-string SQL embeds registry-whitelisted type names — no caller value is ever interpolated). Parameter-path injection audit: clean (dict named-params to `con.execute`; malicious labels die at sql-name validation; DDL labels quoted).
- Cycle detection verified complete (self, mutual SQLView, 3-cycle, root-inclusive) with no diamond false-positives.
- Runner stays within viewdef's public boundary (SQLGenerator, parse_view_definition, registry, quote_identifier); no hidden state; idempotent materialization.
- All type-domain failures surface typed `SQLQueryTypeError` with parameter name and declared-vs-got detail.

Observations (documented, no open issue): (a) SQLView-vs-ViewDefinition dict detection in `_materialize_one` is structural (`select`+`resource` heuristic) — acceptable because `parse_view_definition` enforces select 1..1; (b) charset-suffixed content types still deferred per SOF-SQ-01 AGENTS.md registry.

## Issue counts
5 found / 5 RESOLVED (1 HIGH, 4 MEDIUM). Categories: 5 SPEC_VIOLATION (type-coercion fidelity). 0 architectural drift entries.

## QA Enforcer Gate
QA (SKEPTIC) covered every mandate item including the special-attention surfaces (binding security, cycle completeness incl. root-cycle, registry edge values, bool-as-int, wrong-type error quality). No veto; RETRY_QA not set.

## Recommended Fix Order
None — zero open issues. Clean exit at min_iterations=1 (0 non-terminal CRITICAL/HIGH/MEDIUM).

## Validation
sqlquery suite 89/89; master gate (fresh) 2832/2832; extension binaries md5-matched repo vs site-packages (cql c5b22d58310c1eb7bafa17ce7877f989, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a).
