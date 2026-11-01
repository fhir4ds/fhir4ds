# FEATURE_PLAN_DRAFT (v1) — Batch Augmentation

> Draft Feature Design Document. Source plan:
> `fhir4ds-private/docs/plans/batch-augmentation-plan.md`. Will be
> refined after architecture self-audit into
> `fhir4ds-private/docs/plans/FEATURE_BATCH_AUGMENTATION.md`.

## Objective

Add `batch_size` and `workers` config knobs to `AutoCoder` and
`NotesPipeline`, enabling batch-aware augmentation and parallel
execution for Phase 2 (auto-coding) and Phase 4 (clinical notes NER)
of the medterm4ds integration. Covers Steps 1–6 of the source plan.
Step 7 (default bumps) is deferred.

Defaults preserve today's behavior exactly:
`batch_size=1, workers=1` is byte-identical to the pre-feature code
path. No public API breaks.

## Spec Alignment

- **FHIR R4**: $search on CodeSystem, $expand on ValueSet — unchanged.
  The internal execution strategy is invisible to FHIR semantics.
- **fhir4ds invariants** (verified against current code):
  - `INV-1`: Phase 2 hook skipped when `self._auto_coder is None`
    (`fhir_loader.py:371`)
  - `INV-3`: Phase 4 `extract_conditions` never raises
    (`fhir_loader.py:394–416`)
  - `INV-6`: Every `httpx.Client` constructed with explicit finite
    `timeout=self._timeout` (`http_adapter.py:9–12, 213–222`)
  - Zero-dep default: top-level fhir4ds imports succeed without
    `httpx`, `medterm4ds`, `medspacy`, `spacy`, `torch` (verified by
    `tests/unit/test_import_isolation.py`).

## Codebase Reality (verified, supersedes plan where stale)

| Plan claim | Reality | FDD implication |
|---|---|---|
| Step 3 "Add `load_resources`" | **Already exists** at `fhir_loader.py:334` | Step 3 reduced to: add chunked batch calls + thread lock around breaker |
| `AutoCoderConfig`/`NotesPipelineConfig` are mutable dataclasses | **Both are `frozen=True`** (`auto_coder.py:93`, `notes_pipeline.py:73`) | Preserve `frozen=True`; additive fields only |
| Circuit breaker "needs lock under concurrent access" | **Already documented as single-threaded only** at `http_adapter.py:14–22, 127–130, 152–154` | Step 4 *must* add `threading.Lock`; document thread-safety upgrade |
| "2822/2822 maintained" | `conformance/scripts/run_all.py` computes `grand_passed` dynamically (no literal "2822" in test) | Replaced with "no regression in `grand_passed` vs. baseline" + pinned baseline in test |
| medspaCy/SapBERT loading | Owned entirely by medterm4ds behind `medterm4ds.connect()` / `medterm4ds.extract()` | Worker init just calls `medterm4ds.connect()`; no fhir4ds-side lazy-load changes |
| `ExtractedConcept` picklability | medterm4ds-owned type; existing `_safe_getattr` (`notes_pipeline.py:414`) already tolerates dict-or-dataclass | Worker boundary converts to dicts (defensive); add explicit pickle round-trip test |

## Architecture

```
                          ┌─────────────────────────────────────┐
                          │     FHIRDataLoader.load_resources    │
                          │       (fhir_loader.py:334)           │
                          └───────────────┬─────────────────────┘
                                          │ chunked by batch_size
                          ┌───────────────▼─────────────────────┐
                          │  AutoCoder.augment_resources         │
                          │   (NEW; Step 2)                     │
                          │   ├─ batch_size=1 → augment_resource │
                          │   ├─ batch_size=N, workers=1 → sync  │
                          │   └─ batch_size=N, workers=M → pool  │
                          └───────────────┬─────────────────────┘
                                          │ per-text queries
                          ┌───────────────▼─────────────────────┐
                          │ HTTPTerminologyEndpoint.search_batch │
                          │   (REFACTORED; Step 4)              │
                          │   ThreadPoolExecutor + lock-guarded  │
                          │   circuit breaker                    │
                          └─────────────────────────────────────┘

                          ┌─────────────────────────────────────┐
                          │ NotesPipeline.extract_conditions_batch│
                          │   (NEW; Step 2)                     │
                          │   ├─ batch_size=1 → extract_conditions│
                          │   ├─ len(texts)<200 OR workers=1     │
                          │   │  → sync chunked loop             │
                          │   └─ else → multiprocessing.Pool     │
                          │      (Step 5) with dict boundary     │
                          └─────────────────────────────────────┘
```

The "current approach" and "batch approach" are not different modes —
they are points on the same `batch_size × workers` parameter space.
`batch_size=1, workers=1` IS today's per-resource mode.

## Implementation Plan (file-level)

### Step 1 — Config knobs (zero behavior change)

**Files**:
- `fhir4ds/cql/loader/auto_coder.py:93–143` — add two fields to `AutoCoderConfig`
- `fhir4ds/cql/loader/notes_pipeline.py:73–111` — add two fields to `NotesPipelineConfig`

**Changes**:
```python
@dataclass(frozen=True)
class AutoCoderConfig:
    # ... existing fields unchanged ...
    batch_size: int = 1
    workers: int = 1
```
Same for `NotesPipelineConfig`. Update docstrings with the execution-strategy matrix.

**Tests** (extend `tests/unit/loader/test_auto_coder.py` and `test_notes_pipeline.py`):
- Defaults preserve current behavior — `AutoCoderConfig().batch_size == 1`
- Frozen — `dataclasses.replace(cfg, batch_size=10)` works, direct assignment raises `FrozenInstanceError`
- Construct with `batch_size=500, workers=4` succeeds

**Risk**: zero. **Effort**: 1 hour.

### Step 2 — Batch-aware augmentation methods

**Files**:
- `fhir4ds/cql/loader/auto_coder.py` — add `AutoCoder.augment_resources(resources: list[dict]) -> None`
- `fhir4ds/cql/loader/notes_pipeline.py` — add `NotesPipeline.extract_conditions_batch(resources: list[dict]) -> list[list[dict]]`

**Behavior contract**:
- `batch_size=1`: delegate to existing per-resource method (identical code path)
- `batch_size>1, workers=1`: chunk list, loop calling existing per-resource method per chunk
- `batch_size>1, workers>1`: Step 5/6 dispatch (initially: same as workers=1; pool wired in Step 5/6)

**Crucial invariant**: batch methods must produce *byte-identical* resource output to per-resource for any `batch_size`. Mutates resources in place (matching `augment_resource` semantics).

**Tests**:
- Per-resource and batch methods produce identical Coding attachments for `batch_size ∈ {1, 10, 500}`
- Same derived Conditions from `extract_conditions_batch` (id determinism via existing hash)
- Same `autocoding_cache` table state across batch sizes

**Risk**: low — additive. **Effort**: half day.

### Step 3 — FHIRDataLoader chunked-batch integration

**Files**:
- `fhir4ds/cql/loader/fhir_loader.py:334–460` (existing `load_resources`) — switch the per-resource augmentation hook at L371–372 and the per-resource derived-Conditions hook at L394–416 to call the batch-aware methods when `batch_size > 1`.

**Reality**: `load_resources` already exists and already delegates from `load_ndjson` (L553) and `load_directory` (L596). Step 3 is **not** additive — it's a surgical refactor of the two hooks inside `load_resources` to honor `batch_size`.

**Approach**:
1. Read `self._auto_coder._config.batch_size` (default 1) and chunk the input list before the row-build loop.
2. For each chunk: call `self._auto_coder.augment_resources(chunk)` once instead of `augment_resource(resource)` N times.
3. Same shape for `extract_conditions_batch` on each chunk.
4. Preserve `INV-1` (skip when `self._auto_coder is None`) and `INV-3` (extract never raises).

**Tests** (extend `tests/unit/loader/test_fhir_loader_integration.py`):
- `load_ndjson` with `auto_coder.batch_size=500` produces identical `resources` table to `batch_size=1` (same row count, same JSON byte content modulo deterministic ordering)
- Conformance regression check via `conformance/scripts/run_all.py` — assert `grand_passed` is unchanged vs. baseline (no literal "2822")

**Risk**: medium — touches the loader's main code path. **Effort**: half day.

### Step 4 — Parallel HTTP in `search_batch`

**Files**:
- `fhir4ds/cql/terminology/http_adapter.py:14–22, 127–130, 152–154, 178–193, 423–442`

**Changes**:
1. Add `self._lock = threading.Lock()` in `__init__`.
2. Wrap `_consecutive_failures` and `_tripped_until` reads/mutations in `_is_breaker_open`, `_on_call_success`, `_on_call_failure` with `with self._lock:`.
3. Update the class docstring (L127–130) and module docstring (L14–22) from "NOT thread-safe" → "Thread-safe under a single-instance lock; safe for use by `search_batch`'s internal thread pool".
4. Refactor `search_batch` (L423–442):
   - `len(queries) <= 1` OR breaker open → sequential (today's behavior)
   - else → `ThreadPoolExecutor(max_workers=min(8, len(queries)))`, submit one `search_text` per query, gather futures
   - Each thread's failure updates the shared counter under the lock; if breaker trips mid-flight, remaining futures still execute (they were already submitted) but their results are dropped if breaker is open at result-collection time
5. Preserve `INV-6`: each `search_text` constructs its own `httpx.Client(timeout=...)` (no shared client state)

**Tests** (extend `tests/unit/terminology/test_http_adapter.py`):
- Parallel mode produces same results as sequential for `len(queries) ∈ {2, 8, 50}`
- Breaker trips correctly under concurrent failures: simulate 5 simultaneous failures, verify `_consecutive_failures == 5` (not a torn count)
- Breaker open at submission → fast-returns `[]` for all queries
- Thread-safety smoke test: 100 threads call `search_text` concurrently on a flaky mock; assert no `RuntimeError`, counter ends at correct value

**Risk**: low — internal optimization. **Effort**: half day.

### Step 5 — Multiprocessing pool for NotesPipeline

**Files**:
- `fhir4ds/cql/loader/notes_pipeline.py:195` (existing `extract_conditions`) and new `_extract_batch_parallel`

**Approach**:
1. Add `_extract_batch_parallel(self, texts: list[str]) -> list[list[dict]]` per the plan §187–212.
2. Worker init: `def _init_worker(): global _engine; import medterm4ds; _engine = medterm4ds.connect()`.
3. Worker function: convert medterm4ds result (`ExtractedConcept` or list thereof) **to plain dicts at the process boundary** before returning. This sidesteps the picklability unknowns of the medterm4ds-owned `ExtractedConcept` type — same defensive pattern as the existing `_safe_getattr` (`notes_pipeline.py:414`).
4. Add the "small batch → sync" heuristic: `if len(texts) < 200 or self._config.workers == 1: return self._extract_chunked_sync(texts)`.
5. `extract_conditions_batch` (from Step 2) routes to `_extract_batch_parallel` when `workers > 1` and the heuristic permits.

**Worker count bounding**:
- `actual_workers = max(1, min(self._config.workers, os.cpu_count() or 1))`
- **Memory auto-limit (NEW, not in plan)**: if `psutil` is available (optional dep), warn (not fail) when `workers * 5GB > available_virtual_memory`. Document the ~5GB/worker cost in the `NotesPipelineConfig.workers` docstring. Do NOT make this a hard gate — `psutil` is not a fhir4ds dependency.

**Cross-platform handling**:
- Windows uses `spawn`; workers re-import `medterm4ds`. Document any `if __name__ == "__main__"` guard requirement in user code (fhir4ds cannot enforce this).
- Linux/macOS use `fork`; the existing module-level state at `fhir_loader.py:32–34` (`_CACHE_LOCK`, `_VALUESET_UDF_CACHE_BY_CONNECTION`, `_VALUESET_UDF_REGISTERED_CONNECTIONS`) is inherited but DuckDB connections are not fork-safe — workers must construct their own connection via `medterm4ds.connect()` (which they do; the engine owns its connection).

**Tests** (new file `tests/unit/loader/test_notes_pipeline_parallel.py`, gated by `pytest.mark.slow`):
- Parallel mode produces same Conditions (same ids via deterministic hash) as sequential for `len(texts) ∈ {200, 500}`
- Worker count respected: `workers=2`, `len(texts)=200` → at most 2 worker processes spawned (verified via mock)
- Engine loaded per worker: each worker process logs "medterm4ds engine initialized" exactly once (assertion via worker-init side-effect mock)
- Pickle round-trip test: explicitly `pickle.dumps()` and `pickle.loads()` a sample `dict` produced by the worker function (post-boundary conversion)
- Cross-config matrix: `batch_size ∈ {1, 10, 500}` × `workers ∈ {1, 2, 4}` — all 9 combinations produce identical Conditions (modulo Condition id determinism)
- Small-batch heuristic: `len(texts) < 200` always uses sync path regardless of `workers`

**Risk**: medium — multiprocessing has subtle failure modes. **Effort**: 1 day.

### Step 6 — Multiprocessing pool for AutoCoder (optional, lighter)

**Files**:
- `fhir4ds/cql/loader/auto_coder.py:192` (existing `augment_resource`) and new `_augment_batch_parallel`

**Approach**: same pattern as Step 5, lighter per-worker memory (no medspaCy in workers — just SapBERT queries via `endpoint.search_text`). For HTTP mode, the Step 4 thread-pool already captures most of the win; Step 6 is for in-process endpoint mode.

**Tests** (new file `tests/unit/loader/test_auto_coder_parallel.py`, gated by `pytest.mark.slow`):
- Mirror Step 5's test matrix
- Cross-config correctness: `batch_size ∈ {1, 10, 500}` × `workers ∈ {1, 2, 4}` — identical Coding attachments
- Defer the test if medterm4ds is not installed (consistent with `tests/integration/test_medterm4ds_live.py`'s `pytest.importorskip` pattern)

**Risk**: low (proven pattern from Step 5). **Effort**: half day.

## Test Strategy

### Correctness invariants (cross-config matrix)

For every test, run with `batch_size ∈ {1, 10, 500}` × `workers ∈ {1, 2, 4}` — all 9 combinations must produce **identical resources table contents** (modulo Condition id determinism via the existing hash).

- Same Coding attachments on augmented CodeableConcepts
- Same derived Conditions from `extract_conditions_batch` (same ids)
- Same `autocoding_cache` table state
- Conformance: no regression in `grand_passed` vs. baseline

### Performance benchmarks (manual, skipped in CI)

New file `tests/benchmarks/test_batch_augmentation.py` (gated by `pytest.mark.benchmark`):
- 100-resource load with `batch_size=1, workers=1` (baseline)
- 100-resource load with `batch_size=100, workers=1` (batch win)
- 100-resource load with `batch_size=25, workers=4` (parallel win)

### Failure-mode tests

- One resource fails to augment → only that resource skips enrichment (`INV-3`-style per-resource isolation preserved through batch boundary)
- medterm4ds sidecar down → circuit breaker trips, all resources load without enrichment, WARNING logged
- Worker process crashes → main process catches `BrokenProcessPool`, logs, falls back to sync mode for remaining chunks

### Zero-dep default

Verify `tests/unit/test_import_isolation.py` still passes — the new `threading`, `multiprocessing`, and `concurrent.futures` imports are stdlib and must be lazy inside methods (not at module top), so the import-isolation sentinel continues to pass without updates to `_PUBLIC_SUBPACKAGES`.

## Backward Compatibility

| Existing code | After this feature |
|---|---|
| `AutoCoder(endpoint, conn)` | Unchanged — defaults `batch_size=1, workers=1` |
| `loader.load_resource(resource)` | Unchanged — always per-resource |
| `loader.load_ndjson(path)` | Internal path may use batch, results identical |
| `auto_coder.augment_resource(resource)` | Unchanged — still works, called when `batch_size=1` |
| `notes_pipeline.extract_conditions(resource)` | Unchanged — called when `batch_size=1` |
| `endpoint.search_batch(queries)` | Public signature unchanged; semantics identical; thread-safe now |

No public API breaks. No semantic changes.

## Risks

1. **Multiprocessing on Windows** — `spawn` semantics; workers re-import modules. Document any `if __name__ == "__main__"` guard requirement. Provide `workers=1` fallback.
2. **medterm4ds engine memory** — each worker loads medspaCy + SapBERT (~5GB). On 16GB machines, `workers=2` is the practical max. Document in `NotesPipelineConfig.workers` docstring; warn (not fail) when memory pressure detected via optional `psutil`.
3. **Picklability of medterm4ds results** — convert to dicts at process boundary (defensive). Explicit pickle round-trip test for the dict shape.
4. **Circuit breaker under concurrency** — add `threading.Lock`; thread-safety smoke test with 100 concurrent flaky calls.
5. **Test coverage for parallel paths** — multiprocessing bugs are non-deterministic. Explicit worker-pool tests, not just sync-path unit tests.
6. **`load_resources` already exists** — Step 3 is a *refactor* of the existing hooks, not a new method. Avoid regressing the existing dedup logic (`fhir_loader.py:360–416`).

## Dependencies

- **Not blocked** on medterm4ds publish.
- **Not blocked** on the Python Library Distribution Plan.
- **Not blocked** on Phase 4 cache work — the cache ownership move is orthogonal; the deterministic-results test relies on cache determinism within a single run, not across runs.

## References

- Source plan: `fhir4ds-private/docs/plans/batch-augmentation-plan.md`
- Phase 2 FDD: `fhir4ds-private/docs/plans/medterm4ds-integration.md`
- Phase 4 FDD: (referenced by source plan; verify path during implementation)
- medterm4ds Python Library Distribution Plan: `/mnt/d/medterm4ds/docs/plans/python-library-distribution-plan.md` (Phase 7 is the medterm4ds-side companion)
