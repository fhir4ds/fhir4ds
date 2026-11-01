# Architect Handoff — CQL-08 EXPLORER launch (iteration 1)

## Audit scope
Net working-tree delta for this launch: one regression test + doctrine/knowledge updates; no translator source change survived (spec-prose fix reverted at the Recovery Gate by fixture authority).

## Structural findings
1. **No drift introduced.** The surviving change (`test_cql_is_null_over_query_valued_lists_fixture_semantics_cql08_explorer` in `fhir4ds/cql/duckdb/tests/integration/test_nullological_parity.py`) sits at the correct layer (integration parity, public `translate_cql` + both connection factories) and documents the fixture-governed semantics inline.
2. **Documented inconsistency, fixture-governed (accepted):** query-valued `is (not) null` is existential (row presence) while literal-list null tests are strict-spec. This duality is now pinned in AGENTS.md doctrine and by test; changing it requires overriding official eCQM fixtures — not actionable.
3. **QA-003 (deferred, architecture-relevant):** query-alias/define-name shadowing mis-resolution (`define D` + `from {} D return D` → `FROM "D"`, Catalog Error) indicates identifier-resolution precedence leaks across the query translator's scope boundaries. Recommend the query chunk (CQL-04/05 follow-up) add alias-scoping rules before define resolution.
4. **Process validation:** the Recovery Gate worked exactly as designed — the engineer isolated causation (surgical revert → DQM 47/47), reclassified by fixture authority, and re-ran the full gate (2832/2832).

## QA Enforcer Gate
QA was thorough: dual-path (py + native cpp) on every case, spec verified live against cql.hl7.org Appendix B, boundary/combination coverage per the chunk mandate (temporal/quantity/Concept/Ratio operands, division guards, empty-vs-null lists, postfix chains, case stacks, retrieve-integrated .value/alias/projection surfaces, e2e population SQL). No veto. RETRY_QA remains false.

## State hygiene
All three issues terminal: QA-001 INTENDED (fixture authority), QA-002 INTENDED, QA-003 DEFERRED (out-of-chunk). Zero non-terminal CRITICAL/HIGH/MEDIUM issues; iteration 1 ≥ min_iterations 1 → CLEAN exit. Evidence preserved in `.temp/qa/cql08_explorer3_2026_08_21/`, spec_comp archives, and GLOBAL_KNOWLEDGE.md.

## Recommended fix order (for future chunks)
1. Query alias vs define shadowing (QA-003) — query-translation chunk.
2. None other from this launch.
