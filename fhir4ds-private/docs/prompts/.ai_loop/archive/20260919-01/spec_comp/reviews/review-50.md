# Code Review Findings — Spec-Compliance Campaign Milestone #10 (50 chunks: through CQL-22 + SOF-VD-01..08)

**Date:** 2026-08-23
**Reviewer:** Code Reviewer role (milestone `code_review` workflow, tenth launch)
**Scope:** Uncommitted working-tree diff vs `db1e4164` (dev); delta since milestone #9 (review-45.md): SOF-VD-04..08 + CQL-22 chunk fixes — ViewDef select/column/tag unknown-key + minItems + element-ID validation, constants (integer64 guard, Decimal parse_float, backtick %`name`), repeat recursion-budget thread guard, unionAll null-row suppression (wrapper-instance identity at all depths), fhirpath fallback `_run_with_recursion_budget` + `_is_shadow_extension` provenance, CQL Message/aliased-query where fix. git status/diff flaky on drvfs (known); review used the environment's file snapshot + mtime-based delta identification (post Aug-23 05:00: viewdef types/constants/generator/metadata/parser, fhirpath/__init__, duckdb/udf.py, engine/evaluators/__init__, cql _query.py + tests) plus live execution per PROC_VALIDATION.

## Status of prior findings (all unchanged this delta)

- **REV-002 (MEDIUM, OPEN)** — metadata drift: no new hand-maintained maps added in this delta.
- **REV-003 (LOW, OPEN)** — untracked `conformance/architecture/ARCHITECTURE.md` and `fhir4ds/dqm/AGENTS.md` still present.
- **REV-005 (LOW, OPEN)** — `strings.py:155` still routes through `_translate_pcre_ascii_classes` (re-confirmed live: DeprecationWarning surfaced in parity run).
- **REV-009 (MEDIUM, OPEN)** — FHIRHelpers loader: DQM 47/47 green again this run (third consecutive), no loader error. Still unrooted; keep OPEN but trending transient.
- **REV-010 (MEDIUM, OPEN)** — shape-selection accretion: no new syntactic carve-outs in this delta.
- **REV-011 (LOW, OPEN)** — macro re-anchoring: unchanged.
- **REV-012 (MEDIUM, OPEN)** — cqlUncertain* dual-impl drift: unchanged; no C++ changes since milestone #9 (cql_extension.cpp mtime 08-23 04:23 < binary 04:28).
- **REV-013 (LOW, OPEN)** — fhirVersion binding ships 63 codes (re-verified live), spec-cited; informational only.

## Clobber spot-check (SOF-VD-04..08 + CQL-22 symbols)

All key fix symbols present and coherent; no lost hunks:
- unionAll null-row suppression: `foreachornull_wrapper_ids` paired collection (generator.py:1586/1702-1704/1762/2088), `_union_origin_id` tagging in `_expand_select_unions` (generator.py:2030), `seen_union_wrapper_ids` first-branch-emits logic + `_suppress_null_preserved_row` (generator.py:1892, applied at 2105). Identity via `id(select)` is safe: all wrapper copies stay referenced by `expanded_selects` for the duration of generation, so no id reuse. 31 new tests in `test_union.py`.
- Repeat recursion budget: `_run_with_recursion_budget` (fhirpath/duckdb/udf.py:235-315) with in-place <=20k, worker thread with sized stack above, clean RecursionError degradation; `evaluate_repeat` routed through it (udf.py:3376).
- Shadow-extension provenance: `_is_shadow_extension` set at synthesis (engine/evaluators/__init__.py:480/489) and consumed by both returnRawData and visit filters (fhirpath/__init__.py:78-104) — genuine extension-only elements survive; only `_field`-synthesized nodes dropped.
- Parser validation: unknown column/select fields (parser.py:141-145, 264-268), minItems (parser.py:275-281), `tags`→singular `tag` (parser.py:136-139), tag namespace recommendation (parser.py:857-864).
- Constants: backtick `%\`name\`` substitution (constants.py:90-96, 391), `parse_float=Decimal` (parser.py:455).
- CQL: aliased-query where/return alias binding (_query.py:2220-2246 region), Message parity — 13/13 tests pass.

## Regression interplay check (special attention a)

SOF-VD-07/08 touched the fhirpath fallback evaluator and viewdef generator core. Full viewdef suite (unit + integration incl. test_duckdb.py, test_repeat.py, test_union.py): **1208 passed, 0 failed**. ViewDef conformance: **144/144**. The fallback evaluator changes are provenance-flag-only (no evaluation semantics change); no regression observed.

## Binary freshness (special attention c)

- **cql.duckdb_extension:** repo `c5b22d58310c1eb7bafa17ce7877f989` == site-packages == campaign-expected hash; binary 08-23 04:28 > newest cql source 04:23. Fresh.
- **fhirpath.duckdb_extension:** repo `57d0634b6ee6eddee9fc06a1355bef5a` == site-packages; binary 08-19 09:51 > newest fhirpath source (evaluator.cpp 08-19 09:37). No C++ changes in this delta. Verified current: the binary contains the post-rework native string `"Invalid operands for date/time arithmetic"` (evaluator.cpp:9651). No stale copies under `~/.duckdb`.

## Pre-existing fhirpath parity failures + stale-binary assessment (special attention d)

Reproduced live: **7 failed, 220 passed** in test_string_transform_parity.py + test_arithmetic_parity.py:
1. 5× `test_temporal_arithmetic_spec_edges_native_and_fallback` (`@2016 + 1 'a'`, `@2016-01 + 1 'mo'`, `@2016-02-29 + 23 hours`, `@T12 + 1 day`, `@1974-12-25 - 1 'cm'`) — the **fallback** assert (test_arithmetic_parity.py:393) fails: Python fallback reports valid=True where native (verified live: empty result) and the expected value are False/empty. Native is correct; the Python fallback's validity flag diverges.
2. 2× regex (`replaceMatches` named-group `(?<month>…)`/`${day}` substitution, test_string_transform_parity.py:377; `abc$`.matches with trailing newline, :439) — **native** gap: `std::regex_replace` (evaluator.cpp:5448-5478) does not support named groups or `${name}` substitution; source-level limitation.

**Assessment:** the SOF-VD-07 SKEPTIC handoff claim "C++ sources are ahead of the deployed Aug-19 binary" is **disproven** by three independent signals (binary mtime > all source mtimes; md5 repo==site-packages unchanged since before the claim; a distinctive post-rework native string present in the binary, and native passing the temporal tests the fallback fails). **No fhirpath binary rebuild is needed before campaign end.** The 7 failures are source-level work items, not staleness: fix the fallback validity flag (small Python fix) and route/extend native named-group substitution (std::regex limitation — likely fallback routing or regex-engine work). Filed as REV-014/REV-015.

## New findings

- **REV-014 (MEDIUM, OPEN)** — Python fallback temporal-quantity arithmetic validity divergence: `_surfaces(fallback)` returns valid=True for 5 temporal±UCUM-quantity edge cases where native and expected are empty/False (test_arithmetic_parity.py:393). Violates the dual-engine lockstep invariant; fallback-only blast radius. Fix: align fallback validity/emptiness semantics with native `fn_dateArith`.
- **REV-015 (MEDIUM, OPEN)** — native `replaceMatches` lacks named-group capture substitution (`(?<name>` + `${name}`) and `$`-anchor-vs-trailing-newline parity (evaluator.cpp:5448-5478, std::regex limitation; Python fallback correct). Dual-engine lockstep violation, native-side gap; pre-existing, first time tracked as an issue.
- **REV-016 (LOW, OPEN)** — `_run_with_recursion_budget` (udf.py:262-311) mutates the process-global `threading.stack_size()` and `sys.setrecursionlimit()` while other threads may be spawning/evaluating (lock is held only around the setters, not during `func`). Worst case under concurrent DuckDB UDF execution: sibling threads get oversized stacks or an inflated recursion limit. Bounded, daemon-threaded, and fail-closed to RecursionError; acceptable today, worth a dedicated worker-thread pool if UDF concurrency grows.

Other audit dimensions: no new SQL-injection vectors (`_suppress_null_preserved_row` interpolates only generator-internal aliases); no new error swallowing (udf.py:3377 debug-logs at UDF boundary per existing null-propagation doctrine; generator.py:407 parse-failure→True is conservative); no behavior-changing IG/model hardcoding in the delta.

## Live gates

- ViewDef unit + integration: **1208 passed** (up from 860 — union/repeat/validation test growth).
- ViewDef conformance: **144/144**.
- DQM: **47/47**, accuracy 100%, no FHIRHelpers loader error.
- CQL Message parity: **13/13**.
- cql_tests_runner_report.json still `status: "not-run"` (unchanged from #9; LOW, informational).

## Overall assessment

The SOF-VD-04..08 + CQL-22 delta is spec-grounded, well-tested (1208 viewdef + 144 conformance + 47/47 DQM green), and the deployment invariant holds for both extensions (md5-matched, binary newer than sources, campaign-expected hashes). The mandated stale-binary question resolves to **no rebuild needed**; the 7 pre-existing parity failures are tracked source-level items (REV-014 fallback validity flag, REV-015 native named-group gap). Structural debt (REV-002/003/005/009/010/011/012/013) is unchanged and non-blocking.

**Exit recommendation:** CLEAN (milestone review complete; all open items are tracked debt; none block return to the outer spec-compliance orchestrator).
