# Code Review — Batch Augmentation Feature (dev branch)

**Verdict: PASS WITH FINDINGS**

The Batch Augmentation feature ships 72/72 passing tests across the six
new test modules and import isolation remains clean (3/3). No CRITICAL
issues found. The implementation correctly honors the FDD's INV-A1..A8
list: workers are module-level with no `self` closure (verified by
explicit pickle-round-trip tests), breaker mutations are locked,
`psutil` is optional, the parallel path correctly falls back to sync,
`load_resource` (singular) is unchanged, and Step 6 is inert
(`NotImplementedError`).

Five lower-severity findings follow. None block merge.

---

## Findings

### QA-001 — Torn reads of breaker state in warning-log paths
```json
{
  "id": "QA-001",
  "severity": "LOW",
  "status": "OPEN",
  "category": "CONCURRENCY",
  "spec_citation": "FDD §Step 4 / INV-A5; ROLE_CODE_REVIEWER Phase 4",
  "evidence": "fhir4ds/cql/terminology/http_adapter.py:362-369, 389-396, 422-429. The breaker's `_is_breaker_open(now)` correctly acquires `self._lock`, but the WARNING log block immediately after the early-return reads `self._consecutive_failures` and `self._tripped_until` WITHOUT acquiring the lock. Under concurrent failures from `search_batch`'s thread pool, the logged values can be a torn/inconsistent pair (e.g., failures read before trip, _tripped_until read after). Impact is limited to log-message cosmetics — no control flow depends on these reads — so severity is LOW. The FDD acknowledges this risk explicitly (§Step 4: 'remaining futures still execute ... results are dropped if breaker is open at result-collection time'), so the call-path is safe; only the diagnostic log is racy.",
  "root_cause": "Diagnostic log block placed outside the lock to avoid holding the lock across I/O (logger), at the cost of read consistency.",
  "resolution": "Either (a) snapshot the two values inside `_is_breaker_open` and return them as a tuple so the caller logs from a consistent snapshot, or (b) accept the race and add a code comment documenting it. Option (a) is preferred for observability correctness.",
  "verified_in": "fhir4ds/cql/tests/unit/terminology/test_http_adapter_parallel.py:155 (test_breaker_counter_no_torn_reads_under_concurrency) — covers counter writes, not log-path reads."
}
```

### QA-002 — Duplicated kwargs-build logic between `_extract_kwargs` and `_call_medterm4ds`
```json
{
  "id": "QA-002",
  "severity": "LOW",
  "status": "OPEN",
  "category": "MAINTAINABILITY",
  "spec_citation": "FDD §Step 5 architecture sketch ('Centralized so _call_medterm4ds (sync) and the Pool initializer (parallel) build the identical kwargs')",
  "evidence": "fhir4ds/cql/loader/notes_pipeline.py:392-408 (`_extract_kwargs`) and 510-522 (`_call_medterm4ds`). Both methods build the identical 7-key kwargs dict from the same config fields with the same conditional logic. The FDD explicitly states `_extract_kwargs` exists to 'centralize so _call_medterm4ds (sync) and the Pool initializer build the identical kwargs.' The sync path (`_call_medterm4ds`) does NOT call `_extract_kwargs` — it inlines a second copy. A future config field added to only one site silently desyncs the sync and parallel paths. The regression is partially caught by `test_extract_kwargs_matches_call_medterm4ds` (line 170), but that test only pins today's shape — it does not enforce the call-site refactor.",
  "root_cause": "`_call_medterm4ds` predates `_extract_kwargs`; refactor did not eliminate the duplication.",
  "resolution": "Replace the body of `_call_medterm4ds` with: `return self._extract_fn(text, **self._extract_kwargs())`. The test at line 170 continues to pass.",
  "verified_in": "fhir4ds/cql/tests/unit/loader/test_notes_pipeline_parallel.py:170"
}
```

### QA-003 — `extract_conditions_batch` sync-path emits no INFO for the parallel-threshold fallback when `workers == 1`
```json
{
  "id": "QA-003",
  "severity": "LOW",
  "status": "OPEN",
  "category": "OBSERVABILITY",
  "spec_citation": "FDD §Step 1 NotesPipelineConfig.parallel_threshold docstring ('An INFO log line is emitted when the threshold fires')",
  "evidence": "fhir4ds/cql/loader/notes_pipeline.py:362-368. The INFO log fires only when `workers > 1 AND len(resources) < threshold`. When `workers == 1` (the default) and the user has explicitly raised `parallel_threshold`, no INFO is emitted even though the sync path was selected by the threshold rather than the workers knob. This is arguably correct (workers==1 is the user's explicit choice for sync), but the FDD docstring promises an INFO 'when the threshold fires' without qualification. Users debugging 'why isn't this batch parallelizing?' with `workers=1` will get no diagnostic.",
  "root_cause": "Log condition conflates 'workers==1' (user-intentional sync) with 'threshold not met' (heuristic sync).",
  "resolution": "Either expand the FDD docstring to say 'an INFO log line is emitted when the threshold fires AND workers > 1', or emit the log whenever `len(resources) < threshold` regardless of workers. Low priority either way.",
  "verified_in": "Manual inspection."
}
```

### QA-004 — `augment_resources` swallows `NotImplementedError` separately from generic `Exception`, hiding future worker errors
```json
{
  "id": "QA-004",
  "severity": "LOW",
  "status": "OPEN",
  "category": "ERROR_HYGIENE",
  "spec_citation": "FDD §Step 6 ('DEFERRED'); ROLE_CODE_REVIEWER §Error hygiene",
  "evidence": "fhir4ds/cql/loader/auto_coder.py:286-299. The `try/except` catches `NotImplementedError` first, then `except Exception` as a fallback. The `except Exception` block logs at WARNING and falls back to sync — correct for INV-9 isolation. However, the generic `except Exception` will also swallow any future `NotImplementedError` subclass (Python: NIE *is* a RuntimeError/Exception subclass). Today Step 6 raises plain `NotImplementedError`, so both branches catch it; the only behavioral difference is the log message. This is fine now, but if Step 6 is ever implemented, a worker that raises NIE for a different reason (e.g., a downstream library NIE) will be silently routed to sync with the generic 'parallel path failed' message, losing the Step 6 explanation. Minor.",
  "root_cause": "The two-tier catch was added to differentiate 'Step 6 deferred' from 'Step 6 broken', but the parent class catch obliterates that distinction for NIE specifically.",
  "resolution": "When Step 6 is implemented, drop the `NotImplementedError` branch entirely. For now, document the intent in a code comment. No action required for the current merge.",
  "verified_in": "fhir4ds/cql/tests/unit/loader/test_auto_coder_parallel.py (passes; both branches exercised)."
}
```

### QA-005 — `_extract_batch_parallel` worker count not bounded against available memory, only against `cpu_count()`
```json
{
  "id": "QA-005",
  "severity": "LOW",
  "status": "OPEN",
  "category": "RESOURCE_BOUNDS",
  "spec_citation": "FDD §Step 5 INV-A8 ('warn (not fail) when memory pressure detected')",
  "evidence": "fhir4ds/cql/loader/notes_pipeline.py:431-448. `actual_workers = max(1, min(workers, cpu_count()))` correctly bounds by CPU. The `psutil` block correctly imports lazily and silently skips on ImportError — exactly as specified. However, the warning only fires when `actual_workers * 5GB > available`. On a 64GB machine with 60GB available, `workers=12` passes the check (60 == 60), but medspaCy warm-up overhead + parent DuckDB footprint can still OOM. The FDD says 'warn, not fail' so this matches spec; the only nit is that the threshold constant (5GB) is a magic number not exposed as a config field. `parallel_threshold=200` IS exposed correctly as a config field per audit S2.",
  "root_cause": "Magic constant 5GB reflects today's medspaCy+SapBERT footprint; not parameterized.",
  "resolution": "Either expose `worker_memory_budget_gb: float = 5.0` as a config field, or add a code comment noting the constant is empirical and tie-breaks with the user's right to override via `workers`. No merge blocker.",
  "verified_in": "fhir4ds/cql/tests/unit/loader/test_notes_pipeline_parallel.py — no test exercises the psutil branch (mocked-import path)."
}
```

---

## Dimensions cleared (no findings)

- **Concurrency correctness (dim 1)**: All writes to `_consecutive_failures` and `_tripped_until` happen inside `with self._lock:` (http_adapter.py:190, 200, 206). The 100-thread test at test_http_adapter_parallel.py:155 proves no torn counter writes. QA-001 above is a read-only diagnostic race, not a control-flow race.
- **Picklability (dim 2)**: `_init_worker` and `_worker_extract_fragments` are module-level (notes_pipeline.py:670, 696). Explicit pickle-round-trip tests at test_notes_pipeline_parallel.py:47 and :66 verify no `self` closure; workers convert ExtractedConcept to plain dicts at the boundary (lines 730-744). PASS.
- **Backward compatibility (dim 4)**: `load_resource` (singular) is unchanged (fhir_loader.py:266). With `batch_size=1, workers=1`, `augment_resources` delegates per-resource (auto_coder.py:264-267) and `extract_conditions_batch` chunks into single-element chunks (notes_pipeline.py:362-374) — byte-identical to the pre-feature path. The pre-augment/pre-extract passes in `load_resources` (fhir_loader.py:367-392) produce identical results because they call the same per-resource methods. PASS.
- **Cache invalidation (dim 6)**: Workers in `_worker_extract_fragments` never touch `autocoding_cache` — they return plain concept dicts and the parent calls `_build_condition`. The AutoCoder cache is written only inside `augment_resource` (which runs in the parent). Step 6 deferred path raises `NotImplementedError` (auto_coder.py:322) — confirmed inert, no pool spins up. PASS.
- **SQL injection (dim 9)**: All `con.execute(f"...")` interpolations (fhir_loader.py:194, 214, 666, 718, 818, 873, 976; auto_coder.py:491, 574, 625) use trusted constants (`self.CACHE_TABLE`, `self._quoted_table_name`, `macro_name`) — never user input. All user-provided values flow through `?` placeholders. No new injection surface introduced. PASS.
- **Hardcoded assumptions (dim 7)**: `HTTP_SEARCH_BATCH_MAX_WORKERS = 8` is a named module constant with a documented rationale (http_adapter.py:57-60). `parallel_threshold = 200` IS a config field (notes_pipeline.py:159), not a magic number. No FHIR resource-type-specific branches leaked into the generic runtime paths. PASS.
- **Cross-platform (dim 5)**: Worker functions are module-level, no inherited parent state, so Windows `spawn` re-imports cleanly. The `if __name__ == "__main__"` guard requirement is documented in the `workers` field docstring (notes_pipeline.py:133-137). PASS.

---

**Test summary**: 72/72 batch-augment tests pass; 3/3 import-isolation tests pass. No regressions.

---

## Resolutions (post-review)

All 5 LOW findings addressed:

- **QA-001 RESOLVED**: Added `_breaker_snapshot()` helper
  (`http_adapter.py:184`) that takes the lock and returns
  `(failures, tripped_until)` as a tuple. All three log sites
  (`expand`, `expand_intensional`, `search_text`) now read from the
  snapshot — no more torn reads.
- **QA-002 RESOLVED**: `_call_medterm4ds` now delegates to
  `_extract_kwargs` (`notes_pipeline.py:510-515`). 6 lines → 3 lines;
  single source of truth.
- **QA-003 RESOLVED**: FDD docstring on `parallel_threshold` updated
  to say "INFO log fires AND `workers > 1`" — matches code.
- **QA-004 RESOLVED**: Added explicit comment on the two-tier catch
  in `auto_coder.py:286` documenting why `NotImplementedError` is
  differentiated and when to drop the branch (when Step 6 is
  implemented).
- **QA-005 RESOLVED**: Extracted `WORKER_MEMORY_BUDGET_BYTES = 5 *
  (1024 ** 3)` module constant (`notes_pipeline.py:88`) with a
  comment explaining it's empirical and overridable via `workers`.

Re-ran 153 tests (72 batch-augment + 6 import-isolation + 75
pre-existing related): all pass.
