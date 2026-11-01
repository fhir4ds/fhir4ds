# Design Handoff — Batch Augmentation FDD

**Workflow**: feature_design → WAIT_FOR_USER_APPROVAL
**Plan path**: `fhir4ds-private/docs/plans/FEATURE_BATCH_AUGMENTATION.md`
**Target version**: 0.0.12
**Date**: 2026-07-04

## What was designed

The Batch Augmentation feature adds `batch_size` and `workers` config
knobs to `AutoCoder` and `NotesPipeline`, enabling batch-aware
augmentation and parallel execution for Phase 2 (auto-coding) and
Phase 4 (clinical notes NER). Scope is Steps 1–6 of the origin plan;
Step 7 (default bumps) is deferred.

## What changed vs. the origin plan

The origin plan (`docs/plans/batch-augmentation-plan.md`) was written
before the post-Phase-4 commits landed. Three things shifted:

1. **`FHIRDataLoader.load_resources` already exists** at
   `fhir_loader.py:334` — and `load_ndjson` / `load_directory` already
   delegate to it. Step 3 is no longer additive; it's a surgical
   refactor of the two augmentation hooks inside `load_resources`
   (L371–372 and L394–416) to honor `batch_size`.
2. **Both configs are `frozen=True`** — preserved. New fields are
   additive only.
3. **The circuit breaker is explicitly single-threaded** — Step 4
   must add `threading.Lock` and update the docstrings
   (`http_adapter.py:14–22, 127–130, 152–154`).

The "2822/2822" conformance assertion was also stale — the actual
repo computes `grand_passed` dynamically with no hardcoded count. The
FDD prescribes a baseline-file mechanism
(`baseline_conformance_count.txt`) to capture and assert the current
count without hardcoding.

## Architecture self-audit outcome

7 skeptical notes were raised in
`docs/prompts/.ai_loop/ARCHITECT_REVIEW.md` and addressed in the v2
FDD. Highest-impact:

- **S1 (HIGH)**: Module-level worker functions; no `self` closure.
  Otherwise the parent's DuckDB connection would be pickled into
  worker processes (fork-unsafe).
- **S2 (MEDIUM)**: `parallel_threshold` config field (default 200)
  replaces the magic `< 200` sync heuristic; logs when it fires.
- **S5 (MEDIUM)**: Parallel mode is read-only on `autocoding_cache`
  during the batch; parent writes cache after `pool.map` returns.
- **S6 (MEDIUM)**: Baseline-file conformance assertion instead of the
  stale "2822" literal.

No CRITICAL findings. The feature preserves all 8 Golden Standard
invariants (zero-dep default, frozen config, byte-identical defaults,
non-raising batch boundary, thread-safe breaker, picklable worker
boundary, cross-platform docs, bounded resource use).

## What happens next

Per `ROLE_FEATURE_DESIGNER.md` §4 and `ROLE_MASTER_ORCHESTRATOR.md` §6,
the Orchestrator sets `workflow: WAIT_FOR_USER_APPROVAL` and stops.
The human must write "APPROVED" or "EXECUTE" in chat or
`USER_DIRECTIVES.md` to advance to `feature_implementation`.

When approved, `feature_implementation` (re-hydrating
`ROLE_FEATURE_ENGINEER.md`) will execute Steps 1–6 in sequence:

1. Config knobs (zero behavior change)
2. Batch-aware augmentation methods
3. FHIRDataLoader hook refactor (existing `load_resources`)
4. Parallel HTTP in `search_batch` (thread pool + lock-guarded breaker)
5. Multiprocessing pool for NotesPipeline (module-level workers, dict boundary)
6. Multiprocessing pool for AutoCoder (optional, lighter)

Then `code_review` runs the audit dimensions in `USER_DIRECTIVES.md`
§Code Review Gate (concurrency correctness, picklability, resource
bounds, backward compatibility, cross-platform, cache invalidation,
zero-dep default, hardcoded assumptions).

## Files written this workflow

- `fhir4ds-private/docs/prompts/.ai_loop/FEATURE_PLAN_DRAFT.md` (v1, archived as the audit input)
- `fhir4ds-private/docs/prompts/.ai_loop/ARCHITECT_REVIEW.md` (self-audit with 7 findings + verdict)
- `fhir4ds-private/docs/plans/FEATURE_BATCH_AUGMENTATION.md` (v2, refined — the implementation source of truth)
- `fhir4ds-private/docs/prompts/.ai_loop/design_handoff.md` (this file)
- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json` (state updated to WAIT_FOR_USER_APPROVAL)
