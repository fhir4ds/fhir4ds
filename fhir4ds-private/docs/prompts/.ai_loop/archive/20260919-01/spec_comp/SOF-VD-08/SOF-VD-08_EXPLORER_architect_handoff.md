# Architect Handoff — SOF-VD-08 EXPLORER (iteration 1, 2026-08-23)

## Compression of the iteration

EXPLORER QA probed every SOF-VD-08 mandate item at boundary scale (24-branch unions with duplicate preservation, 3-level unionAll nesting, branch-level forEachOrNull wrappers at maximum depth, mixed populated/empty branches, where at all scopes, %constants in branches, collection=true type mismatch, unionAll×nested-select cross joins, %rowIndex in nested union arms under forEach stacks, contained resourceType mixing) on both the native extension and the forced-Python fallback — all identical and conformant except one finding. Ground truth was re-verified against the published ig/2.0.0 IG zip (StructureDefinition snapshot + Process(S,N) notes + sof-js reference impl). Remediation fixed the single HIGH: backtick-quoted FHIRPath constant references (%`name`) silently resolved to empty because `iter_constant_references` fell through to the backtick skip-region; the fix yields and substitutes them, normalizes builtin runtime variables to plain %name, and raises ConstantResolutionError for undefined names, with a 7-test regression class. No architectural drift: the fix is lexical, engine-upstream, and layer-appropriate (see .temp/architect/golden_standard_sof_vd08_explorer.md).

## Structural health

- Issues this iteration: 1 SPEC_VIOLATION (HIGH) — RESOLVED. 0 CRITICAL, 0 MEDIUM open.
- QA Enforcer: QA effort sufficient (all mandate items, dual-engine parity, spec citations, reproducer). No veto, RETRY_QA false.
- Recommended fix order: none pending.

## State hygiene

QA-001 tombstoned in evolution.json; full evidence archived to ARCHIVE_LOG.md. AGENTS.md updated (launch note + NOT A BUG registry entries). GLOBAL_KNOWLEDGE.md updated (stats row, personality log, recurring theme: fixture-invisible bug classes, 3rd occurrence).
