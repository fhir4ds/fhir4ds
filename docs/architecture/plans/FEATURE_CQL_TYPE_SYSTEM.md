# FEATURE PLAN DRAFT — v0.0.16 CQL Type System (Option A)

Status: v2 FINAL (Feature Designer; self-audit resolutions + independent second-opinion amendments incorporated)
Mandate: `.ai_loop/USER_DIRECTIVES.md` (v0.0.16 CQL TYPE SYSTEM, Option A only; Option C deferred)

## 1. Objective

Deliver a complete, authoritative CQL type-inference layer for the fhir4ds-v2
CQL translator so every library define/expression carries its exact CQL type
(List<T> element types, Interval point types, Date/DateTime/Time,
Integer/Long/Decimal, Code/Concept/Quantity/Ratio, Tuple fields) through to
the result boundary. The `$cql` facade serializer flips to metadata-first;
the shape-guessing heuristics (`_reconcile_type_ref` / `_infer_runtime_type`)
demote to a logged fallback layer.

**Binding constraint 1 (metadata-only):** the unified type pass runs
ALONGSIDE translation. Lowering routes MUST NOT change. Acceptance proof:
generated SQL byte-identical pre/post for the DQM 47-measure corpus.

## 2. Spec Alignment

- CQL 1.5 §2 (type system: Simple, Structured, Interval, List, Tuple,
  Choice), §3 (literal/selector grammar: typed nulls, lists, tuples,
  intervals, instances), §9/§16-§22 (operator signatures → return types),
  Appendix B Table 9-E conversions.
- FHIR R4 modelinfo mapping (FHIR_TYPE_TO_CQL_TYPE) for retrieve element
  types and choice disjunctions.
- Project doctrine: AGENTS.md "Result serialization ... must be
  CQL-metadata-driven"; REV-002 (no parallel hand-maintained type tables);
  REV-010 (do NOT perturb the dynamic-list shape-selection detection layer).

## 3. Architecture

### 3.1 New module: `fhir4ds/cql/translator/type_map.py`

One authoritative type-assignment module. Data flow:

```
AST (per definition, topological order)
   │  TypeMapBuilder (new, in type_map.py)
   ▼
DefinitionTypeMap: Dict[define_name, CQLTypeRef]  (+ expression-level cache)
   │                                   ┌──────────────────────────┐
   │  attach (additive field)          │ Existing consumers keep  │
   ▼                                   │ working unchanged:       │
DefinitionMeta.cql_type_ref: Optional[CQLTypeRef] = None           │
   │                                   │ definition_meta readers, │
   ▼                                   │ RowShape/stores_list     │
CQLResultMetadata (facade)             │ lowering route dispatch  │
   └── serializer metadata-first       └──────────────────────────┘
```

Key decisions:

- **CQLTypeRef is the canonical representation** (reuse
  `fhir4ds/cql/fhir_server/types.py:CQLTypeRef`; move it to the neutral
  `fhir4ds/cql/types/` package in a dedicated first commit so translator ←
  facade is a clean dependency direction; facade re-imports from the new
  home for backwards compat).
- **TypeMapBuilder runs AFTER translation completes (post-translation
  attach), inside `translate_library()` before `get_definition_meta`
  deep-copies.** It performs its OWN dependency-ordered walk: the
  translator populates `definition_meta` in DECLARATION order (forward
  references resolve via pre-registered definition ASTs, not topo order —
  the existing `_topological_sort_ast_definitions` Kahn helper in
  inference.py is currently dead code and is resurrected for the builder).
  The builder therefore computes its own topological order over the
  definition ASTs with an in-progress cycle cutoff → Any, and may rely on
  the FINISHED definition_meta (post-translation facts like
  stores_list_value / sql_result_type / alias propagation are inputs, not
  competitors). It is a read-only pass over the AST + parse context
  (parameters, codes, valuesets, function declarations, and the finished
  `definition_meta`) — it never inspects generated SQL text, never
  influences lowering, and its ONLY DefinitionMeta mutation is setting the
  NEW `cql_type_ref` field (audit S1: NO back-fill of `cql_type` in
  v0.0.16 — the facade reads `cql_type_ref` first; this removes any
  possibility of changing lowering dispatch that reads `cql_type`).
- **DefinitionMeta gains one additive field**: `cql_type_ref: Optional
  [CQLTypeRef] = None`. `cql_type` (str) stays untouched for ALL existing
  consumers (audit S1: no back-fill — any Any→known mutation could reroute
  lowering dispatch such as `_is_string_index_source` /
  `_validate_boolean_operand` and break byte-identical SQL).
- **Unknown is first-class**: the builder returns `Any` (ANY_TYPE) for
  genuinely dynamic values; it never guesses. **Age/duration-uncertainty
  surfaces** (§22.21: VARCHAR that is an integer OR closed-interval JSON
  at runtime) are typed `Any` by policy — runtime inference handles them
  well and typing them Integer would manufacture rescue-WARNING noise.
  **Choice-element disjunctions without an `as` cast → Any** (never
  "first-known" — a guessed arm lies in `cqf-cqlType` extensions and
  still trips the rescue on the wrong arm).
- **sql_result_type is a builder INPUT, not a facade tier**: the builder
  consumes `sql_result_type` as one type source; the facade's
  `from_definition_meta` chain stays `cql_type_ref` → `cql_type` →
  `sql_result_type` → Any, and a builder-Any is trusted as Any at the
  facade (runtime inference) even when sql_result_type exists — never a
  blind physical-hint override of a known-map miss.
- **Performance**: the builder caches inference results per definition
  (and per AST-node id for deep alias chains) to keep the added pass
  linear; gate 6 (<5% translation-time regression) guards it (audit S4).

### 3.2 Consolidation strategy for existing helpers (constraint 2)

The scattered classifiers become **thin wrappers or are deleted**, in three
tiers (per unit of work, not big-bang):

| Existing helper | Disposition |
|---|---|
| `InferenceMixin._infer_cql_type` (inference.py:1086) | Becomes a thin wrapper delegating to `TypeMapBuilder.infer_expr_type` (keeps signature + call sites); its per-node logic MOVES into the builder. |
| `_infer_row_shape`, `_detect_quantity_fields`, FHIR_TYPE_TO_CQL_TYPE | Stay in inference.py (shape/cardinality is NOT CQL type; out of scope) but import shared type data from type_map.py where overlapping. |
| `_function_return_type` closure (_functions.py:400) | Wrap: implementation delegates to the builder's function-return table IF outputs provably identical on the pinned corpus; else stays and is marked as lowering-frozen (audit S2). |
| `_infer_static_cql_type_for_logical_operand` (_operators.py:1230) | Keep method and its tables FROZEN in v0.0.16 (audit S2: consumed by lowering validation); builder is the authority for the FACADE map only. Wrap-not-rewrite. |
| `_static_source_cql_type` (_temporal_components.py:798) | DELETE; call sites use builder. |
| `_infer_static_numeric_type` (_operators.py:121) | Keep (small, focused); builder reuses it for numeric promotion. |
| `_static_structural_type_name` (_query.py:919) | FROZEN in v0.0.16 (audit S2: 36 lowering-layer call sites; delegation could change routing). Builder may reuse its logic read-only; deletion deferred to the route-unification milestone. |
| `_element_type` closure family (_functions.py:452) | Same wrap-if-identical policy as `_function_return_type` (audit S2). |
| `_static_list_element_types` (_functions.py:375) | FROZEN in v0.0.16 — it feeds aggregate-lowering routes (CQL-20 exact-typed dispatch); only its inner closures may share the builder's tables (review Q2-4). |
| `_logical_operand_property_cql_type` (_operators.py:1206) | DELETE — duplicate of `_infer_fhir_property_type`; call sites call the builder. |
| `_infer_row_shape_for_expr` (_lists.py:264) | Keep (shape, not type). |
| SQL `result_type` channel | Untouched (parallel channel, merges at DefinitionMeta as today). |

Rule: one function-return-type table, one literal/selector typing function,
one property-typer — all in type_map.py — as the AUTHORITY FOR THE FACADE
TYPE MAP. Lowering-side classifiers that must stay frozen for
byte-identical SQL (per audit S2) are wrapped, not rewritten; their full
deletion is explicitly deferred to the route-unification milestone and
recorded on the REV-002 ledger. Consolidation depth in v0.0.16 is bounded
by INV-T1.

**Short-term N+1 drift mitigation (review Q2)** — v0.0.16 knowingly ships
the builder PLUS frozen helpers, so three guardrails are mandatory:
1. *Share data, not logic*: where frozen helpers and the builder overlap
   (literal typing, To*/constructor return maps), the TABLES live once in
   type_map.py and are imported by the frozen helpers (dispatch code
   untouched); corpus-diff proof at U5.
2. *Differential drift tripwire* (CI test): run the builder and each
   frozen classifier over a shared corpus (DQM 47 libraries' definition
   ASTs + a generated expression matrix) and assert identical outputs
   wherever both are non-Any — named test
   `test_type_map_differential_drift_tripwire`.
3. *Sunset ledger entry*: REV-002 records the frozen set, the tripwire
   test name, and the route-unification milestone that deletes them.

### 3.3 Facade flip: metadata-first serializer

`result_serializer.py`:

1. `_reconcile_type_ref` and `_infer_runtime_type` move AFTER metadata
   dispatch and become the **fallback + assertion layer** (audit S6):
   - (a) metadata `Any` → runtime inference as today, NO log (sanctioned
     Any policy);
   - (b) serialization-would-crash with known metadata ("crash" = any
     exception path including the typed `CQLFacadeError`s from
     `_as_python_list` / `_as_json_object` / `_serialize_scalar`, e.g.
     Quantity JSON value with Integer metadata, scalar with List
     metadata) → runtime fallback RESCUES (preserving the existing rescue
     semantics so the reconcile doctrine tests still pass) and **logs a
     WARNING** naming the definition + both types — every such override
     is a type-map gap to close. The rescue is FAILURE-DRIVEN, not
     mismatch-driven: runtime/metadata disagreement without a crash
     never triggers it;
   - (b′) the metadata-first check + rescue apply RECURSIVELY at every
     `serialize_value` level (list elements, tuple fields, interval
     bounds), mirroring today's per-level reconcile;
   - (c) known metadata + serializable value → metadata wins outright,
     no runtime consult.
2. Metadata-known types serialize directly (current `_serialize_scalar`
   dispatch unchanged — it is already metadata-driven once the reconcile
   gate is demoted).
3. `CQLResultMetadata.from_definition_meta` reads `cql_type_ref` (new
    preferred) with `cql_type`/`sql_result_type` fallback chain unchanged.
4. Typed `CQLFacadeError(SERIALIZER_GAP)` only when metadata is `Any` AND
   runtime inference also fails — unchanged contract.

**Migration guard**: the two existing tests that pin value-first doctrine
(`test_runtime_structure_overrides_weak_or_wrong_metadata`,
`test_handle_cql_operation_reconciles_quantity_aggregate_metadata`) get
re-adjudicated: the reconcile still fires for wrong-metadata cases (gap
logging), so the assertions should hold — the serializer keeps rescuing
wrong metadata; what changes is KNOWN metadata is trusted first. Any test
that pinned runtime-overrides-CORRECT-metadata must be updated and each
such case becomes a type-map gap regression test.

### 3.4 Type sources the builder must enumerate (constraint 5)

| # | Source | Type rule |
|---|---|---|
| 1 | Literal selectors | Typed nulls `null as T` → T; Boolean/Integer/Long/Decimal/String; Date/DateTime/Time split; Quantity `5 'mg'`; Ratio `1:8`. |
| 2 | List selectors | `{}` → List<T> from `as` cast context or List<Any>; homogeneous literal lists → List<common>; heterogeneous → type error marker (translator already raises at lowering; builder records Any). |
| 3 | Tuple selectors | `Tuple { a: 1 'mg' }` → Tuple{a: Quantity} recursive. |
| 4 | Interval selectors | `Interval[low, high]` → Interval<common point type>; `null as Interval<T>` → T. |
| 5 | Instance selectors | Code/Concept/ValueSet/CodeSystem + structured instances per §3 grammar. |
| 6 | Retrieves | `[Observation]` → List<Observation>; `[Observation: profile]` → List<profile-type or Observation>; choice elements → Any UNLESS narrowed by an `as` cast (never first-known guessing — review Q4-4). FHIR_TYPE_TO_CQL_TYPE for element typing. |
| 7 | Function return types | Builtin table (one authoritative table: count→Integer, sum/product/min/max numeric promotion, avg→Decimal, To* conversions, temporal constructors, uncertain-aggregates→Any per the age-uncertainty policy); user-defined functions (fluent/inline/include libraries) ALWAYS recurse into the function body (CQL `define function` has NO declared return type) with cycle cutoff; `Message(source,...)` → source type T; `Children()`/`Descendants()` → List<Any>. |
| 8 | if/case | Common type of branches (spec's implicit-conversion common-type rule); no common type → Any. |
| 9 | Query sources | Scoped-symbol walker over Query ASTs (the real work of U3): from-alias source types, let bindings, with-clause aliases (iter-11 scope), aggregate-accumulator aliases (QA-013), return-clause typing (property chains off aliases incl. depth-2 alias propagation per CQL-19); singleton from → element type. Precedent: `_infer_resource_type_from_cql_expr` (_lists.py:1893) which already re-derives alias scopes post-hoc for RESOURCE types — the builder generalizes it to full CQL types. |
| 10 | Parameters | Declared parameter type wins unless it is Any (audit S7: no speculative refinement beyond declared type in v0.0.16). |
| 11 | Coalesce | First non-null-argument type per spec. |
| 12 | Definition references | Topological-order lookup with cycle cutoff → Any; include-library defines via prefixed name lookup (existing include_handler contract). |
| 13 | as/convert | `as T` → T (nullable assertion); `convert X to T` → T. |
| 14 | Operators (binary/unary) | Comparison/logical/membership → Boolean; arithmetic promotion ladder (Integer<Long<Decimal, Quantity-aware, temporal ± Quantity); set ops preserve operand type; duration/difference between and the AGE FAMILY → Any (uncertain-interval policy, review Q4-1). |

Forward/recursive cutoff policy: depth cap + in-progress set; unresolved → Any (same policy as `_definition_cql_asts` recursion today).

### 3.5 Failure taxonomy

- Builder NEVER raises — it returns Any on uncertainty (constraint 6). Its
  only outputs are CQLTypeRef or ANY_TYPE.
- Serializer gap → existing typed CQLFacadeError(SERIALIZER_GAP).
- Metadata/runtime conflict at the facade → fallback + `logging.warning`
  (module logger `fhir4ds.cql.fhir_server.result_serializer`).

## 4. Implementation Plan

Ordered units; each passes gates 1-3 (byte-identical SQL, 2832/2832, full
cql pytest tree green) before the next begins:

1. **U1 — CQLTypeRef relocation + DefinitionMeta field.** Move CQLTypeRef +
   its parser to `fhir4ds/cql/types/typeref.py` (the existing `cql/types/`
   package is a stub graveyard — its three dead stub modules are DELETED
   in this unit); facade re-imports from the new home (public
   `fhir4ds.cql.fhir_server.types.CQLTypeRef` re-export preserved). Import
   hygiene rule: translator imports `cql.types.typeref` only, never
   `cql.fhir_server.*`. Additive `DefinitionMeta.cql_type_ref = None`
   field. Pure mechanical; byte-identical SQL trivially holds.
2. **U2 — TypeMapBuilder core (sources 1-5, 13, 14).** Literals, selectors,
   as/convert, operators. Unit tests: per-source matrix pinning exact
   CQLTypeRef.canonical() values.
3. **U3 — Retrieves, queries, defines (6, 9, 12).** Topological walk,
   definition references, include-library defines, query return typing,
   alias propagation.
4. **U4 — Functions and parameters (7, 10, 11).** Builtin return table,
   user-function body recursion, Coalesce, parameter defaults.
5. **U5 — Consolidation.** Wrap/delete the scattered helpers per §3.2
   table. Deletion order: `_static_source_cql_type`, `_function_return_type`
   closure, `_element_type` closures, `_logical_operand_property_cql_type`.
   After each deletion, full gate re-run.
6. **U6 — Facade flip.** Metadata-first serializer per §3.3; reconcile
   becomes logged fallback; update/re-adjudicate serializer tests; new
   facade tests per acceptance gate 4 (List<Interval<Date>>, List<Code>,
   Tuple nesting, Long vs Integer, Date vs DateTime vs Time from real
   translated libraries).
7. **U7 — Scale spot-check + gap report.** Per-library translation
   overhead check (<5% vs recorded baseline); gap backlog = remaining Any
   results AND rescue-WARNING counts (higher-signal events) on the DQM
   corpus + cql-tests corpus.

## 5. Test Strategy

- **Per-unit regression tests** (land with each unit): new test file
  `fhir4ds/cql/tests/unit/test_type_map.py` (builder matrix) +
  `fhir4ds/cql/tests/integration/test_facade_metadata_first.py` (facade).
- **Byte-identical SQL proof**: script capturing DQM 47-measure generated
  SQL pre/post (hash each measure's SQL; diff must be empty) PLUS the
  facade synthetic-library path (`define "return": <expr>` through
  `translate_library_to_sql`) over an expression matrix — the DQM corpus
  does not exercise it (review Q6-6). Run per unit.
- **Differential drift tripwire**: `test_type_map_differential_drift_tripwire`
  (see §3.2) — lands with U5 and runs in every subsequent gate.
- **Master gates per unit**: `conformance/scripts/run_all.py` 2832/2832;
  full `fhir4ds/cql` pytest tree green (tripwires: test_logical_parity.py,
  test_clinical_type_parity.py, test_list_part2_parity.py,
  test_temporal_complex_parity.py, conversion parity files, aggregate
  suites).
- **Facade**: gate 4 test list from USER_DIRECTIVES.
- **Runner**: gate 5 — hold-or-improve vs 1667/24/40 clean-runner baseline
  (hold is acceptable; do not chase the 24).
- **Scale**: gate 6 re-stated — translation time is patient-count-
  independent; measure per-library translation overhead across the
  DQM 47 + expression corpus against a recorded pre-change baseline
  (<5%).

## 6. Rollback Plan

- The metadata pass is additive (new module + one optional field). Rollback
  of U1-U5 = revert commits; no data migrations.
- The serializer flip (U6) is one commit; revert restores value-first.
- Feature flag: `CQLServerConfig.metadata_first_serialization: bool = True`
  on the config object (default on; off restores legacy reconcile-first
  order for A/B debugging and the rollback story).

## 7. Implementation Record (v0.0.16 campaign, 2026-09-20)

All units U1-U7 landed; every gate green after each unit (byte-identical SQL
47/47, conformance 2832/2832, full cql unit tree). Key as-built notes:

### 7.1 REV-002 sunset ledger entry

- **Frozen set** (lowering consumers; deletion deferred to the
  route-unification milestone): `_static_structural_type_name`
  (_query.py), `_infer_static_cql_type_for_logical_operand` (_operators.py),
  `_static_list_element_types` + inner closures `_function_return_type` /
  `_element_type` (_functions.py).
- **Deleted in v0.0.16**: `_static_source_cql_type`
  (_temporal_components.py) and `_logical_operand_property_cql_type`
  (_operators.py) — call sites now use shared module functions
  `static_source_cql_type` / `infer_fhir_property_type_str` in
  `translator/type_map.py`.
- **Tripwire**: `test_type_map_differential_drift_tripwire`
  (fhir4ds/cql/tests/unit/test_type_map.py) — 57-entry shared corpus;
  builder vs `infer_cql_type_compat` asserted identical where both non-Any.
  Documented intentional divergences: uncertainty family (age/between) →
  Any; power(int,int≥0) → Integer/Long; Sum(List<Quantity>) → Quantity;
  as/convert dotted names → bare; identifier lookup order; builder-only
  branches (QualifiedIdentifier, AliasRef, scoped query walker).
- **Legacy compatibility**: `_infer_cql_type` is a thin wrapper delegating
  to `infer_cql_type_compat(context, node)` in type_map.py — a VERBATIM
  port of the legacy logic (byte-exact wrapper proven by DQM-47 snapshot
  diff: 1049 defines, zero drift). The builder (`TypeMapBuilder.type_of`)
  is the FACADE authority and intentionally diverges per the allowlist
  above.

### 7.2 U7 scale + gap findings

- Per-library translation overhead on DQM 47: builder on vs off totals
  47.31s vs 50.05s (−5.5%, run-to-run noise; max single +46%; no scaling
  cliff — translation is patient-count-independent). Gate 6 (<5% mean
  overhead) PASS.
- Static gap census (1354 defines): 952 non-Any (70.3%); 305 `<no-ast>`
  (include-library defines — covered by the from_definition_meta
  cql_type fallback chain); 97 AST-level Any backlog: Property 48,
  Query 44, BinaryExpression 4, Identifier 1. Rescue-WARNING counts come
  from live $cql traffic (facade logger).

### 7.3 Rollback flag (as-built)

`CQLServerConfig.metadata_first_serialization: bool = True` (default on);
threaded through `handle_cql_operation` → `serialize_evaluation_result` →
`serialize_value`/`_serialize_known` (keyword-only, recursed per level).
`metadata_first=False` restores the legacy `_reconcile_type_ref`
value-first path verbatim (pre-dispatch, no rescue wrapping). Pinned by
`test_metadata_first_rollback_flag_restores_legacy_reconcile`.
