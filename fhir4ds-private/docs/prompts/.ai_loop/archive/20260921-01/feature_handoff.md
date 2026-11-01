# Feature Implementation Handoff — v0.0.16 CQL Type System (Option A)

Pipeline: feature_design (DONE) → **feature_implementation (DONE, this handoff)** → code_review → pre_release → docs_audit → scribe.
No commits made — Joel commits.

## What landed (U1-U7, all gates green after each unit)

### New architecture
- `fhir4ds/cql/types/typeref.py` — CQLTypeRef + _TypeParser + ANY_TYPE (moved verbatim from fhir_server/types.py; dead stub modules cql_types.py/fhir_types.py/type_checker.py DELETED; facade re-export preserved).
- `fhir4ds/cql/translator/type_map.py` (~1300 lines) — **TypeMapBuilder** (facade authority) + shared module functions: `infer_cql_type_compat` (VERBATIM legacy `_infer_cql_type` port; `_infer_cql_type` is now a thin wrapper — byte-exact proven by DQM-47 snapshot diff, 1049 defines zero drift), `static_source_cql_type`, `infer_fhir_property_type_str`, `static_numeric_literal_value`, `property_chain_parts`, `is_fhir_resource_type`, `infer_query_return_property_type_str`.
- `DefinitionMeta.cql_type_ref: Optional[CQLTypeRef]` — ONE additive field (context.py); NO cql_type back-fill. Builder attaches inside `translate_library()` (translator.py, end).
- Builder coverage: literals/selectors/lists/tuples/intervals/instances (U2); retrieves, scoped-symbol query walker (from/let/with/aggregate/return aliases), include-prefixed define refs, property typing w/ FHIR schema + tuple fields + Quantity subfields (U3); builtin function-return table, user-fn body recursion w/ cycle cutoff, Coalesce, parameters, numeric aggregates, power/abs (U4). Uncertainty family (AgeIn*/between) + uncast choice disjunctions → Any (never guess).
- Deleted duplicates: `_static_source_cql_type` (_temporal_components.py), `_logical_operand_property_cql_type` (_operators.py) — callers rewired to shared type_map functions. Frozen (per FDD §3.2, REV-002 sunset ledger in plan §7.1): `_static_structural_type_name`, `_infer_static_cql_type_for_logical_operand`, `_static_list_element_types`+closures.

### Facade flip (U6) + rollback flag (U7)
- `CQLResultMetadata.from_definition_meta` chain: cql_type_ref → cql_type → sql_result_type → Any (builder consumes sql_result_type as INPUT; facade never trusts it blind).
- `result_serializer.py` metadata-first: known metadata trusted; Any → silent runtime inference; would-crash (typed CQLFacadeErrors) → runtime rescue + WARNING log, FAILURE-driven not mismatch-driven, recursive per level. `_reconcile_type_ref` deleted from default path, restored verbatim under `metadata_first=False`.
- `CQLServerConfig.metadata_first_serialization: bool = True` feature flag threaded through handle_cql_operation → serialize_evaluation_result → serialize_value/_serialize_known (keyword-only, per-level recursion).

### U7 findings
- Perf: DQM-47 translation builder on/off = 47.31s vs 50.05s (−5.5%, noise; gate 6 <5% mean PASS).
- Gap census (1354 defines): 952 non-Any (70.3%); 305 no-AST (include defines — covered by cql_type fallback); **97 AST-level Any backlog: Property 48, Query 44, BinaryExpression 4, Identifier 1**. Rescue-WARNINGs = live-traffic gap signal (facade logger).

## Tests
- `fhir4ds/cql/tests/unit/test_type_map.py` — 46 tests incl. `test_type_map_differential_drift_tripwire` (57-entry corpus; builder vs compat identical where both non-Any; documented intentional divergences: uncertainty→Any, power int rules, Sum(List<Quantity>)→Quantity, dotted cast names→bare, identifier order, builder extras).
- `test_fhir_server_serializer.py` — 10 tests incl. `test_metadata_first_contract_u6` + `test_metadata_first_rollback_flag_restores_legacy_reconcile`. All 36 pre-existing facade tests pass UNCHANGED (reconcile pins re-adjudicated as failure-driven rescue).

## Gates (final tree)
- Byte-identical SQL: `PYTHONPATH=/mnt/d/fhir4ds python3 .temp/typemap/compare_baseline.py` → 47/48... 47/47 BYTE-IDENTICAL, exit 0 (harness: .temp/typemap/{capture,compare}_baseline.py; CTE-order-normalized digests).
- Legacy snapshot diff: EMPTY (.temp/typemap/legacy_infer_snapshot.json vs PRE_U5 backup).
- cql unit tree: 1708 passed. Conformance: `python3 conformance/scripts/run_all.py` → **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
- Runner gate 5 (cql-tests-runner): NOT RUN — external runner acquisition-dependent; checked-in report is a 'not-run' placeholder. FDD policy: hold-or-improve vs 1667/24/40; not chasing.

## Files touched (summary)
- NEW: fhir4ds/cql/types/typeref.py; fhir4ds/cql/translator/type_map.py; fhir4ds/cql/tests/unit/test_type_map.py.
- MODIFIED: fhir4ds/cql/types/__init__.py (exports); fhir4ds/cql/fhir_server/types.py (import + from_definition_meta chain + config flag); result_serializer.py (flip + flag); operations.py (flag thread); fhir4ds/cql/translator/context.py (additive field); translator.py (builder hook); inference.py (_infer_cql_type wrapper); expressions/_temporal_components.py + expressions/_operators.py (deletions + rewires); test_fhir_server_serializer.py (2 new tests); docs/architecture/plans/FEATURE_CQL_TYPE_SYSTEM.md (§7 implementation record + REV-002 sunset ledger).
- DELETED: fhir4ds/cql/types/{cql_types,fhir_types,type_checker}.py stubs.

## Notes for next roles
- code_review: full uncommitted diff vs 0.0.15 baseline; watch for sibling-session clobber of the campaign files; §7.1 ledger lists every disposition; .temp/typemap/ harnesses reproduce all gates (PYTHONPATH required).
- pre_release: version bump 0.0.15→0.0.16 across pyproject + root + 6 subpackage constants; facade API surface change (new config field) belongs in release notes.
- docs_audit: FDD §7 is the source of truth for as-built behavior.
