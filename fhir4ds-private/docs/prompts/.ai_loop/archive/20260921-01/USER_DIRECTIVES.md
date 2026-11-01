# 🎯 USER DIRECTIVES — v0.0.16 CQL TYPE SYSTEM

<!--
This file is the PRIMARY MANDATE for the AI Initializer for the v0.0.16 cycle.
v0.0.15 (DuckDB upgrade + pressure-test remediation + evolution campaign)
runs FIRST — this cycle builds on the post-0.0.15 tree. Do not start until
the v0.0.15 pipeline has completed (USER_DIRECTIVES.md, main file).
-->

## Strategic Goal

Deliver **Option A: a complete, authoritative CQL type-inference layer** for
the fhir4ds-v2 CQL translator, so every library define/expression carries
its exact CQL type (List<T> element types, Interval point types,
Date/DateTime/Time, Integer/Long/Decimal, Code/Concept/Quantity/Ratio,
Tuple fields) through to the result boundary — eliminating the
shape-guessing heuristics in the `$cql` facade serializer and closing the
"exact type isn't easy via DuckDB" gap identified in the certification
work (2026-06-04, commit a3da6e9d and the cql-tests-runner campaign:
clean-runner baseline 1667 pass / 24 fail / 40 skip).

Ship as **fhir4ds-v2 0.0.16**.

**Scope decision (Joel, 2026-09-19):** Option C (targeted facade
heuristic fixes toward the 24 clean-runner fails) is explicitly DEFERRED —
no immediate certification need. This campaign does Option A only.

## Target Version

**0.0.16** (Release Engineer bumps from 0.0.15). medterm4ds bound
unchanged. DuckDB pin: whatever 0.0.15 landed (single-pin doctrine).

## Pipeline

1. `feature_design`
2. `feature_implementation`
3. `code_review`
4. `pre_release`
5. `docs_audit`
6. `scribe`

## Feature Design (Option A — CQL Type System)

Execute `ROLE_FEATURE_DESIGNER.md`. The WAIT_FOR_USER_APPROVAL gate is
**KEPT** for this cycle: the refined FDD gets a human review (Joel) before
implementation begins — this is exactly the class of architectural decision
worth a checkpoint. Use `/second-opinion` on the core architecture choice
during design refinement and present its view alongside the designer's.

### Problem statement (verified history)

The translator lowers CQL → SQL; DuckDB returns physical types
(VARCHAR/DOUBLE/JSON), erasing CQL types at the boundary. Type knowledge
exists only piecemeal:

- `DefinitionMeta.cql_type` + `stores_list_value` + `RowShape`
  (`fhir4ds/cql/translator/cte_manager.py`) — per-define, incomplete
- `_function_return_type`, `_infer_static_cql_type_for_logical_operand`,
  `_static_source_cql_type`, `_infer_static_numeric_type` — scattered
  single-purpose classifiers in `translator/expressions/`
- `_infer_cql_type` lives on the library translator, not the mixin stack
  (CQL-03 doctrine forced standalone duplicates)
- The facade (`fhir4ds/cql/fhir_server/result_serializer.py`)
  compensates with `_reconcile_type_ref` + `_infer_runtime_type`
  shape-guessing (VARCHAR "looks like" a date; JSON "looks like" an
  interval) — documented fragile seam; AGENTS.md doctrine line: result
  serialization "must be CQL-metadata-driven. Do not pick valueDate/
  valueCoding/... based only on DuckDB physical type"

### Design constraints (binding)

1. **Metadata-only in v0.0.16 — lowering routes must NOT change.** The
   unified type pass runs ALONGSIDE translation and feeds the result
   boundary; it must not become the routing authority for SQL lowering.
   Rationale: widening type inference once silently changed lowering
   routes and regressed CMS128 (CQL-20 HISTORIAN incident); the dynamic
   -list shape-selection detection layer is accreted chunk-tagged
   carve-outs (REV-010) that must not be perturbed mid-cycle. Route
   unification is a follow-up milestone, explicitly OUT OF SCOPE.
   **Acceptance proof of metadata-only-ness: generated SQL is
   byte-identical pre/post for the DQM 47-measure corpus.**
2. **One authoritative classifier.** Consolidate the scattered inference
   helpers into a single type-assignment module (reuse `CQLTypeRef` from
   `fhir_server/types.py` as the canonical representation — it already
   parses/serializes the needed shapes). Existing helpers become thin
   wrappers or are deleted — no parallel hand-maintained duplicates
   (REV-002 drift family rule).
3. **Both consumers, one source.** The complete type map attaches to
   `CQLResultMetadata` for the facade AND remains readable by the
   translator's existing consumers (definition_meta readers) without
   behavior change.
4. **Serializer flips to metadata-first.** `_reconcile_type_ref` /
   `_infer_runtime_type` demote to a fallback + assertion layer (log when
   they must override metadata — every override is a type-map gap to
   close); typed `CQLFacadeError` only for genuinely untyped dynamic
   values.
5. **Type sources the FDD must enumerate** (walk the AST): literal
   selectors (all §3 grammar forms incl. typed nulls, lists, tuples,
   intervals, instances), retrieve element types (FHIR_TYPE_TO_CQL_TYPE
   mapping + choice disjunction), function return types (builtins +
   user-defined fluent/inline chains + include libraries), if/case
   common-type, query sources (from/let/return/alias chains incl. the
   depth-2 alias propagation doctrine from CQL-19), parameters (declared
   types incl. default-value refinement), Coalesce/common supertypes, and
   definition references (forward/recursive cutoff policy).
6. **Unknown is a first-class answer.** The map may yield `Any` for
   genuinely dynamic values — never guess. The facade falls back to
   runtime inference only for `Any`.
7. **Dual-engine parity preserved** — this is translator-layer Python
   only; no extension rebuilds expected (native/WASM untouched).

### FDD deliverables checklist

- Architecture: module layout, data flow (AST → type map →
  DefinitionMeta/metadata → facade), CQLTypeRef canonicalization rules
- Complete type-source enumeration (constraint 5) with per-source test
  matrix
- Migration/compatibility plan for each existing consumer of
  `cql_type`/`stores_list_value`/`_function_return_type` (wrapper or
  delete, no duplication)
- Acceptance gates (below) + failure taxonomy (typed errors, never silent)
- Rollback plan (metadata pass is additive; serializer flip is one
  feature-flagged commit)

## Acceptance Gates (binding for implementation)

1. **Byte-identical SQL**: DQM 47-measure corpus generated SQL identical
   pre/post (metadata-only proof).
2. **Master conformance gate**: 2832/2832 (ViewDef 144, FHIRPath 935,
   CQL 1706, DQM 47) — hard, non-negotiable.
3. **Full `fhir4ds/cql` pytest tree green**, including the spec-compliance
   campaign regression files (`test_logical_parity.py`,
   `test_clinical_type_parity.py`, `test_list_part2_parity.py`,
   `test_temporal_complex_parity.py`, `test_conversion_*_parity.py`,
   aggregate/list/temporal suites) — these pin the type-inference seams
   (stores_list_value, alias propagation, logical-operand typing) and are
   the tripwires for this work.
4. **Facade**: serializer metadata-first with runtime fallback; fallback
   overrides logged; existing facade tests updated; new tests: exact types
   for List<Interval<Date>>, List<Code>, Tuple nesting, Long vs Integer,
   Date vs DateTime vs Time disambiguation from real translated libraries.
5. **cql-tests-runner clean report**: hold-or-improve vs the 1667/24/40
   baseline (improvement NOT promised — type-guessing may not be among
   the 24 fails; do not chase the 24, that's deferred Option C).
6. **20k-patient scale spot-check**: no measurable translation-time
   regression from the added pass (<5% on the CQL 0.42s benchmark class).

## Spec-Compliance Pass? — NO (adjudicated)

A full ~50-chunk spec-compliance re-run is NOT warranted: v0.0.16 is
metadata-only by design (constraint 1 — byte-identical SQL), so operator
semantics cannot change. Coverage instead comes from gate 2 + gate 3 (the
existing campaign regression suites ARE the spec-compliance tripwires) +
gate 5. Revisit ONLY if implementation proves unable to meet constraint 1
— if lowering routes must change, STOP, record NEEDS_CONTEXT, and return
to Joel for a scope decision (that would become a spec-compliance-gated
follow-up).

## Feature Implementation

Per `ROLE_FEATURE_ENGINEER.md`, execute the approved FDD. Surgical diffs;
no drive-by refactors of the detection layer (REV-010 stays open);
regression tests land with each unit of work (per-domain, not one big-bang
suite). Every checkin-sized unit passes gates 1-3 before the next starts.

## Code Review

Standard `ROLE_CODE_REVIEWER.md` audit of the full 0.0.16 diff. Verify:
metadata-only invariant (SQL diff proof re-run on final tree), no
duplicated type tables (REV-002 family), REV ledger carried forward,
clobber spot-checks for the 0.0.15 fix symbols still intact, extension
binary md5 parity (should be untouched — flag any binary change as a
review finding).

## Release Prep (pre_release)

Per `ROLE_RELEASE_ENGINEER.md`: bump 0.0.15 → 0.0.16 (pyproject + root +
all 6 subpackage constants), wheel build, `pip check`, fresh-install smoke
(3.10 + 3.11), medterm4ds bound verified in METADATA, gate 2832/2832 from
clean env, extension md5s repo == site-packages == wheel, both CI legs
green.

## Documentation Updates (docs_audit)

Per `ROLE_DOCS_AUDITOR.md`, target 0.0.16:
- New architecture doc section: the CQL type system (type map, CQLTypeRef
  canonical form, facade metadata-first contract, `Any` fallback policy).
- Facade/AGENTS.md doctrine update: `_reconcile_type_ref` heuristics are
  FALLBACK ONLY; every override is a logged gap.
- Release notes v0.0.16: type system, facade exact-type serialization,
  certification-readiness framing (runner baseline status).
- Website per `web/website/AGENTS.md` (PRODUCT_VERSION, releases.md,
  wheel refresh in wasm-demo + static/wasm-app) — standard release steps.

## Scribe

Concise commit message(s) from ARCHIVE_LOG.md / GLOBAL_KNOWLEDGE.md.
(Drafts only — Joel commits.)

## Focus Areas (cross-cutting)

- **Ordering**: v0.0.15 completes first; this campaign starts from that
  tree. If 0.0.15's DuckDB upgrade was deferred/blocked, proceed on 1.5.2
  — the type pass is DuckDB-version-independent.
- **Non-regression**: gates 1-3 run per implementation unit AND at
  code_review/pre_release.
- **Fix root causes**; no heuristic shims layered over the type map.
- **No commits** at any pipeline step — Joel reviews and commits.
- **Single-writer discipline**; PROC_VALIDATION.md context rules
  (PYTHONPATH=/mnt/d/fhir4ds, filtered output, fresh runs).
- **Deferred, do not do here**: Option C facade fixes, the 24
  clean-runner fails, REV-010 route unification, spec-compliance
  re-campaign.
