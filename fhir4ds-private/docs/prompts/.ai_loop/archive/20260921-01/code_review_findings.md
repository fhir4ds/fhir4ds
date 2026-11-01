# Code Review Findings — v0.0.16 CQL Type System Campaign

Date: 2026-09-20
Reviewer role: code_review (ROLE_CODE_REVIEWER.md)
Scope: full uncommitted campaign diff (13 tracked modified files, +311/−648; 4 untracked new files; 3 deleted stub modules)

## Verdict: CLEAN_WITH_NOTES

No CRITICAL, HIGH, or MEDIUM findings. All seven units (U1–U7) implement the
FDD (docs/architecture/plans/FEATURE_CQL_TYPE_SYSTEM.md) as designed. The
reviewer amendments from the design-phase second opinion are all present and
verified in code.

## Findings ledger

None new this campaign. Existing REV items carried forward unchanged:
REV-002 (metadata duplication family — now MITIGATED by this campaign's
sunset ledger + tripwire; full resolution at the route-unification
milestone), REV-003/005/009/010/011/012/013/014/015/016/017/018/019 — all
pre-existing, untouched by this diff.

## What was verified (line-by-line)

1. **typeref.py (141 lines, new)** — verbatim relocation of CQLTypeRef +
   _TypeParser + ANY_TYPE from fhir_server/types.py. Frozen dataclass,
   no translator/fhir_server imports (dependency direction documented in
   module docstring). Identity re-export verified: FacadeRef IS CQLTypeRef.
2. **fhir_server/types.py (−171 net)** — CQLTypeRef/_TypeParser removed,
   imports from cql.types.typeref, __all__ added,
   CQLResultMetadata.from_definition_meta chain now
   cql_type_ref → cql_type → sql_result_type → Any with isinstance
   CQLTypeRef guard (duck-typed metas from older callers still work).
   sql_result_type only consulted when no builder ref (FDD: builder
   consumes it as INPUT; facade never trusts it blind).
   CQLServerConfig.metadata_first_serialization: bool = True rollback flag.
3. **result_serializer.py (+108)** — metadata-first flip as FDD §3.3:
   _reconcile_type_ref deleted from the default path (restored verbatim
   under metadata_first=False legacy path); null → null_parameter;
   Any → silent runtime inference; else _serialize_known inside
   try/except CQLFacadeError → failure-driven rescue (NOT mismatch-driven)
   with WARNING log naming both types; rescue recursive per-level
   (serialize_value is the recursion point); String runtime never rescues
   (VARCHAR transport doctrine + malformed-JSON serializer-gap pin
   preserved). Shape guards (Boolean rejects dict/list/tuple;
   Integer/Long reject bool; _strip_temporal_marker raises on non-str)
   make the rescue genuinely failure-driven. All 36 pre-existing facade
   tests pass UNCHANGED — the pinned reconcile tests now exercise rescue.
4. **type_map.py (1549 lines, new)** — TypeMapBuilder facade authority +
   infer_cql_type_compat VERBATIM legacy port. Dual-authority doctrine is
   load-bearing and documented: builder (facade) and compat (lowering)
   INTENTIONALLY diverge (uncertainty family→Any, power int rules,
   Sum(List<Quantity>)→Quantity, dotted cast names→bare, identifier order,
   unary is-true/is-false family, builder extras). Byte-exactness of the
   compat port proven by the 1049-define DQM snapshot diff (EMPTY).
5. **inference.py (−425)** — _infer_cql_type is now a one-line delegate
   to infer_cql_type_compat(self._context, ast_node); import inside method
   body avoids cycle. All other InferenceMixin methods intact.
6. **Deletions** — _static_source_cql_type (_temporal_components.py) and
   _logical_operand_property_cql_type (_operators.py) deleted; callers
   rewired to shared module fns (static_source_cql_type,
   infer_fhir_property_type_str) preserving semantics incl. the
   Quantity-subfield dict WITH comparator; isinstance guards preserved at
   call sites.
7. **context.py** — additive cql_type_ref: Optional[Any] = None field with
   doctrine comment; NO cql_type back-fill anywhere (byte-identical SQL
   guarantee; ~40 lowering sites read cql_type).
8. **translator.py hook** — TypeMapBuilder(self._context).attach() at end
   of translate_library(); docstring documents declaration-order
   population and the builder's own memoized walk with cycle cutoff.
9. **Security** — no SQL construction in new code (pure AST typing +
   serialization); no secrets; no injection vectors; no model-knowledge
   hardcoding beyond data-driven schema lookups (FHIR_TYPE_TO_CQL_TYPE
   imported from inference — existing data table); no error swallowing
   (_context_get_function Exception→None is a lookup-miss path consistent
   with the builder-never-raises doctrine).

## Notes (non-blocking)

- N+1 type-knowledge drift risk is now actively guarded: shared tables in
  type_map.py, CI tripwire test_type_map_differential_drift_tripwire
  (57-entry shared corpus, asserts identical where both non-Any),
  REV-002 sunset ledger in FDD §7.1.
- 97-define AST-level Any backlog (Property 48, Query 44, Binary 4,
  Identifier 1) is the documented gap frontier, not a defect.
- Cosmetic: type_map.py lacks a trailing newline after final `return "Any"`.
- docs/architecture/plans/FEATURE_AGENTIC_VERIFY_MCP.md is an unrelated
  pre-existing untracked file — NOT campaign; do not stage it.

## Gate evidence (final tree)

- type_map + serializer focused: 56 passed
- cql unit tree: 1708 passed
- DQM-47 SQL baseline compare: BYTE-IDENTICAL 47/47 (exit 0)
- Conformance run_all.py: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47)
- Legacy snapshot diff (1049 defines, 47 measures): EMPTY

## Harness reproduction (.temp/typemap/)

- capture_baseline.py / compare_baseline.py — byte-identical gate
  (CTE-order-normalized digests; raw sha256 drifts across processes)
- snapshot_legacy_infer.py — legacy _infer_cql_type ground truth
- u7_perf_gap.py — per-library translation overhead + Any census
  (47.31s vs 50.05s, −5.5% = noise; no scaling cliff)
