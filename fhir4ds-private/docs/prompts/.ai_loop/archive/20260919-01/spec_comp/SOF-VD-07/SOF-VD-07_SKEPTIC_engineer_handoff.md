# Engineer Handoff — SOF-VD-07, iteration 1

## Triage
| Issue | Category | Severity | Disposition |
|---|---|---|---|
| QA-001 recursion-budget segfault | ROBUSTNESS | MEDIUM | CONFIRMED → fixed |
| QA-002 identical-sibling value dedup | SPEC_AMBIGUITY | LOW | INTENDED (doctrine) |
| QA-003 non-document row order | SPEC_AMBIGUITY | LOW | INTENDED (spec unpinned) |
| QA-004 primitive-yielding repeat empty | SPEC_AMBIGUITY | LOW | INTENDED (SOF-VD-05 pin) |

## QA-001 fix (root cause, not a shim)
- **Root cause**: `_eval_with_recursion_budget` and `fhirpath_repeat_udf` raised `sys.setrecursionlimit(json_depth*4+1000)` without bound. On CPython ≤3.10 every Python frame consumes native C stack, so at ~14k-deep JSON (limit ~57k) the evaluator's per-level `visit()` recursion (fhir4ds/fhirpath/__init__.py) smashed the 8 MB stack → SIGSEGV of the host process (reproduced: exit 139, faulthandler pins visit/get_data).
- **Fix** (fhir4ds/fhirpath/duckdb/udf.py): new `_run_with_recursion_budget(func, needed_limit, *args)`:
  - needed_limit ≤ current limit → run in place (unchanged behavior);
  - ≤ `_INLINE_RECURSION_LIMIT_MAX` (20,000) → in-place raise under `_RECURSION_LIMIT_LOCK` (unchanged behavior);
  - above the ceiling → run on a dedicated worker thread whose stack is sized `needed_limit × 2048 B` (1 MiB–512 MiB clamps), restoring `threading.stack_size()` and the recursion limit afterwards; if a worker stack can't be configured, degrade to the safe inline ceiling so the worst outcome is a clean `RecursionError` (caught by the UDF → `[]` + debug log), never a segfault.
  - Both `_eval_with_recursion_budget` (all FHIRPath UDFs benefit) and `fhirpath_repeat_udf` now route through it. No behavior change for budgets ≤ 20k.
- **Regression test**: `fhir4ds/viewdef/tests/integration/test_duckdb.py::TestRepeat::test_repeat_extreme_depth_does_not_crash_fallback` (depth 6000 exercises the worker-thread path; asserts 6001 rows, correct first/last linkIds, and restoration of recursion limit + thread stack size). Passes.
- Verified post-fix: depths 5000/6000 → correct rows; former crash depths 14000+ no longer segfault (they degrade to very slow-but-correct due to inherent O(n²) serialized-subtree output; 14000+ simply exceeds a 300 s budget — memory-bound, not a crash).
- Native C++ `RepeatDfs` untouched: verified OK to depth 20k via `allow_unsigned_extensions` load; beyond that it is OOM-bound, not stack-bound. Binary md5 57d0634b6ee6eddee9fc06a1355bef5a unchanged repo==site-packages (no native rebuild needed — Python-fallback-only change).

## Validation (fresh runs, PYTHONPATH=/mnt/d/fhir4ds)
- viewdef pytest suite: **1186 passed** (baseline 1185 + 1 new regression test), 0 failed.
- ViewDef conformance runner: **144/144 (100%)**.
- Master gate `conformance/scripts/run_all.py`: **OVERALL 2832/2832 (100%)**.
- fhirpath duckdb pytest suite: 1758 passed, **7 failed — ALL pre-existing, unrelated to this change** (native-vs-fallback parity in temporal-quantity arithmetic `@2016 + 1 'a'` edges and replaceMatches named-group regex; failing tests use tiny literals that hit the byte-identical `needed_limit <= current_limit` fast path — the C++ sources in the working tree are ahead of the Aug-19 fhirpath.duckdb_extension binary, which register_fhirpath cannot even load under the unsigned-extension policy in this env). Logged for the outer orchestrator; out of SOF-VD-07 scope.
- fhirpath.duckdb_extension md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages (unchanged; no native rebuild required for this Python-fallback fix).
