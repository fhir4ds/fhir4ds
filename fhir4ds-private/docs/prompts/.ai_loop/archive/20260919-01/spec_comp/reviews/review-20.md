# Code Review Findings — Spec-Compliance Campaign Milestone #4 (FP-16..FP-20) + Parity Drift Investigation

**Date:** 2026-08-19
**Reviewer:** Code Reviewer role (milestone `code_review` workflow, fourth launch)
**Scope Part A:** Uncommitted working-tree diff vs `db1e4164` (dev), delta since milestone #3 (review-15.md): FP-16..FP-20 fixes (operators.py error contracts, native Time-arith rendering, exact int64 div/mod + Decimal mod, INT32/INT64 literal enforcement, unary-minus overflow doctrine, native incompatible-operand arithmetic throw, mixed-unit granularity selection, Meta.profile/source uri-family typing + native is() subtype chain, %context docstrings, new parity/regression test files). Grammar untouched this period (verified: `FHIRPath.g4` diff only carries the pre-existing FP-10 non-greedy STRING change).
**Scope Part B (special directive):** classify the ~160–183 pre-existing integration parity failures (FP-18 QA-007, FP-19 QA-003, FP-20 SKEPTIC QA-005 / HISTORIAN QA-004).

## Part A — Milestone review

### Status of prior findings (REV-001..REV-005)

- **REV-001 (LOW, unguarded `std::stoi` in `fhirpathSplitUnitTerm`)** — STILL OPEN. `evaluator.cpp:2151-2172`: a composed unit term ending in `-` (e.g. `x-`) still reaches `std::stoi("-")`. Not literal-reachable; hardening only.
- **REV-002 (MEDIUM, hand-maintained metadata duplicated across engines)** — STILL OPEN. Confirmed present and aligned this milestone: `fhirFieldType` profile→canonical / source→uri entries landed in native table AND `fhir_path_to_type.json` (lockstep comment present); `typecheck.py`/`nodes.py` mirrors remain. Structural drift risk unchanged.
- **REV-003 (LOW, unrelated untracked files in the campaign tree)** — STILL OPEN. `conformance/architecture/`, `fhir4ds/dqm/AGENTS.md`, `fhir4ds/cql/tests/unit/loader/test_iter{4,6}_qa_regression.py` still present alongside legitimate campaign files (`functions/navigation.py` verified present).
- **REV-004 (LOW, `__int128` overflow budget in exact decimal helpers)** — MOOT-ISH / STILL OPEN by record: the guarded helpers are currently ABSENT from the working tree (see Part B, bucket b); the finding re-applies whenever they are re-landed.
- **REV-005 (LOW, mid-pattern inline regex flags deprecation)** — STILL OPEN. `_compile_regex` (`fhir4ds/fhirpath/engine/invocations/strings.py`) still passes patterns verbatim to `re.compile`.

### New findings

- **REV-006 (HIGH, OPEN) — FP-16 SKEPTIC fix LOST from `operators.py`.** `fhir4ds/fhirpath/duckdb/operators.py::membership()` (lines 572-574) again returns `FHIRPathCollection([])` on a multi-item singleton operand instead of raising `FHIRPathError("in requires the left operand to contain at most one item")` (§6.4.2/§6.4.3). The engine messages exist (`engine/invocations/collections.py:354,365`) and the regression test exists (`test_collection_operator_parity.py::test_membership_helper_singleton_violations_raise_fhirpath_error`) — confirmed FAILING ("DID NOT RAISE"). File mtime Aug 18 13:46 vs test mtime Aug 18 11:50: the fixed file was overwritten after the fix landed. 13th instance of the "exported helper API forgotten"/silent-`return {}` family, here via clobber rather than omission.
- **REV-007 (MEDIUM, OPEN, umbrella of Part B bucket b) — sibling-session whole-file clobbering of `evaluator.cpp`.** Multiple verified source fixes documented in milestone #3 review and chunk handoffs are absent from the current working tree even though their tests survive: `powerDecimalExactText`/`powerDecimalGuarded28Text`/`expandScientificToFixed`/`shortestRoundTripText`/`leastPrecisionDecimalPlaces`/`frac_digits` (FP-11/FP-13), the `!explicit_namespace` guard on the literal-Quantity `isType` branch (FP-15; current line 10087 lacks it), and the `extension`/`modifierExtension`→Extension entries in `fhirFieldType` (FP-12). See Part B.

### Verified correct in the FP-16..FP-20 delta (non-findings)

- **%context docstrings** (`duckdb/context.py:32,246`, `duckdb/evaluator.py:919`) correctly state %context is the ORIGINAL node; locked by `test_environment_context_semantics_fp20.py` (passes).
- **Meta.profile/source typing** landed in lockstep (native `fhirFieldType` FP-20 HISTORIAN QA-001 comment + `fhir_path_to_type.json` entries); `test_uri_type_reflection_parity_fp20.py` 81/81 passes together with FP-18/FP-20 unit suites.
- **FP-18 unit suite** (`test_fp18_math_operators.py`) green.
- **Grammar untouched** this period; no SQL-injection vectors or error-swallowing introduced in the Python delta reviewed.

## Part B — Parity drift investigation (special directive)

### Method

Ran the full `fhir4ds/fhirpath/duckdb/tests/integration/` directory twice against the CURRENT tree (binary `fhirpath.duckdb_extension` Aug 19 00:53, md5-matched to the site-packages deploy; `evaluator.cpp` Aug 19 00:45 — binary is fresh vs source). Result: **75 failed / 697 passed** (was 183 at FP-18 SKEPTIC, 86-172 at intermediate launches). Sampled each failure class with `--tb=line`. Symbol-audited `evaluator.cpp` (contains a benign NUL byte inside a comment → grep needs `-a`).

### Classification (75 current failures)

| Bucket | Count | Evidence |
|---|---|---|
| (a) stale-binary — ALREADY FIXED by the Aug 19 rebuilds | ~108 (of the historical 183; 0 current) | 183 → 75 after FP-19/FP-20 rebuilds; `FhirpathDerivedUnitTable` and `structuralFHIRComplexType` are now present in source AND binary (`1 'kN' = 1000 'N'` family now passes). The committed HEAD binary (394 KB source era) was the stale artifact. |
| (b) LOST SOURCE FIXES (binary correctly reflects source; source was clobbered) | **67** | comparison 37 (`leastPrecisionDecimalPlaces` absent — `1.0 ~ 1.0001` native false); power_math 16 + math_parity 5 (`2.power(3)` native `'8.0'` vs expected `'8'` — exact int64/Decimal power helpers absent); type_parity 3 (`5 'mg' is FHIR.Quantity` native true — namespace guard lost at evaluator.cpp:10087); tree_utility 3 (`extension.type().name` native `object` — `extension` entry missing from `fhirFieldType`); collection 1 (REV-006, membership raise); aggregate_lexical 1 (`(1+'x')|99` native `['99']` vs fallback `[]` — passed at FP-19 close, now regressed); fp08 1 (native double rendering vs 28-digit exact — FP-11 family). |
| (c) wrong test expectation / known native limitation | ~2 | string_transform 2: `replaceMatches` named-group `$1` references (std::regex has no named captures) and regex anchor flag parity — pinned by tests but structurally unreachable with std::regex; needs explicit xfail-with-reason or the RE2 migration. |
| (d) untriaged (test-expectation vs engine-gap, per-case) | 6 | arithmetic 5 temporal edges (`@2016-01 + 1 'mo'`, `@T12 + 1 day`, `@1974-12-25 - 1 'cm'` — FALLBACK-side expectation mismatches, not native parity) + equality 1 (string equivalence case/whitespace parity diff). |
| (e) test-environment artifact (races/PYTHONPATH) | 0 currently | binary == site-packages deploy (md5 match), binary newer than source. But the race MECHANISM is the root cause of bucket (b) — see below. |

### Root cause

**Sibling campaign sessions concurrently editing the same working tree with whole-file overwrites (last-writer-wins).** Timeline evidence: FP-16 fix landed ~Aug 18 11:50 (test mtime) but `operators.py` was overwritten Aug 18 13:46 without it; `evaluator.cpp` was rewritten through Aug 19 00:45 (FP-19/FP-20 chunks) without the FP-11/FP-12/FP-13/FP-15 sections that milestone review #3 verified present on Aug 18. FP-20 HISTORIAN already documented a mid-run overwrite + `.git/index.lock` deadlock. Each session apparently holds a stale in-memory copy of the big files and rewrites them wholesale, silently dropping other sessions' hunks. The "stale binary" theory explains only bucket (a); the rebuild then compiled a clobbered source, producing a fresh-but-deficient binary whose failure signature looked like "tests expect native semantics absent from source" (FP-18 QA-007's `expandScientificToFixed` observation).

### Reconciliation plan (ordered; NOT applied — classify/plan only)

1. **Freeze concurrency**: no sibling launches touch the tree until steps 2-4 complete; acquire a single-writer lock (or move each launch to its own git worktree).
2. **Re-land lost source fixes** from the chunk handoffs (tests already define done): FP-11 exact power/sqrt/decimal-text helpers, FP-13 `leastPrecisionDecimalPlaces` at both quantity-equivalence sites, FP-15 `!explicit_namespace` guard on the literal-Quantity `isType` branch, FP-12 `extension`/`modifierExtension` `fhirFieldType` entries, FP-19 error-abort-through-`|` propagation, FP-16 `operators.py::membership/contains` raise (REV-006). Expected: 67 failures → 0.
3. **Rebuild + redeploy** the extension to repo bundle and site-packages; rerun the integration directory (expect 75 → ~8) plus the conformance master gate (2832/2832 must hold).
4. **Triage the remainder**: mark the 2 std::regex named-group cases explicit xfail (or schedule RE2); resolve the 6 untriaged (5 temporal-edge fallback expectations vs doctrine registry, 1 string-equivalence parity) case-by-case as test-fix or engine-fix.
5. **Add a clobber guard**: post-edit/post-build symbol check (e.g. grep for `powerDecimalExactText`, `leastPrecisionDecimalPlaces`, the isType namespace guard, `extension` field entry; plus a membership-raise unit test in the pre-commit set) so any future overwrite fails loudly instead of drifting.

## Overall assessment

**The campaign's chunk work is spec-sound, but the working tree is currently NOT a superset of the campaign's fixes.** 67 of 75 remaining parity failures are re-landable lost fixes caused by sibling-session file clobbering, not by wrong doctrine or wrong tests. The FP-16..FP-20 delta itself is clean except REV-006 (the lost FP-16 helper fix). Block the next C++-touching chunk and the commit until the reconciliation plan steps 1-3 run.
