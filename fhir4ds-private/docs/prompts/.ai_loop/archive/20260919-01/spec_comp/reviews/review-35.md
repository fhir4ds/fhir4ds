# Code Review Findings — Spec-Compliance Campaign Milestone #7 (CQL-11..CQL-15)

**Date:** 2026-08-22
**Reviewer:** Code Reviewer role (milestone `code_review` workflow, seventh launch)
**Scope:** Uncommitted working-tree diff vs `db1e4164` (dev); delta since milestone #6 (review-30.md): CQL-11..CQL-15 chunk fixes — exact TruncatedDivide, Round/RoundTo `system.floor` shadowing fix, Decimal multiply overflow nulls, Successor/Predecessor boundary guards, duration-negate casts, `parse_expression` trailing-token rejection (parser.py:3010), string Indexer LIST_EXTRACT doctrine (_lists.py:891), Combine typed guards (_functions.py:1286+), SplitOnMatches parity, bare same-as parsing (parser.py:740/813), no-precision same-or bounds, starts/ends precision phrases (_temporal_comparisons.py:361+), ends-precision conjunct, collapse-per UDF lowering (`collapse_intervals_per`, `TemporalUnitPrecision`, `TemporalPrecisionMeetsOrOverlaps`, `CollapseIntervalsPerFunc`), includes precision routing (`intervalIncludesPrecise`), expand boundary truncation, CMS128 list-recognition repair. Native cql extension: math.cpp/boundary.cpp/quantity.cpp/interval.cpp/cql_extension.cpp + rebuilt binaries. Whole-tree diff: 120 files, ~20.5k insertions.

## Status of prior findings

- **REV-001 (LOW → RESOLVED)** — unguarded `std::stoi` family in evaluator.cpp: all stoi/stol/stoll sites removed during the fhirpath native rework; no occurrences remain in the 12,396-line evaluator.cpp.
- **REV-002 (MEDIUM, OPEN)** — hand-maintained metadata drift surface. No new behavior-changing IG hardcoding observed in the CQL-11..15 delta (CMS mentions in translator are comments only; `placeholder.py:95` `resource_type ==` is a data-class equality, not a model branch). Unchanged.
- **REV-003 (LOW, OPEN)** — unrelated untracked files `conformance/architecture/`, `fhir4ds/dqm/AGENTS.md` still in tree. Unchanged.
- **REV-004 (LOW → RESOLVED)** — `exactDecimalRatioText` no longer exists in evaluator.cpp (refactored away during the native rework); no equivalent unbounded ratio helper found.
- **REV-005 (LOW, OPEN)** — `_compile_regex` (strings.py:151) still compiles patterns verbatim, though it now routes through `_translate_pcre_ascii_classes` and `_translate_named_groups` at call sites, which mitigates the largest failure class. Unchanged.
- **REV-006/007 (RESOLVED/verified)** — no regression; symbol audit reconfirms.

## Clobber spot-check (CQL-11..15 symbols)

All key fix symbols present and coherent: `collapse_intervals_per` registered in `_JSON_LIST_FUNCS` (_functions.py), list-source set + from_json wrap (_query.py), First/Last JSON wrap (_lists.py), `_temporal_intervals.py` lowering, udf/interval.py, extension.py, and native `CollapseIntervalsPerFunc`/`TemporalUnitPrecision`/`TemporalPrecisionMeetsOrOverlaps` (cql_extension.cpp); `intervalIncludesPrecise` (_operators.py + udf/interval.py + native); `LIST_EXTRACT` interval recognition (_lists.py:783/891/1015); Combine static-operand validators (_functions.py:1286-1288); `system.floor`/`system.ceil` Round/RoundTo shadowing fix with documented CQL-11 HISTORIAN QA-001 rationale (macros/math.py:76-99); boundary.cpp `successor_of`/predecessor guards; parser bare-`same` handling (parser.py:740, 813) and trailing-token rejection (parser.py:3010). Prior-period symbols (QA-103 `resolve_placeholders` order_by traversal, add_alias row-shaped registration) still present. **No lost hunks detected.**

## Binary freshness (special attention)

- **cql.duckdb_extension:** repo bundle md5 `98a8c8583ed41359edfe929c03869d83` == build/release output == build/release/repository/v1.5.2 copy. Binary mtime Aug 22 03:03 > newest source cql_extension.cpp 03:00 — repo bundle fresh. **BUT site-packages copy is STALE**: md5 `025c79ed...`, mtime Aug 21 22:00 (deployed before the final rebuild). No stale copies under `~/.duckdb` cache. → **REV-008**.
- **fhirpath.duckdb_extension:** repo bundle md5 `57d0634b...` == site-packages; binary (Aug 19 09:51) newer than evaluator.cpp (Aug 19 09:37). Fresh and md5-matched.

## DQM gate (special attention)

Live runs this review against the final tree:
- Run 1: **46/47** — CMS871 ERROR "Failed to load included library 'FHIRHelpers' ... 'Token' object is not subscriptable" (error surfaced via include_handler.py:67).
- Run 2: **47/47**, 100.0% accuracy — identical tree, sequential runner, shared `library_cache` dict across measures (run_dqm.py:139).

The stored report (pre-run) was 47/47. The CMS128 collapse-per regression repair (QA-005) holds — CMS128 passed both live runs.

### Gate-claim discipline assessment (process finding)

Two mid-period DQM regressions (CQL-05 QA-103; CQL-15 SKEPTIC's collapse-per lowering breaking CMS128 with a gate claim that did not hold for the final tree) show that per-chunk gate claims are invalidated by later hunks and by single-pass verification. Combined with the intermittent CMS871 loader failure observed this review, recommendations:
1. Inner launches must re-run the DQM suite (not just `run_all` summaries) against the FINAL tree state before closing a chunk, and record binary md5s (both extensions, all three deployment locations) in the engineer handoff.
2. The DQM gate should treat loader ERRORs as retry-worthy (run the failing measure at least twice) before declaring regression or pass — one-pass gates are unreliable given REV-009 nondeterminism.
3. Chunk handoff gate claims made before the final tree state should be labeled "pre-final-tree" unless re-verified.

## New findings

- **REV-008 (HIGH, OPEN)** — `~/.local/lib/python3.10/site-packages/fhir4ds/cql/duckdb/extensions/cql.duckdb_extension` md5 `025c79edaea4af69621e5ae59060d1e3` ≠ repo bundle `98a8c8583ed41359edfe929c03869d83` (stale by one rebuild, Aug 21 22:00 vs Aug 22 03:03). Violates the GLOBAL_RULES deployment invariant; the final CQL-11..15 native fixes are not live in the installed package. Fix: re-copy repo bundle to site-packages and re-verify md5.
- **REV-009 (MEDIUM, OPEN)** — Intermittent CMS871 FHIRHelpers load failure: "'Token' object is not subscriptable" (1 of 2 identical sequential runs). Root cause unknown; candidates are the shared `library_cache` (run_dqm.py:139) interacting with include resolution (include_handler.py:38-67) and nondeterministic parse/AST state. Gate flakiness risk in both directions. Evidence: two live run logs from this review.

Other audit dimensions: no new SQL-injection vectors (`LOAD '{escaped_path}'` in extension.py:105 escapes the path; macros interpolate internal constants only); no new error swallowing in the delta; no behavior-changing IG/model hardcoding in generic logic; SQLRaw usage unchanged and confined to boundary APIs; CMS871 point-type warning is a non-fatal inference default with an explicit message.

## Overall assessment

The CQL-11..15 delta is spec-grounded and well-tested; the CMS128 recovery repair is intact and verified live. Two new issues: one HIGH deployment gap (stale site-packages CQL binary — mechanical fix) and one MEDIUM intermittent loader failure worth root-causing. Prior hardening debt shrinks to three OPEN items (REV-002/003/005, all LOW/MEDIUM). No blockers for the next pipeline step, but REV-008 should be remediated before any wheel build or pre_release pass.

**Exit recommendation:** CLEAN (milestone review complete; open items are tracked debt; REV-008 flagged for the pre-release deployment check).
