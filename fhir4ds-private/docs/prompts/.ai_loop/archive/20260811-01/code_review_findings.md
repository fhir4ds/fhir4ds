# Code Review Findings — medterm4ds PyPI migration (commit bd5d7ded)

**Reviewer:** CODE_REVIEWER role, .ai_loop pipeline.
**Target:** 0.0.11 re-release gate.
**Scope:** commit `bd5d7ded` "fix(terminology): use medterm4ds from PyPI as a normal extra dep" plus working-tree state.
**Method:** Line-by-line audit of every changed file against ROLE_CODE_REVIEWER §3 audit dimensions (SQL injection, error swallowing, circuit breaker correctness, defensive import chains, dead code, type safety) plus AGENTS.md Known Fragile Areas cross-reference.

---

## Overall Verdict: PASS WITH FINDINGS

The commit's core refactor is sound: dead pre-PyPI import paths are correctly excised, the circuit breaker invariant on `expand_intensional` is preserved (no `_on_call_failure` invocation on the "not supported" path), the defensive import chain prefers the canonical top-level re-export and falls back to the full path correctly, and the dead `categories` field is fully removed from `NotesPipelineConfig` and `_extract_kwargs`. **No SQL injection, error swallowing, or type-safety regressions were found in production code.** Three findings: one HIGH-severity missed test update (the live-sidecar sibling test still passes the removed kwarg), and two MEDIUM-severity documentation drift items. None are CRITICAL blockers for the 0.0.11 release, but REV-001 will manifest as a `TypeError` the moment anyone runs the live integration suite.

---

## Findings by Severity

### HIGH (1)

**REV-001 — Missed test update: `test_medterm4ds_live.py` still passes the removed `categories` kwarg**
- File: `fhir4ds/cql/tests/integration/test_medterm4ds_live.py:281`
- The commit updated `test_medterm4ds_in_process.py` (removed `categories=["condition"]`) but missed the live-sidecar sibling test, which still constructs `NotesPipelineConfig(categories=["condition"], min_grade="probable")`.
- Since `categories` was removed from the `NotesPipelineConfig` dataclass (`fhir4ds/cql/loader/notes_pipeline.py:99-163`), this construction raises `TypeError: __init__() got an unexpected keyword argument 'categories'`.
- Reproducer: `MEDTERM4DS_TEST_URL=http://127.0.0.1:8001/fhir pytest fhir4ds/cql/tests/integration/test_medterm4ds_live.py::test_phase4_notes_pipeline_extracts_conditions`
- Impact: live-sidecar integration test is broken for any CI / downstream packager / manual QA that sets `MEDTERM4DS_TEST_URL`. The standard conformance run (`conformance/scripts/run_all.py`) does not invoke this test, so conformance stays green, but the release artifact gate (USER_DIRECTIVES item 5: "release/package/import checks for 0.0.11") will surface this if the packager exercises the `[ner]` extra against a real sidecar.
- Recommended fix: drop the `categories=["condition"],` line at `test_medterm4ds_live.py:281`, mirroring the in_process test's update. One-line change; no semantic loss (the kwarg was a no-op against published medterm4ds anyway).

### MEDIUM (2)

**REV-002 — FDD still documents the removed `categories` kwarg as a supported medterm4ds.extract parameter**
- File: `docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md:40-67`
- The FDD (referenced as the source of truth at `notes_pipeline.py:13`) still shows `categories: list[str] | None = None` in the medterm4ds.extract contract sketch (line 47) and lists `categories=None (all)` in the NotesPipelineConfig defaults (line 64). The published PyPI medterm4ds 0.0.1 wheel does NOT accept this kwarg.
- Impact: any future maintainer implementing against the FDD will reintroduce the bug the commit just fixed. Will be caught by `pytest`, but the FDD should not advertise a contract the upstream doesn't ship.
- Owner: docs_audit workflow (next in pipeline). Surfaced here because `notes_pipeline.py:13` cites this FDD as the canonical spec reference.

**REV-003 — AGENTS.md Known Fragile Areas entry references removed `fhir_api_helpers` import paths**
- File: `fhir4ds/cql/AGENTS.md:4646-4651` (medterm4ds Phase 1 integration notes, item 5 "medterm4ds symbol drift")
- The entry names `medterm4ds.apps.fhir_api_helpers.expand_url_pattern` / `expand_intensional` as the symbols whose drift would degrade the adapter. The commit removed all `fhir_api_helpers` references; the canonical surface is now `medterm4ds.Terminology.expand_url` (preferred), `medterm4ds.apps.fhir_api.expand_url_pattern` (fallback), `medterm4ds.services.discovery.search_names`. The Known Fragile Areas registry is specifically designed to flag drift for future maintainers, so an out-of-date entry actively undermines the safety net.
- Owner: docs_audit workflow. Surfaced here because the entry cross-references the file under review.

### LOW (0)

No LOW findings. The remaining broad `except Exception` blocks in `in_process_adapter.py` (lines 269, 315, 401, 481) are all justified per the invariants documented in `AGENTS.md:4642-4645` (INV-8: endpoint failures are scoped to the resolver fallback path and logged at WARNING/ERROR). The breaker-state mutation in `_on_call_failure` (lines 174-184) logs at ERROR when the breaker trips, satisfying the audit requirement.

---

## Implementation Health Summary

The core production-code refactor in `bd5d7ded` is clean and idiomatic. Circuit-breaker correctness on `expand_intensional` is preserved (verified: no `_on_call_failure` invocation on the "not supported" path; the docstring accurately describes the invariant). The defensive import chain at `in_process_adapter.py:93-104` correctly prefers the canonical top-level re-export `medterm4ds.LocalDuckDBEngine` and falls back to `medterm4ds.engines.duckdb.engine.LocalDuckDBEngine` only if the re-export is absent. No `SQLRaw` or string-interpolated DuckDB execution was introduced. The `notes_pipeline.py` worker pool boundary remains fork-safe (workers are module-level functions; no closure over `self`). Type hints on the rewritten `expand_intensional` and `_extract_kwargs` are accurate; `_extract_kwargs` return type widened appropriately to `dict[str, Any]`. The two MEDIUM doc-drift items will be owned by the docs_audit workflow; the single HIGH test-update miss is a one-line fix the engineer workflow can pick up before pre_release gates the wheel.
