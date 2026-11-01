# ARCHITECTURE SELF-AUDIT — Batch Augmentation FDD v1

> Designer-owned architecture self-audit per `ROLE_FEATURE_DESIGNER.md`
> Step 3, applying the standards of `ROLE_ARCHITECT.md`. Phase 1
> (Golden Standard) and Phase 2 (Code Audit against the FDD draft)
> only. Phases 3 (empirical validation) and 4 (issue logging) belong
> to the post-implementation evolution loop.
>
> Prior Phase-4 architect review archived at
> `archive/ARCHITECT_REVIEW_phase4_2026-07-03.md` (unrelated cycle).

## Golden Standard — 8 falsifiable invariants

The Batch Augmentation feature must preserve these invariants. Each is
falsifiable: a concrete test or code reading can prove it violated.

**INV-A1 (Zero-dep default)**: Top-level `import fhir4ds` succeeds
with `httpx`, `medterm4ds`, `medspacy`, `spacy`, `torch` all
uninstallable. Verified by `tests/unit/test_import_isolation.py`
sentinel. New stdlib imports (`threading`, `multiprocessing`,
`concurrent.futures`) must be lazy inside methods, never at module top.

**INV-A2 (Frozen config)**: `AutoCoderConfig` and
`NotesPipelineConfig` remain `@dataclass(frozen=True)`. Mutation only
via `dataclasses.replace`. Required so existing call sites that pass
configs by reference and replace them keep working.

**INV-A3 (Byte-identical defaults)**: With
`batch_size=1, workers=1`, the `resources` table content (rows +
JSON byte content) and `autocoding_cache` table state produced by
`load_ndjson(path)` is byte-identical to the pre-feature code path.
Verified by direct comparison test against a pinned baseline.

**INV-A4 (Phase 4 non-raising boundary preserved through batch)**:
`NotesPipeline.extract_conditions_batch` never raises — a single bad
resource poisons only its own slot. Mirrors existing `INV-3` at
`fhir_loader.py:394–416` for the per-resource path.

**INV-A5 (Circuit breaker thread safety)**: After Step 4,
`HTTPTerminologyEndpoint` is safe for concurrent calls from the
internal thread pool. The `_consecutive_failures` and
`_tripped_until` counters show no torn reads or writes under
concurrent failures. Class and module docstrings updated from
"NOT thread-safe" to "Thread-safe under internal lock; safe for
search_batch's thread pool".

**INV-A6 (Process-boundary picklability)**: Every value crossing a
`multiprocessing.Pool` boundary is `pickle.dumps()`-able. medterm4ds-
owned `ExtractedConcept` is converted to plain `dict` at the worker
return boundary, sidestepping any picklability regression in a future
medterm4ds release.

**INV-A7 (Cross-platform worker semantics documented)**: Windows
`spawn` vs POSIX `fork` differences are documented in the
`NotesPipelineConfig.workers` docstring, including the
`if __name__ == "__main__"` guard requirement for user code under
`spawn`. fhir4ds does not silently fail on Windows.

**INV-A8 (Resource bounds)**: Worker count is bounded by
`min(config.workers, os.cpu_count() or 1)`. When `psutil` is
available (optional, not a dependency), the pipeline logs a WARNING
when `workers * 5GB > available_virtual_memory`. No unbounded pools.

## Audit findings — FDD v1 against the Golden Standard

### PASS — invariants addressed by the draft

- **INV-A1**: FDD Test Strategy section explicitly states new stdlib
  imports must be lazy. ✅
- **INV-A2**: FDD Step 1 explicitly preserves `frozen=True`. ✅
- **INV-A3**: FDD Test Strategy prescribes byte-identical comparison
  for `batch_size=1` baseline. ✅
- **INV-A4**: FDD Step 2 says batch methods must respect the same
  per-resource isolation as today's `extract_conditions`. ✅
- **INV-A5**: FDD Step 4 mandates `threading.Lock` around breaker
  state and docstring update. ✅
- **INV-A6**: FDD Step 5 prescribes dict conversion at worker
  boundary plus pickle round-trip test. ✅
- **INV-A8**: FDD Step 5 has worker-count bounding formula and
  optional `psutil` warning. ✅

### FINDING — Skeptical Notes to address in v2

**S1 (HIGH): DuckDB connection fork-safety is under-specified.**
The FDD says "DuckDB connections are not fork-safe — workers must
construct their own connection via `medterm4ds.connect()`." But the
*parent* process holds a connection via the loader (`self.con` on
`FHIRDataLoader`). After `fork()`, child processes inherit the file
descriptors but DuckDB's internal locks are not fork-safe. The FDD
should explicitly state: workers MUST NOT touch the parent's DuckDB
connection; medterm4ds owns its own connection inside the worker
process. Worker functions must be `def _extract_one(text): ...` with
**no reference to `self` or `self.con`** — the worker is a
module-level function that uses the global `_engine` set up by
`_init_worker`. The current Step 5 code sketch has the worker
function reference `self._extract_kwargs`, which would force `self`
to be pickled into the worker — that drags in the parent's DuckDB
connection. **Fix**: lift `_extract_kwargs` into the initializer;
workers read it from a module global alongside `_engine`.

**S2 (MEDIUM): The "small batch → sync" heuristic threshold is magic.**
FDD Step 5 says `if len(texts) < 200: use sync`. The plan's
justification is "30s medspaCy warm-up per worker." But:
- 30s warm-up × 4 workers in parallel = 30s wall time, not 120s. The
  threshold should be `warmup_seconds * workers / per_text_cost_ms`,
  not a fixed 200.
- On a machine where medspaCy is already warm (e.g. user called
  `extract_conditions` once before), the heuristic is wrong.
- 200 is silent — no log line, no way for users to know why their
  `workers=8` config didn't parallelize.

**Fix in v2**: Make the heuristic explicit and observable.
- Add a `parallel_threshold` field to `NotesPipelineConfig` (default
  200, documented as "tuned for cold medspaCy warm-up").
- Log at INFO level when the heuristic fires: "len(texts)=%d <
  parallel_threshold=%d; using sync mode".
- Document in the docstring that users with pre-warmed medspaCy can
  lower this to 0.

**S3 (LOW): ThreadPoolExecutor max_workers cap of 8 is undocumented magic.**
FDD Step 4 has `max_workers=min(8, len(queries))` but doesn't justify
the 8. Reasonable choice (most sidecars handle 8 concurrent), but
should be a named constant or config field. **Fix in v2**: add
`HTTP_SEARCH_BATCH_MAX_WORKERS = 8` module constant with a comment
citing sidecar concurrency limits.

**S4 (MEDIUM): `extract_conditions_batch` return type ambiguity.**
FDD Step 2 says the return is `list[list[dict]]`. But the existing
`extract_conditions(resource) -> list[dict]` returns a list of
*derived Conditions* for one resource. The batch version returns one
list-of-Conditions per resource. That's correct but easy to confuse
with a flat list. **Fix in v2**: add an explicit type alias
`DerivedConditions = list[dict]` and document the per-resource
grouping in the docstring with an example.

**S5 (MEDIUM): Cache invalidation under batch execution is not addressed.**
The `autocoding_cache` is keyed by `(codeable_path_text, engine_version, ...)`.
If two resources in the same batch have the same CodeableConcept text,
the cache hit semantics must be identical whether the work happens in
the parent process or in a worker process. Since workers each load
their own engine and the cache lives in the *loader's* DuckDB
connection, parallel workers can only read cache (no write back from
workers — that would require IPC). **Fix in v2**: document that
parallel mode is **read-only on the autocoding_cache** during the
batch; cache writes happen in the parent process after `pool.map`
returns. Workers may recompute a Coding that the parent already
cached — that's acceptable (correctness preserved; minor perf cost
on cache misses).

**S6 (MEDIUM): Conformance "2822/2822" assertion shape.**
The FDD correctly identifies that "2822" is not asserted in code. But
the v1 Test Strategy still says "no regression in `grand_passed` vs.
baseline" without specifying how the baseline is captured. **Fix in
v2**: capture the baseline at feature-branch start
(`git stash && python3 conformance/scripts/run_all.py 2>&1 | grep
grand_passed`) and write it to
`tests/integration/baseline_conformance_count.txt`. The CI assertion
becomes "current `grand_passed` >= baseline file content". This
matches how the actual repo works (no hardcoded count).

**S7 (LOW): Plan staleness around `load_resources`.**
The source plan says "Add (or confirm existence of) a batch-load
method" — implying the author wasn't sure. The FDD v1 correctly
notes that it already exists, but the Implementation Plan section
still reads as if Step 3 is mostly-additive. **Fix in v2**: rewrite
Step 3 to lead with "Refactor the existing two augmentation hooks
inside `load_resources` (L371–372 and L394–416) to honor `batch_size`
— `load_resources` itself already exists."

## Recommended Fix Order for v2

1. **S1** (HIGH): Restructure worker functions to be module-level,
   read `_extract_kwargs` from global. Without this fix, Step 5 will
   crash on `fork`-unsafe DuckDB or pickle the parent connection.
2. **S2** (MEDIUM): Promote the threshold to a config field, log when
   it fires.
3. **S5** (MEDIUM): Document cache read-only semantics in parallel mode.
4. **S6** (MEDIUM): Capture baseline file, replace "2822" assertion.
5. **S4** (LOW): Type alias + example in docstring.
6. **S3** (LOW): Named constant for `max_workers`.
7. **S7** (LOW): Rewrite Step 3 lead sentence.

No **CRITICAL** findings. The draft is structurally sound; the
skeptical notes are refinements, not redesigns.

## Verdict

The v1 draft preserves all 8 Golden Standard invariants at the design
level. The 7 skeptical notes above will be addressed in v2 before
the FDD is finalized. The feature is safe to hand off to
implementation once v2 is written.
