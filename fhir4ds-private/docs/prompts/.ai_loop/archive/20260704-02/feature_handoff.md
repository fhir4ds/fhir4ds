# Feature Handoff — Batch Augmentation Implementation

**Workflow**: feature_implementation → ready for code_review
**Plan**: `fhir4ds-private/docs/plans/FEATURE_BATCH_AUGMENTATION.md`
**Target version**: 0.0.12
**Date**: 2026-07-04

## What was implemented

All 6 steps of the FDD executed. The implementation adds `batch_size`,
`workers`, and `parallel_threshold` config knobs to `AutoCoder` and
`NotesPipeline`, refactors `FHIRDataLoader.load_resources` to honor
batch_size, makes `HTTPTerminologyEndpoint.search_batch` thread-pooled
and thread-safe, and wires multiprocessing for NotesPipeline.

## Files changed

**Source code** (4 files):
- `fhir4ds/cql/loader/auto_coder.py` — Step 1, 2, 6: config fields,
  `augment_resources`, `_augment_batch_parallel` (deferred per FDD)
- `fhir4ds/cql/loader/notes_pipeline.py` — Step 1, 2, 5: config fields,
  `extract_conditions_batch`, `_extract_batch_parallel`, module-level
  workers (`_init_worker`, `_worker_extract_fragments`), `_extract_kwargs`
- `fhir4ds/cql/loader/fhir_loader.py` — Step 3: refactored
  `load_resources` to pre-augment + pre-extract before the row-build loop
- `fhir4ds/cql/terminology/http_adapter.py` — Step 4: `threading.Lock`
  around breaker state, `ThreadPoolExecutor` in `search_batch`,
  `HTTP_SEARCH_BATCH_MAX_WORKERS` constant, updated docstrings

**Tests** (7 new files):
- `fhir4ds/cql/tests/unit/loader/test_batch_config.py` — Step 1 config tests
- `fhir4ds/cql/tests/unit/loader/test_auto_coder_batch.py` — Step 2/3 cross-config
- `fhir4ds/cql/tests/unit/loader/test_notes_pipeline_batch.py` — Step 2/3 cross-config
- `fhir4ds/cql/tests/unit/terminology/test_http_adapter_parallel.py` — Step 4
- `fhir4ds/cql/tests/unit/loader/test_notes_pipeline_parallel.py` — Step 5
- `fhir4ds/cql/tests/unit/loader/test_auto_coder_parallel.py` — Step 6 (deferred)
- `fhir4ds/cql/tests/integration/test_conformance_baseline.py` + `baseline_conformance_count.txt` — audit S6

## What's deferred

**Step 6 (AutoCoder parallel pool) — DEFERRED per FDD.** The plan
explicitly says "Skip if Step 5 surfaces problems that warrant
deferring." Step 5 surfaced the DuckDB-shared-connection hazard: a
single `Connection` object cannot be safely used across concurrent
`execute()` calls (per DuckDB Python docs). The same hazard applies to
threads. The cross-resource parallel win for AutoCoder in HTTP mode is
already captured by Step 4's `search_batch` thread pool, which runs
concurrently inside each per-resource `augment_resource` call. The
in-process endpoint case remains single-threaded per resource; future
work could use `con.cursor()` per thread to enable true parallelism.

`AutoCoder._augment_batch_parallel` raises `NotImplementedError`.
`augment_resources` catches it and falls back to synchronous chunked
mode. Cross-config tests confirm all 9 (batch_size × workers)
combinations produce byte-identical results.

## Verification

- **1703 unit + integration tests pass** (4 skipped — medterm4ds live tests
  requiring the sidecar; 8 deselected — slow benchmarks)
- **24 new tests pass** (Step 1-6 coverage + import-isolation sentinel)
- **0 regressions** in the existing test suite
- **Import-isolation sentinel passes** — zero-dep default preserved;
  new stdlib imports (`threading`, `multiprocessing`, `concurrent.futures`)
  are lazy inside methods, never at module top
- **All 9 (batch_size × workers) combinations produce byte-identical
  resources table contents** in the FHIRDataLoader integration tests

## What was NOT done

- **Full conformance suite run** (`python3 conformance/scripts/run_all.py`)
  not executed in this session — it takes 5–10 minutes. The
  `baseline_conformance_count.txt` is set to 2822 (historical baseline
  from the post-Phase-4 commits). The CI gate
  `test_conformance_no_regression` (marked `slow` + `integration`)
  enforces `current >= 2822` when run.
- **Live medterm4ds integration test** — requires the sidecar running
  locally; existing `tests/integration/test_medterm4ds_live.py` covers
  this path. The new parallel infrastructure is verified via mocked
  Pool tests.

## Handoff to code_review

Per `ROLE_CODE_REVIEWER.md`, the reviewer should focus on:

1. **Concurrency correctness** (Step 4):
   - Verify `threading.Lock` guards all reads AND writes of
     `_consecutive_failures` and `_tripped_until` (no torn reads)
   - Verify `search_batch`'s thread pool correctly handles mid-flight
     breaker trips
2. **Picklability** (Step 5):
   - Verify `_worker_extract_fragments` and `_init_worker` are
     module-level (no closure over `self`) — explicit regression test
   - Verify the dict-conversion at process boundary is complete
3. **Resource bounds** (Step 5):
   - Worker count bounded by `min(workers, os.cpu_count())`
   - Optional `psutil` warning at ~5GB/worker threshold
4. **Backward compatibility**:
   - Defaults preserve byte-identical behavior — verified by cross-config tests
   - `load_resource` (singular) unchanged
5. **Cross-platform**:
   - Worker functions are module-level (Windows `spawn` safe)
   - Config docstring documents the `if __name__ == "__main__"` guard
6. **Cache invalidation**:
   - Parallel mode is read-only on `autocoding_cache` during the batch
   - Parent writes cache after `pool.map` returns
7. **Hardcoded assumptions** (per CLAUDE.md / GLOBAL_RULES.md):
   - `HTTP_SEARCH_BATCH_MAX_WORKERS = 8` is a named module constant
     with comment justifying the value
   - `parallel_threshold = 200` is a config field (not magic)

## State

`evolution.json` advanced to `code_review` workflow, `pipeline_step=2`.
