# Architect Handoff — SOF-VD-07, iteration 1 (SKEPTIC)

## Golden Standard (slice invariants)
See `/mnt/d/fhir4ds/.temp/architect/golden_standard.md` (7 invariants: array-form parser validation, any-depth recursive union traversal with termination, per-node focus for columns/where/%rowIndex/nested select, dual-engine parity, no global-state leaks, no fixture-specific branching, graceful degradation never SIGSEGV).

## Audit findings
- **Invariant 7 violation (QA-001, fixed this iteration)**: the recursion-budget mechanism violated the graceful-degradation invariant (process crash). Fix restores the invariant and strengthens it for ALL FHIRPath UDFs, not just repeat — general, not test-specific. No fixture-specific or resource-type branching exists in repeat runtime paths (invariants 1-6 hold).
- Fix quality: `_run_with_recursion_budget` restores both `sys.setrecursionlimit` and `threading.stack_size` (invariant 5); regression test asserts interpreter-state restoration explicitly. Inline fast paths are byte-identical to the previous behavior for small budgets — no blast radius on ordinary resources.
- Residual (accepted, documented): beyond ~10k depth, repeat is memory/time-bound by inherent O(n²) serialized-subtree output (each repeated node carries its subtree JSON); native and fallback share this; not architectural debt, it is the data model the spec implies (node-as-context).
- Pre-existing, out of scope, flagged to outer orchestrator: 7 fhirpath duckdb pytest parity failures (temporal-quantity edges, replaceMatches named groups) — the working tree's C++ sources are ahead of the deployed Aug-19 fhirpath.duckdb_extension binary (which register_fhirpath cannot load under this env's unsigned-extension policy).

## QA Enforcer Gate
QA (SKEPTIC) was NOT lazy: all 19 official repeat fixtures run through the real parse→generate→DuckDB pipeline with the official-runner SQL adaptation; probed union dedup (incl. overlapping paths), ordering, %rowIndex, where, parser cardinality/mutual-exclusion, duplicate siblings, cycle-equivalent deep nesting on BOTH engines (native exercised via allow_unsigned_extensions LOAD). Root-caused the one real bug to the C-stack mechanism with a faulthandler-pinned reproducer. **No RETRY_QA.**

## Compressed handoff
Iteration 1: 4 issues (1 MEDIUM fixed+verified — Python-fallback recursion-budget segfault on ~14k-deep JSON, fixed generally via stack-sized worker thread with clean RecursionError degradation; 3 LOW INTENDED doctrine pins: value-based union dedup, unpinned row order, dict-only collection). Gates fresh: viewdef pytest 1186/1186 (new regression test included), ViewDef conformance 144/144, master run_all 2832/2832; extension md5 57d0634b6ee6eddee9fc06a1355bef5a repo==site-packages unchanged.

## Recommended fix order
None remaining for this chunk. Chunk SOF-VD-07 is CLEAN; zero non-terminal CRITICAL/HIGH/MEDIUM issues at iteration 1 (≥ min_iterations).
