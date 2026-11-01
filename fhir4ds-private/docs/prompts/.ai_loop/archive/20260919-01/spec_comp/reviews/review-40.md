# Code Review Findings — Spec-Compliance Campaign Milestone #8 (CQL-16..CQL-20)

**Date:** 2026-08-22
**Reviewer:** Code Reviewer role (milestone `code_review` workflow, eighth launch)
**Scope:** Uncommitted working-tree diff vs `db1e4164` (dev); delta since milestone #7 (review-35.md): CQL-16..CQL-20 chunk fixes — interval sentinels (int64/Quantity) + open-bound native intersect + cross-numeric compare (extensions/cql/src/cql/interval.cpp), boundary/difference/math dispatch + `QuantitySentinelJson` (cql_extension.cpp), LIST_EXTRACT recognition, in-keyword dispatch, dynamic-list promotion machinery (`_promote_fhirpath_text_list`, `stores_list_value`/`stores_patient_list` markers, alias-marker propagation), union rows-gating with peer-shape guards, full-list materialization (`_list_operator_full_list_source`), SingletonFrom adjudication, sub-day Difference boundaries (`_subday_boundary_difference`), Duration uncertainty, bare same-as parsing, starts/ends precision phrases, expand low-only truncation, typed aggregate dispatcher + decimal-exact shifted-deviation statistical macros (macros/aggregate.py), cte_manager UNKNOWN-branch guards, extensive parity/regression tests. git status/diff hang on the drvfs tree (known); review used the session-start snapshot plus targeted file/symbol inspection per PROC_VALIDATION context protection.

## Status of prior findings

- **REV-002 (MEDIUM, OPEN)** — metadata drift surface: unchanged. QICore mentions in the delta are config paths/docstrings (`model_config.py`, `fluent_function_loader.py` content-root search paths); no behavior-changing IG hardcoding in generic logic.
- **REV-003 (LOW, OPEN)** — untracked `conformance/architecture/` and `fhir4ds/dqm/AGENTS.md` still in tree. Unchanged.
- **REV-005 (LOW, OPEN)** — `fhir4ds/fhirpath/engine/invocations/strings.py:151` still routes through `_translate_pcre_ascii_classes` (mitigated), but `fhir4ds/fhirpath/duckdb/functions/string.py:59` still compiles patterns verbatim. Unchanged.
- **REV-008 (HIGH → RESOLVED)** — stale site-packages cql binary: repo bundle md5 `3e7d4167143e01907fdd8561db43b7d7` == site-packages copy; binary mtime (Aug 22 05:59) > newest native sources (interval.cpp 05:57, cql_extension.cpp 04:38). Deployment invariant satisfied.
- **REV-009 (MEDIUM, OPEN)** — intermittent FHIRHelpers loader failure: root cause not addressed; this review's live DQM run passed 47/47 with no loader error (1 run — inconclusive given 1-of-2 historical flakiness). `library_cache` sharing (run_dqm.py:139, include_handler.py:229-313) remains the prime suspect.

## Clobber spot-check (CQL-16..20 symbols)

All key fix symbols present and coherent:
- Interval: `sentinel_start_bound`/`sentinel_end_bound` with int64/Long doctrine comments (interval.cpp:736/772/1143-1153), open-bound `Interval::intersect` (interval.cpp:1510+), cross-numeric int64/double bound parsing (interval.cpp:293-356), `QuantitySentinelJson` ±1e20 sentinels (cql_extension.cpp:879/914/950).
- Lists: `_promote_fhirpath_text_list` (_utils.py:40, invoked from translator.py:1835, _functions.py, _lists.py, _operators.py); `stores_list_value` marker (context.py:307) set/propagated in translator.py:1741-1897 (dynamic-list, navigation-list, union, alias, SQLArray, and list-returning PATIENT_SCALAR paths) and consumed at 15+ dispatch sites; `stores_patient_list` (translator.py:1741, _property.py:292); LIST_EXTRACT doctrine (_lists.py:829/937/1061/1116); union rows-gating + `_union_operand_as_list` peer-shape guards (_operators.py:4170-4230); full-list materialization `_list_operator_full_list_source` (_lists.py:2291+); SingletonFrom with pinned >1 NULL adjudication (_functions.py:3712, _lists.py:2484).
- Temporal/string: bare-`same` parsing (parser.py:740/813); `_subday_boundary_difference` (udf/datetime.py:406+3 sites); `_duration_between_with_uncertainty` (udf/datetime.py:474); expand low-only truncation (udf/interval.py:3996).
- Aggregates: decimal-exact shifted-deviation `_statistical_macro` for StdDev/Variance/Median (macros/aggregate.py:55-109); CQL-20 typed-dispatcher markers throughout _functions.py.
- cte_manager UNKNOWN-branch guards intact (cte_manager.py:1374-1413 scalar-aggregate/derived-table `_pt`-correlation preservation; :1678-1682 UNKNOWN-shape identity passthrough).
**No lost hunks detected.** Prior-period symbols (collapse_intervals_per, intervalIncludesPrecise, system.floor shadowing fix) also reconfirmed present.

## Binary freshness (special attention)

- **cql.duckdb_extension:** repo bundle `fhir4ds/cql/duckdb/extensions/` md5 `3e7d4167143e01907fdd8561db43b7d7` == site-packages copy. Binary mtime Aug 22 05:59 > interval.cpp 05:57 > cql_extension.cpp 04:38. Fresh and md5-matched (matches the campaign's expected `3e7d4167`).
- **fhirpath.duckdb_extension:** repo bundle md5 `57d0634b6ee6eddee9fc06a1355bef5a` == site-packages. Fresh.
- No stale copies found under `~/.duckdb` cache (no cql copies present).

## DQM gate (special attention)

Live run against the final tree: **47/47 measures passed (100.0%)** — includes the three mid-period regression families (CMS128, CMS117/122/124/125/130, CMS1017/832) and no FHIRHelpers loader error this pass. The repaired shape-selection machinery holds on the final tree.

## Shape-selection machinery assessment (mandated special attention)

The machinery has a **principled core**: a physical-shape metadata model (`RowShape`, `stores_list_value`, `has_resource`, `cql_type`) that downstream dispatch reads uniformly. However, the **trigger/detection layer is accreting special cases**: translator.py:1726-1900 alone stacks five chunk-tagged detection paths (CQL-18 HISTORIAN QA-001 dynamic-list, CQL-18 EXPLORER QA-001 navigation-list, CQL-19 SKEPTIC QA-003 union operand classifier, CQL-19 HISTORIAN QA-003 null-operand widening, CQL-19 EXPLORER QA-004 list-returning scalar, plus alias propagation), each keyed to syntactic AST shapes rather than inferred data types. The union operand classifier `_is_element_list_union_operand` (translator.py:1792-1806) whitelists node kinds (Property/ListExpression/null/`as`/nested-union) specifically to keep DQM resource unions out — a regression-guard-shaped carve-out, and its separate `not isinstance(..., _DefRetrieve)` checks are dead conditions (Retrieve already fails the whitelist). `_union_operand_as_list`'s `peer_rows` gating (_operators.py:4210+) is another measure-regression-driven asymmetry (documented, correct today, but fragile). Three DQM regressions in one period caught by the gate is consistent with this fragility. **REV-010 (MEDIUM)**: consolidate shape detection into a single type-inference-driven classifier (compute list-ness from inferred CQL types once) instead of per-operator syntactic promotion + peer-gating; every new special case currently risks silently rerouting resource unions.

## New findings

- **REV-010 (MEDIUM, OPEN)** — maintainability: dynamic-list shape-selection detection layer accretes chunk-specific syntactic special cases (translator.py:1726-1900; _operators.py:4170-4230 `_union_operand_as_list` peer-gating; _lists.py:2266-2341 retrieve-shaped predicates). Metadata model is sound; detection should be type-driven and centralized. Includes dead redundant Retrieve guards in the union branch.
- **REV-011 (LOW, OPEN)** — `macros/aggregate.py` shifted-deviation macros reference the first non-null element via `list_filter(x,...)[1]` per aggregate call; within a single query with multiple statistical aggregates over the same column this re-filters/re-anchors per macro (DuckDB may not CSE macro expansions). Correctness is fine (shift-invariance documented); minor performance/consolidation note only.

Other audit dimensions: no new SQL-injection vectors (macros interpolate internal type-guard strings only; `error('CQL ... requires List<Decimal> source')` is a fixed literal); no new error swallowing (`except` blocks in the delta are narrow and re-raising/wrapping); no behavior-changing IG/model hardcoding in generic logic (CMS mentions are comments/docstrings only); SQLRaw usage unchanged and confined to boundary APIs; Quantity sentinels use documented ±1e20 domain constants rather than magic per-measure values.

## Overall assessment

The CQL-16..20 delta is spec-grounded, exceptionally well-tested (17+19 tests in the two new parity files alone, with doctrine comments pinning each fix to spec sections and QA incident IDs), and the deployment invariant is finally satisfied across all locations (REV-008 resolved). DQM is green on a live final-tree run. The one structural concern is REV-010: the shape-selection detection layer is winning by accretion — each DQM regression added another syntactic carve-out — and should be consolidated before the next operator family lands on top of it.

**Exit recommendation:** CLEAN (milestone review complete; open items REV-002/003/005/009/010/011 are tracked debt; none block the next pipeline step).
