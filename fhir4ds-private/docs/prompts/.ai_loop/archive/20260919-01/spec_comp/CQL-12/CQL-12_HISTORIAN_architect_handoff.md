# Architect Handoff — CQL-12 (HISTORIAN re-launch), iteration 1

Golden standard (scoped): .temp/architect/golden_standard_cql12_historian_relaunch.md
(7 invariants extending the prior SKEPTIC golden standard; key new invariant: DuckDB
macros with lambda-bearing branches cannot enforce their own type guards — binder
resolves list_filter against the actual column type before any CASE branch executes,
so wrong-shape operands must be rejected at translation time with typed errors).

Audit verdict: the QA-001 fix is architecturally sound.
- The typed TranslationError in the Combine lowering (expressions/_functions.py)
  sits at the correct layer (translation validates shape before SQL emission),
  mirrors the established QA-004 `[Resource].field` guard doctrine, and adds no
  hardcoding, no SQLRaw, no silent fallback.
- Supported Combine sources (literal lists, typed-null lists, folded query
  subqueries per the EXPLORER doctrine, list_apply row shapes) are unaffected —
  confirmed by the 9/9 string parity suite including the new regression test.
- Baseline protection verified with a fresh full run: ViewDefinition 144/144,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47, OVERALL 2832/2832.

Findings: 1 MEDIUM resolved (QA-001 opaque Combine failure), 1 LOW intended
(QA-002 Split null separator, registry). No new drift. ARCH-001 (modelinfo
chained-property typing → real List<String> navigation) remains the recommended
future chunk; when it lands, the new typed guard should be tightened to allow
list-typed chained navigation sources.

QA Enforcer Gate: QA was thorough for a second-personality pass — verified the live
normative text for every chunk operator, then hunted genuinely new divergence axes
(Unicode/multibyte, regex dialect edges, dynamic/composed sources, typed-null
boundaries, prior-fix regression re-verification through evaluate_measure on both
engines). RETRY_QA = false.

State hygiene: issue details archived to ARCHIVE_LOG.md; evolution.json tombstoned
(QA-001 RESOLVED, QA-002 INTENDED); workflow=null, exit_reason=CLEAN (iteration 1
>= min_iterations 1, zero non-terminal CRITICAL/HIGH/MEDIUM issues). Control
returned to the outer spec-compliance orchestrator.
