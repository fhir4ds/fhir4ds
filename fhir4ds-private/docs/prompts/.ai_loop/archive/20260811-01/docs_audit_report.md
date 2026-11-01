# Docs Audit Report — 0.0.11 Re-Release

**Phase:** DOCS_AUDIT (pipeline step 3/5)
**Target version:** 0.0.11
**Audit date:** 2026-08-10
**Trigger:** Re-release of 0.0.11 after commit `bd5d7ded` ("fix(terminology): use medterm4ds from PyPI as a normal extra dep").

---

## 1. Notebook Execution Status

| Notebook | Status | Cells | Errors | Notes |
|----------|--------|------:|-------:|-------|
| `docs/notebooks/cql.ipynb` | PASS | 7 | 0 | `%pip install -q --find-links ../../dist "fhir4ds-v2[measures]==0.0.11"` resolves to `/mnt/d/fhir4ds/dist/fhir4ds_v2-0.0.11-py3-none-any.whl`. |
| `docs/notebooks/dqm.ipynb` | PASS | 7 | 0 | Same install snippet as `cql.ipynb`. |
| `docs/notebooks/fhirpath.ipynb` | PASS | 8 | 0 | `%pip install -q --find-links ../../dist fhir4ds-v2==0.0.11`. |
| `docs/notebooks/viewdef.ipynb` | PASS | 5 | 0 | Same install snippet as `fhirpath.ipynb`. |
| `fhir4ds-private/docs/notebooks/viewdef.ipynb` | FAIL (DOC-001 LOW) | 5 | 1 | Untracked internal playground. Cell 4 raises `CatalogException: Table with name resources does not exist!`. Pre-existing; unrelated to 0.0.11 re-release. NOT a blocker — directory is not git-tracked and not published. |
| `fhir4ds-private/docs/notebooks/{cql,dqm,fhirpath}.ipynb` | PASS | — | 0 | Untracked internal playground. Version-unpinned install (`%pip install fhir4ds-v2`); executes against the installed 0.0.11. |

**Method:** `jupyter nbconvert --to notebook --execute`. Executed notebooks written to `.temp/docs_audit/notebook_exec_v2/` (public set) and `fhir4ds-private/docs/notebooks/*.executed.ipynb` (private set).

**Static verification (all notebooks):** Zero references to removed APIs (`categories=`, `fhir_api_helpers`, `engines.local_duckdb`). All public-docs install snippets pin `fhir4ds-v2==0.0.11` and use `--find-links ../../dist` to resolve to the freshly-built wheel at `/mnt/d/fhir4ds/dist/fhir4ds_v2-0.0.11-py3-none-any.whl` (verified: wheel METADATA reports `Version: 0.0.11`).

---

## 2. Stale Data Log

| Finding | Type | Status | Detail |
|---------|------|--------|--------|
| REV-002 | API signature drift in FDD | RESOLVED | `docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md` lines 40-67 advertised `categories: list[str] \| None = None` as a medterm4ds.extract kwarg and listed `categories=None (all)` as a NotesPipelineConfig default. Rewrote the contract block to enumerate the actual published PyPI medterm4ds 0.0.1 signature (`extract(text, *, format, ner_labels, result_types, mode, min_grade, include_negated, include_uncertain, include_historical)`) and added a re-release note explaining the pre-PyPI draft drift. Cross-checked against `fhir4ds/cql/loader/notes_pipeline.py:_extract_kwargs()`. |
| REV-003 | Symbol drift in Known Fragile Areas registry | RESOLVED | `fhir4ds/cql/AGENTS.md` item 5 named pre-PyPI import paths (`medterm4ds.apps.fhir_api_helpers.expand_url_pattern` / `expand_intensional`) as canonical. Rewrote to enumerate the canonical post-PyPI surface (`LocalDuckDBEngine` top-level + full-path safety net, `Terminology.expand_url`, `apps.fhir_api.expand_url_pattern`, `services.discovery.search_names`) with file:line citations to `in_process_adapter.py`. Added a Known Limitation block flagging that `expand_intensional` has NO programmatic entry point on PyPI medterm4ds 0.0.1 (HTTP only). |
| DOC-001 (new) | Private playground notebook cell error | OPEN (LOW) | `fhir4ds-private/docs/notebooks/viewdef.ipynb` cell 4 raises `CatalogException`. Pre-existing, untracked, not published. See Section 1. |
| Version references | Stale-version sweep | CLEAN | No unpinned-to-0.0.11 version references in user-facing docs. All historical release install snippets in `web/website/docs/getting-started/releases.md` (0.0.5 through 0.0.10) are inside per-release sections and are accurate. The Phase 4 FDD's `Target version: 0.0.12` is a forward-looking design decision (Phase 4 originally targeted 0.0.12) — out of scope per the docs-auditor constraint against modifying FDD design decisions. |
| Conformance counts | Stale-count sweep | CLEAN | All conformance counts in `README.md`, `web/website/docs/getting-started/{whitepaper,benchmarking,releases}.md`, and `docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE1_TERMINOLOGY.md` match the current baseline (134/134, 935/935, 1706/1706, 47/47, 2822/2822). |
| Placeholders | `[PLACEHOLDER]` / TODO sweep | CLEAN | Zero hits across `docs/`, `web/website/docs/`, `README.md`, `AGENTS.md` files. |
| Broken links | Link verification | DEFERRED | Programmatic link crawling is out of scope for this docs-audit iteration. Spot-checked the medterm4ds-related cross-references (all internal file paths resolve). No externally broken links observed in the spot check. |
| medterm4ds API surface | Removed-API sweep | CLEAN | `grep -rn 'fhir_api_helpers\|engines\.local_duckdb\|categories='` returns only (a) the intentional historical "removed in commit bd5d7ded" mention inside the rewritten AGENTS.md item 5, (b) the explanatory note in the rewritten Phase 4 FDD, and (c) the intentional `expand_intensional` "not supported" stub at `in_process_adapter.py:331/349/357`. |

---

## 3. Audience Alignment Notes

| Page | Audience | Tone | Status |
|------|----------|------|--------|
| `web/website/docs/getting-started/whitepaper.md` | Stakeholder | Strategic, value-oriented ("paradigm shift", "~137× faster", "zero-server"). Conformance counts correct. | CLEAN |
| `web/website/docs/getting-started/benchmarking.md` | Stakeholder | Strategic, accuracy-first ("100% spec compliance", upstream-gap framing). Conformance counts correct. | CLEAN |
| `web/website/docs/getting-started/installation.md` | Developer | Technical, copy-pastable. PyPI package name (`fhir4ds-v2`) and import name (`fhir4ds`) distinction preserved. | CLEAN |
| `web/website/docs/user-guide/engine.md` | Developer | Technical. SQL-first / hybrid-execution / zero-server framing. | CLEAN |
| `web/website/docs/getting-started/releases.md` | Both | Re-release section (new) leads with the migration summary; conformance table follows; upgrade snippet pins 0.0.11. Original 0.0.11 ship notes preserved verbatim in the next section. | CLEAN |

No stylistic deviations observed.

---

## 4. Draft Release Notes (v0.0.11 re-release)

Appended to `web/website/docs/getting-started/releases.md` immediately above the original `## Version 0.0.11` section. Summary:

> **Version 0.0.11 (re-release)** — *August 2026*
>
> Documentation-and-packaging re-release. Applies a single Python-only commit (`bd5d7ded`) that migrates the medterm4ds integration from a vendored/source-checkout arrangement to the published PyPI wheel. No C++ or WASM changes; the bundled `fhirpath.duckdb_extension` is byte-for-byte identical to the original 0.0.11 ship.
>
> **What changed:**
> - `pyproject.toml` `[terminology]` extra now declares `medterm4ds>=0.0.1` as a normal PyPI dependency.
> - `in_process_adapter` canonical surface: `medterm4ds.LocalDuckDBEngine` (top-level re-export), `medterm4ds.engines.duckdb.engine.LocalDuckDBEngine` (safety net), `medterm4ds.Terminology.expand_url` (preferred), `medterm4ds.apps.fhir_api.expand_url_pattern` (fallback), `medterm4ds.services.discovery.search_names`. Legacy pre-PyPI import fallbacks removed.
> - `NotesPipelineConfig` dropped the unsupported `categories` kwarg. Published PyPI medterm4ds 0.0.1 signature: `extract(text, *, format, ner_labels, result_types, mode, min_grade, include_negated, include_uncertain, include_historical)`.
> - Known limitation surfaced: `expand_intensional` has no programmatic entry point on PyPI medterm4ds 0.0.1 (HTTP only). In_process adapter returns empty + WARNING; use the HTTP adapter for full intensional ValueSet expansion.
>
> **What did NOT change:** conformance baselines (134/935/1706/47, 2822 overall), public API surface, wheel C++/WASM contents.
>
> **Conformance baselines (re-release verification):** 134/134 ViewDefinition v2, 935/935 FHIRPath R4, 1706/1706 CQL, 47/47 DQM QI-Core 2025, 2822/2822 overall.
>
> **Upgrade:** `pip install fhir4ds-v2==0.0.11` (the `[terminology]` and `[ner]` extras now pull medterm4ds from PyPI automatically — no manual install required).

---

## 5. Issue Disposition

| Issue | Severity | Status | Owner |
|-------|----------|--------|-------|
| REV-002 | MEDIUM | RESOLVED | docs_auditor |
| REV-003 | MEDIUM | RESOLVED | docs_auditor |
| DOC-001 | LOW | OPEN | future (private playground, untracked) |

**No CRITICAL or HIGH findings.** One new LOW finding (DOC-001) deferred — private untracked playground notebook with a pre-existing cell error unrelated to the re-release.

**Verdict: PASS.** Ready for the next pipeline step (benchmarks).
