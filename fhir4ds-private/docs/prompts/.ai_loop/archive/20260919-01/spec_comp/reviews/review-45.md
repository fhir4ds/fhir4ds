# Code Review Findings — Spec-Compliance Campaign Milestone #9 (CQL-21..CQL-22 + SOF-VD-01..03)

**Date:** 2026-08-23
**Reviewer:** Code Reviewer role (milestone `code_review` workflow, ninth launch)
**Scope:** Uncommitted working-tree diff vs `db1e4164` (dev); delta since milestone #8 (review-40.md): CQL age-uncertainty machinery (uncertainty-aware duration/age, cqlUncertain{Add,Subtract,Multiply,Compare,Min,Max,ListMin,ListMax,ListSum} UDFs in Python + native, several native rebuilds, cql binary md5 `c5b22d58`), dynamic Code equality (`coding_matches_exact`), `Average` registration, aliased-query where-clause fix, boolean-constant column guard; ViewDef fhirVersion full-codesystem binding, DeviceAlert resource type, integer64 constant guard, Decimal constants (parse_float=Decimal + plain-notation serialization), preflight warning text, boolean constant column runtime-guard routing; extensive parity tests. git status/diff are slow on drvfs (known); review used a background git status snapshot plus targeted file/symbol inspection and live execution per PROC_VALIDATION.

## Status of prior findings

- **REV-002 (MEDIUM, OPEN)** — metadata drift: unchanged. New delta hardcodes only spec-published value sets (`FHIR_VERSION_CODES` in viewdef/metadata.py:63-95 with source citation), which is data-driven-with-citation, not IG behavior branching.
- **REV-003 (LOW, OPEN)** — untracked `conformance/architecture/ARCHITECTURE.md` and `fhir4ds/dqm/AGENTS.md` still present. Unchanged.
- **REV-005 (LOW, OPEN)** — `strings.py:155` still routes through `_translate_pcre_ascii_classes` (mitigated); `fhir4ds/fhirpath/duckdb/functions/string.py` still compiles verbatim. Unchanged.
- **REV-009 (MEDIUM, OPEN)** — FHIRHelpers loader flakiness root cause not addressed; this milestone's DQM report is 47/47 green with no loader error (second consecutive green run — leaning transient, keep OPEN).
- **REV-010 (MEDIUM, OPEN)** — shape-selection accretion: no new syntactic carve-outs added in this delta; the CQL-21 dispatch sites (`operators.py:252-257`, `_lists.py:2945`, `_functions.py:111` whitelist) reuse the existing UDF-name dispatch pattern. Unchanged.
- **REV-011 (LOW, OPEN)** — macro re-anchoring: unchanged.

## cqlUncertain* family assessment (mandated special attention)

Nine uncertainty UDFs are implemented **twice**: Python (`fhir4ds/cql/duckdb/udf/datetime.py:716-967`, registered at 2394-2404) and native C++ (`extensions/cql/src/cql_extension.cpp:3852-4060`, registered at 7602-7627). Runtime selection is sound: `extension.py:_try_load_bundled_cpp_extension` + `_SafeConnection._function_exists` skips Python re-registration of native-owned names, so exactly one implementation executes per connection (native on DuckDB 1.5.x; Python only as fallback). Live smoke test on DuckDB 1.5.2 (native path) confirms correct three-valued semantics: `[4,16] >= 15 → NULL`, `3 × [-2,5] → [-6,15]`, `Sum(1,[2,3]) → [3,4]`, `Min(2,[1,9]) → [1,2]`.

However the two implementations have **drifted in input strictness** (fallback-only blast radius):
- Python `_parse_int_or_interval` (datetime.py:708-713) defaults missing keys via `av.get('start', 0)`/`av.get('end', 0)` — a malformed interval JSON yields a bounds-containing-0 interval instead of NULL; native `ParseUncertainRange` (cql_extension.cpp:3738-3766) fails closed to NULL.
- Native accepts both `start`/`low` and `end`/`high` key aliases; Python only `start`/`end`.
- Python on a float string (`"4.5"`) returns a float from orjson, fails `isinstance(av, int)`, then `av.get(...)` raises an uncaught AttributeError inside the UDF (crash rather than NULL).

Filed as **REV-012 (MEDIUM)**: dual-language duplication of CQL uncertainty semantics (18 implementations + translator dispatch spread over 3 files) mirrors the REV-010 accretion pattern; recommend either sharing the parser strictness doctrine (fail-closed, one key schema) or generating one side from the other, plus a fallback-path parity test (the only cqlUncertain tests live in `test_clinical_operator_parity.py`, executed against native).

## Clobber spot-check (CQL-21..22 + SOF-VD-01..03 symbols)

All key fix symbols present and coherent; no lost hunks:
- Age/duration uncertainty: `_age_with_uncertainty` (udf/age.py:63, 3 call sites), `_duration_between_with_uncertainty` (udf/datetime.py:474, shared with DurationBetween/DifferenceBetween at 690-705), native age.cpp/age.hpp/boundary.cpp/interval.cpp/math.cpp all modified with §22.21/§22.22 doctrine comments.
- cqlUncertain family: all 9 Python funcs (datetime.py:716-967) + all 9 native funcs (cql_extension.cpp:3852-4060) + registrations both sides.
- Dynamic Code equality: `_translate_dynamic_code_equality` + `_resolve_code_ref_for_dynamic_equality` (_operators.py:3716-3760), `codingMatchesExact` (udf/valueset.py:453, registered 718) with exact-match-on-defined-elements semantics documented.
- Average: `_functions.py:2398-2400` keyword normalization + registration.
- Aliased-query where: `_query.py:2281/2443-2453/3745-3747` alias binding for WHERE/RETURN; parity tests in `test_structural_type_parity.py:1093+`.
- ViewDef: `FHIR_VERSION_CODES` frozenset (metadata.py:63-95, **63 codes**, full codesystem incl. `[publication].[major]` parents, source-cited — mandate text said "60", the extra 3 are the parent-level codes and this is the more spec-faithful full binding; informational only); `DeviceAlert` (metadata.py:29); integer64 range guard (constants.py:147-159, 230); `parse_float=Decimal` (parser.py:417); preflight warning text (generator.py:1197-1234); boolean-constant column runtime guard routing (generator.py:444).

## Binary freshness (special attention)

- **cql.duckdb_extension:** repo bundle md5 `c5b22d58310c1eb7bafa17ce7877f989` == site-packages copy (`~/.local/lib/python3.10/site-packages/fhir4ds/.../cql.duckdb_extension`) == `/tmp/duckdb_cpp_ext` build copy. Binary mtime Aug 23 04:28 > newest native source (cql_extension.cpp 04:23, age.cpp 04-22 19:40). Fresh and md5-matched (matches the campaign's expected `c5b22d58`).
- **fhirpath.duckdb_extension:** repo md5 `57d0634b6ee6eddee9fc06a1355bef5a` == site-packages. Binary Aug 19 09:51 > evaluator.cpp Aug 19 09:37. Fresh.
- No stale cql copies under `~/.duckdb` cache.

## Live gates

- ViewDef unit + spec compliance: **860 passed** (test_constants, test_parser, test_spec_compliance).
- DQM report: **47/47** measure tests passed, no FHIRHelpers loader error.
- ViewDef conformance report: **144/144** tests passed.
- Note: `conformance/reports/cql_tests_runner_report.json` has `status: "not-run"` — modified in the diff but the runner was not executed this cycle (LOW, informational).

## New findings

- **REV-012 (MEDIUM, OPEN)** — cqlUncertain* dual implementation drift: Python fallback parser is lenient/divergent vs native (`datetime.py:708-713` missing-key defaults to 0, no `low`/`high` alias support, uncaught AttributeError on float strings) and the 9-function family is hand-maintained in two languages; only the native path is exercised by tests. Consolidate strictness doctrine + add fallback-path coverage.
- **REV-013 (LOW, OPEN)** — informational: milestone mandate cites "60 codes" for the fhirVersion binding; implementation ships 63 (full codesystem incl. 3 parent-level codes) with source citation. More spec-faithful than the mandate; flagging for outer-orchestrator awareness only.

Other audit dimensions: no new SQL-injection vectors (LOAD path escapes quotes; macros interpolate fixed literals); no new error swallowing (`_age_with_uncertainty` logs-and-returns-None at a UDF boundary, consistent with null-propagation doctrine); no behavior-changing IG/model hardcoding (FHIR_VERSION_CODES is a spec-published value set with citation, appropriate as constants).

## Overall assessment

The CQL-21..22 + SOF-VD-01..03 delta is spec-grounded, well-tested (viewdef 860 unit + 144 conformance; DQM 47/47 green again), and the deployment invariant holds for both extensions (md5-matched repo/site-packages, binary newer than sources, expected campaign hash `c5b22d58`). The age-uncertainty family is functionally correct on the live native path (verified by execution). The one structural concern is REV-012: nine uncertainty UDFs duplicated across Python and C++ with already-divergent parse strictness, only one side tested — the same accretion dynamic flagged in REV-010, now at the UDF layer.

**Exit recommendation:** CLEAN (milestone review complete; open items REV-002/003/005/009/010/011/012/013 are tracked debt; none block the next pipeline step).
