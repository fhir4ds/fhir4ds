# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Implement the **Batch Augmentation** feature per the plan at
`fhir4ds-private/docs/plans/batch-augmentation-plan.md`. This adds
`batch_size` and `workers` config knobs to `AutoCoder` and
`NotesPipeline`, enabling batch-aware augmentation and parallel
execution for Phase 2 (auto-coding) and Phase 4 (clinical notes NER)
of the medterm4ds integration.

The work covers **Steps 1–6** of the plan (foundational config +
batch methods + loader integration + parallel HTTP + multiprocessing
pools). **Step 7** (bumping defaults after one minor release of
stability) is deferred and explicitly out of scope for this cycle.

The feature is a performance optimization that preserves today's
behavior exactly when `batch_size=1, workers=1` (the defaults). No
public API breaks.

## Target Version

0.0.12

## Pipeline

1. feature_design
2. feature_implementation
3. code_review

Single cycle. The plan doc already covers the design work; the
feature_design step validates the plan against the current codebase,
refines into an FDD, and performs an architecture self-audit.

## Feature Design Gate

The feature_design step should:
- Use the existing plan at `fhir4ds-private/docs/plans/batch-augmentation-plan.md`
  as the starting point (do NOT redesign from scratch)
- Validate the plan against the current codebase (integration points
  may have shifted during the post-Phase-4 commits: the circuit
  breaker, the health probe, the parser fix all touched adapter code)
- Refine into a Feature Design Document (FDD) with concrete file-level
  implementation tasks for Steps 1–6
- Architecture self-audit using ROLE_ARCHITECT.md standards
- Specifically audit:
  - Multiprocessing picklability of medterm4ds result types
  - Circuit breaker behavior under concurrent access (thread safety)
  - Worker memory bounds on resource-constrained machines
  - Cross-platform multiprocessing semantics (Windows spawn vs POSIX fork)
- Hand off the refined FDD to the feature_implementation step

## Feature Implementation Gate

The feature_implementation step should execute Steps 1–6 of the plan
in sequence. Each step is independently shippable but should land in
this cycle:

- **Step 1**: Add `batch_size: int = 1` and `workers: int = 1` to
  `AutoCoderConfig` and `NotesPipelineConfig`. Zero behavior change.
- **Step 2**: Add `augment_resources(list[dict])` to AutoCoder and
  `extract_conditions_batch(list[dict])` to NotesPipeline. Both
  delegate to per-resource methods when `batch_size=1`. Additive only.
- **Step 3**: Add `FHIRDataLoader.load_resources(iterable)`. Refactor
  `load_ndjson` and `load_directory` to use it internally.
  `load_resource` (singular) preserves today's behavior.
- **Step 4**: Refactor `HTTPTerminologyEndpoint.search_batch` from
  sequential loop to concurrent `ThreadPoolExecutor`. Integrate with
  the existing circuit breaker (shared failure counter under lock).
- **Step 5**: Multiprocessing pool for NotesPipeline. Add
  picklability verification for `ExtractedConcept`. Add the
  "small batch → sync" heuristic (`if len(texts) < 200: sync`).
- **Step 6**: Multiprocessing pool for AutoCoder (optional, lighter
  per-worker memory than Step 5).

Implementation must:
- Write code following existing fhir4ds patterns (see AGENTS.md)
- Add unit tests for every new method and config combination
- Add cross-config correctness tests: every test runs with
  `batch_size ∈ {1, 10, 500}` × `workers ∈ {1, 2, 4}` — all
  combinations must produce identical resources table contents
- Verify `python3 conformance/scripts/run_all.py` still passes
  2822/2822 (no regression to existing spec compliance)
- Verify `python3 -c "import fhir4ds"` still succeeds with no
  optional deps installed (zero-dep default preserved)

## Code Review Gate

After implementation:

- Review the diff for correctness, test coverage, and architectural
  alignment
- **Specific audit dimensions**:
  - **Concurrency correctness**: thread safety of circuit breaker
    under parallel HTTP; process safety of multiprocessing pool
  - **Picklability**: verify ExtractedConcept and SearchResult survive
    `pickle.dumps()`/`pickle.loads()` round-trip across process
    boundaries
  - **Resource bounds**: worker count auto-limiting on memory-
    constrained machines; no unbounded thread/process pools
  - **Backward compatibility**: every existing test passes unchanged
    with default config; `batch_size=1, workers=1` produces byte-
    identical results to pre-feature behavior
  - **Cross-platform**: multiprocessing works on Windows (spawn) and
    POSIX (fork); documented if a worker startup cost is unavoidable
  - **Cache invalidation**: autocoding_cache and any Phase 4 cache
    remain correct under batch and parallel execution
- Verify zero-dependency default: `fhir4ds` core imports and runs
  without `medterm4ds`, `httpx`, `medspacy`, `spacy`, or `torch`
- Check for hardcoded assumptions (per CLAUDE.md / GLOBAL_RULES.md)
- Run full conformance suite as regression check (2822/2822 must hold)

## Step Definitions

### Step 1: Config knobs (no behavior change)

- Add `batch_size: int = 1` and `workers: int = 1` to `AutoCoderConfig`
  and `NotesPipelineConfig`
- Update docstrings with the execution-strategy matrix
- No changes to augmentation methods yet
- Tests: defaults preserve current behavior

### Step 2: Batch-aware augmentation methods

- Add `augment_resources(resources: list[dict])` to AutoCoder
- Add `extract_conditions_batch(resources: list[dict])` to NotesPipeline
- Both internally loop with `batch_size` chunks; `batch_size=1`
  delegates to existing per-resource methods
- Existing per-resource methods unchanged
- Tests: batch methods produce identical results to per-resource for
  any `batch_size`

### Step 3: FHIRDataLoader integration

- Add `load_resources(iterable)` method
- Refactor `load_ndjson` and `load_directory` to use it internally
- `load_resource` (singular) preserves today's per-resource behavior
- Tests: `load_ndjson` with `batch_size=500` produces identical
  resources table to `batch_size=1`

### Step 4: Parallel HTTP in `search_batch`

- Refactor `HTTPTerminologyEndpoint.search_batch` to use
  `ThreadPoolExecutor` for >1 queries
- Integrate with circuit breaker (shared failure counter under lock)
- Tests: parallel mode produces same results as sequential; breaker
  still trips correctly under concurrent failures

### Step 5: Multiprocessing pool for NotesPipeline

- Implement `_extract_batch_parallel` per the plan
- Add picklability verification for `ExtractedConcept` (or convert to
  dicts at process boundary)
- Add the "small batch → sync" heuristic (`len(texts) < 200`)
- Tests: parallel mode produces same results as sequential; worker
  count respected; engine loaded per worker

### Step 6: Multiprocessing pool for AutoCoder (optional)

- Same pattern as Step 5, lighter per-worker memory
- Lower priority (Phase 2 is less CPU-bound than Phase 4)
- Skip if Step 5 surfaces problems that warrant deferring

## Focus Areas

- **Zero-dependency default**: `fhir4ds` core imports and runs without
  `medterm4ds`, `httpx`, `medspacy`, `spacy`, or `torch` installed.
  Verified by `tests/unit/test_import_isolation.py` sentinel.
- **Backward compatibility**: every existing test passes unchanged
  with default config. `batch_size=1, workers=1` produces byte-
  identical results to today's behavior.
- **Conformance baseline**: 2822/2822 maintained throughout. No spec
  regressions allowed.
- **Cross-config correctness**: every batch/parallel test runs with
  multiple `batch_size` × `workers` combinations. All produce
  identical results.
- **Concurrency safety**: circuit breaker remains correct under
  parallel HTTP access (shared mutable state needs lock).
  Multiprocessing pool doesn't corrupt shared DuckDB connections.
- **Cross-platform**: Windows uses `spawn` for multiprocessing;
  workers must handle re-importing modules cleanly. Document any
  `if __name__ == "__main__"` guard requirements.
- **Resource bounds**: worker count auto-limited by available memory.
  Document the ~5GB per worker cost for Phase 4 (medspaCy + SapBERT).
- **Picklability**: medterm4ds result types (`ExtractedConcept`,
  `SearchResult`) must cross process boundaries. Verify with explicit
  pickle round-trip tests.
- **Performance benchmark**: include a benchmarks test (skipped in CI,
  run manually) that demonstrates the speedup for each config
  combination vs the `batch_size=1, workers=1` baseline.
