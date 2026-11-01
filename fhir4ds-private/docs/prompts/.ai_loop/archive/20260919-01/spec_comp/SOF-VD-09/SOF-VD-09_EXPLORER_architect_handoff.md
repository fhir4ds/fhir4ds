# Architect Handoff — SOF-VD-09 EXPLORER (2026-08-23, iteration 1)

Scope: `fhir4ds/viewdef` where-lowering (generator.py `_process_selects`,
`_build_single_query`, `_resolve_environment_path_context`, parser where
shape/where-path validation). No code changes this launch; audit is a
re-audit of the surface as left by SKEPTIC/HISTORIAN.

Golden standard (invariants re-checked against code):
1. All where predicates lower through the same fhirpath_json='[true]'
   boolean gate as columns — verified in generated SQL (E1, E8).
2. Multiple root wheres compose as one flat WHERE with AND — no nested
   subquery per where (E1 SQL shape inspected).
3. Mixed builtin-context expressions fail loud, never silently re-scope
   (E3/E3b/E3c exercise the HISTORIAN guard at depth and in unionAll).
4. Non-singleton-true filter results exclude rows per FHIRPath boolean
   semantics (E6, E9) — consistent on both engines.
5. Where descriptions are metadata only, never affecting lowering (E7).
6. resourceType guard on shared tables composes as the first AND
   condition with root wheres (E8).

Structural findings: none. Abstraction boundaries (parser shape → generator
lowering → UDF evaluation) hold; no silent fallbacks observed in where
handling; guards are symmetric across orderings.

QA Enforcer Gate: QA was NOT lazy — the launch mandate's full boundary list
was covered (50+ wheres, heavy FHIRPath trees, prefix-mixed-focus at depth
and in unionAll, absent/typed-null operands, repeat+where, multi-boolean
collections, SQL shape, 5KB description round-trip, 400-row mixed table,
constants, unknown builtins), all dual-engine. RETRY_QA: false.

State hygiene: `issues[]` empty (nothing to archive/tombstone); prior-launch
issues remain recorded in spec_comp/SOF-VD-09/* and ARCHIVE_LOG.md.

Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds): viewdef pytest 1227/1227;
ViewDefinition conformance 144/144 (where.json 8/8); master gate 2832/2832
(ViewDef 144 / FHIRPath 935 / CQL 1706 / DQM 47); fhirpath.duckdb_extension
md5 57d0634b6ee6eddee9fc06a1355bef5a identical repo↔site-packages.

Verdict: chunk SOF-VD-09 is structurally sound and fully closed after four
launches (SKEPTIC, HISTORIAN, EXPLORER, EXPLORER-boundary). Clean exit at
iteration 1 (min_iterations=1, zero open issues).
