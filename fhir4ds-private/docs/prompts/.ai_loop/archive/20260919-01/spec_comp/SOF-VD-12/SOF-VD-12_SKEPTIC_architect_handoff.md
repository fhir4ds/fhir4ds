# Architect Handoff — SOF-VD-12 (iteration 1)

Scope: diff of this launch = fhir4ds/viewdef/metadata.py (canonical alias
sets), fhir4ds/viewdef/types.py (validate_supported_view_profiles membership
test), fhir4ds/viewdef/tests/unit/test_parser.py (regression test).

Golden-standard invariants checked:
1. Profile/spec knowledge must be data-driven in the metadata registry, not
   branch logic — PASS (frozensets of canonical aliases; adding a profile
   canonical = editing the registry).
2. No silent fallbacks — PASS (unrecognized profile canonicals are simply not
   enforced, which is documented runner-level stance: profile conformance is
   validator-level; the engine enforces the profiles it knows).
3. Back-compat: legacy sql-on-fhir.org/ig spellings still recognized — PASS
   (all 1232 viewdef tests pass unchanged).
4. Single recognition point: validate_supported_view_profiles is invoked at
   both parse and to_dict; membership test sits in one place — PASS.
5. No test-driven hacks — the regression test exercises both violating and
   conforming shapes under official canonicals — PASS.

Findings: none. RETRY_QA not set. Chunk SOF-VD-12 is CLEAN at iteration 1
(>= min_iterations=1, zero non-terminal CRITICAL/HIGH/MEDIUM).
