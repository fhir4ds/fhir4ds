# Design Handoff — medterm4ds Phase 4: Clinical Notes NER Extension

**Handoff date:** 2026-07-03
**Phase:** 4 of 4 (Clinical Notes NER)
**Target version:** 0.0.12
**FDD:** `docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md`
**Audit:** `fhir4ds-private/docs/prompts/.ai_loop/ARCHITECT_REVIEW.md` (9 invariants, all testable)
**Draft (line-drift traceable):** `fhir4ds-private/docs/prompts/.ai_loop/FEATURE_PLAN_DRAFT.md`

---

## 1. What was designed

A clinical-notes-aware auto-coding pipeline that extends Phase 2's
text-only CodeableConcept path to narrative note bodies. Pipeline:
medspaCy (Sectionizer + ConText) → HuggingFace token-classification NER
(`d4data/biomedical-ner-all`) → section + assertion filter → SapBERT
linking via Phase 1 endpoint → CodeableConcept construction (reusing
Phase 2's autocoding extension with `engine="medterm4ds-ner"`) → NEW
derived Condition resources, loaded into DuckDB alongside their source.

Each derived Condition carries provenance via
`Condition.evidence.detail` referencing `{source_resourceType}/{source_id}`,
a `derived-from-text` extension with span offsets + section title for
debugging, `verificationStatus="unconfirmed"`, `clinicalStatus="active"`,
and a `meta.tag=auto-derived` marker. Source resources are NEVER
mutated. Derived ids are deterministic hashes of
`(source_type, source_id, span_start, span_end)` for idempotent re-runs.

The whole pipeline is opt-in behind a new `[fhir4ds,ner]` extra
(`medspacy`, `spacy`, `transformers`, `torch`). `fhir4ds` core imports
cleanly without those deps — every NER-specific import is lazy.

## 2. Key design decisions

| # | Decision | Rationale |
|---|----------|-----------|
| a | **Pipeline invocation inside `FHIRDataLoader`, after augmentation, before validation; derived Conditions join the same batch** | One call site; one transaction; pre-validation placement so the raw dict is readable; cache reuse via Phase 2 `autocoding_cache` table. |
| b | **base64-decoding lives in a helper, not in the path DSL** | Known finite set of base64 paths; tuple-keyed dict is faster than parsing a DSL; list-aware walker (`_walk_path_list_aware`) handles both base64 and non-base64 list intermediates uniformly. |
| c | **Heavy models (medspaCy + scispaCy + biomedical-ner-all) load lazily on first `extract_spans()`** | Zero-dep module-import guarantee; one-time cost amortized across the load; cached on the `ClinicalNoteNER` instance. |
| d | **Section allow-list + context excludes as module-level data** | Data-driven defaults in `section_allowlist.py`; overridable via `ClinicalNotesConfig`. Empty list disables filtering (footgun, documented). |
| e | **NER-type → category mapping as data-driven dict** | Lives in `notes_pipeline.py` (`NER_TYPE_TO_CATEGORY`); overridable via `ClinicalNotesConfig.ner_type_overrides`. Unknown labels log DEBUG and skip. |
| f | **Derived Condition id = deterministic hash of `(source_type, source_id, span_start, span_end)`** | Idempotent re-runs; DuckDB delete-before-insert dedups cleanly; 16-hex-char (64-bit) suffix is collision-safe. |
| g | **Reuses Phase 2's autocoding extension with `engine="medterm4ds-ner"`** | Downstream consumers route on `engine` to find NER-derived codings for Phase 5 re-derivation sweeps. |

## 3. Refinements from the architecture self-audit

- **S1 (helper extraction):** Phase 2's `AutoCoder` private methods
  (`_lookup_or_search`, `_filter_and_truncate`, `_resolve_index_version`,
  `_result_to_dict`) are promoted to a new shared module
  `fhir4ds/cql/loader/search_helpers.py`. Both `AutoCoder` and
  `ClinicalNotesPipeline` consume them. Removes private-API coupling;
  Phase 2 tests pass unchanged.
- **S2 (batch insert):** In `load_resources`, derived Conditions MUST
  be appended to the row list (single bulk INSERT), not per-row
  `_insert_resource`. FDD §4.7 now states this explicitly.
- **S3 (list-aware walker):** `_walk_path_list_aware()` handles 0, 1,
  and N list-element matches. Multiple `content[]` entries are
  concatenated with `\n\n` before NER.
- **S4 (cache key for spans):** Section title is NOT part of the
  SapBERT cache key. SapBERT search is purely lexical+semantic on
  span text; section-based filtering happens BEFORE SapBERT, so the
  cache key correctly omits section. FDD Open Question 6 closed.
- **S5 (`derived-from-text` extension):** New module
  `derived_from_text_extension.py` mirrors Phase 2's
  `autocoding_extension.py`. 6 sub-extensions with pinned URLs + value
  types (`source-path`, `section-title`, `span-start`, `span-end`,
  `ner-model`, `sectionizer-version`).
- **S6 (loop prevention):** `ClinicalNotesPipeline._visited` set
  tracks derived `(resourceType, id)` pairs to break any future loop
  if `Condition` is added to `note_paths`.
- **S7 (performance budget re-validated):** 300 ms/note target
  achievable on tested models; performance test gates at 330 ms
  (10% slack). Larger scispaCy model (`en_core_sci_lg`) will break
  the budget; documented.
- **S8 (multi-process):** DuckDB single-writer; multiprocessing recipe
  documented but not implemented in v1.

## 4. Critical Engineer pre-flight

Before any code change:

1. Confirm `medspacy` and `d4data/biomedical-ner-all` are installable
   in the dev environment. Run:
   ```bash
   pip install -e ".[ner,dev]"
   python -m spacy download en_core_sci_sm
   ```
2. Grep for existing callers of `AutoCoder._lookup_or_search` etc. —
   the extraction in §4.4 must not break any current caller.
   ```bash
   grep -rn '_lookup_or_search\|_filter_and_truncate\|_result_to_dict' \
     fhir4ds/ conformance/ tests/
   ```
3. Verify the DuckDB version supports `INSERT OR REPLACE` on the
   `autocoding_cache` PK (already used in Phase 2; preserved).

## 5. Files touched

**New (6):**
- `fhir4ds/cql/loader/section_allowlist.py`
- `fhir4ds/cql/loader/derived_from_text_extension.py`
- `fhir4ds/cql/loader/search_helpers.py` (extracted from `auto_coder.py`)
- `fhir4ds/cql/loader/notes_ner.py`
- `fhir4ds/cql/loader/notes_pipeline.py`
- `fhir4ds/cql/tests/fixtures/notes/synthetic_notes.ndjson` + `expected_spans.json`

**New tests (6):**
- `fhir4ds/cql/tests/unit/loader/test_section_allowlist.py`
- `fhir4ds/cql/tests/unit/loader/test_derived_from_text_extension.py`
- `fhir4ds/cql/tests/unit/loader/test_search_helpers.py`
- `fhir4ds/cql/tests/unit/loader/test_notes_ner_unit.py`
- `fhir4ds/cql/tests/unit/loader/test_notes_pipeline_unit.py`
- `fhir4ds/cql/tests/unit/loader/test_fhir_loader_ner_integration.py`
- `fhir4ds/cql/tests/integration/test_notes_ner_loader.py`

**Modified (4):**
- `fhir4ds/cql/loader/auto_coder.py` (refactor: delegate to search_helpers)
- `fhir4ds/cql/loader/fhir_loader.py` (add `notes_pipeline` kwarg + hook)
- `pyproject.toml` (add `[fhir4ds,ner]` extra)
- `docs/getting-started/ner.md` (new setup instructions — Engineer creates)

## 6. Verification gates

- **Unit (stubbed):** `pytest fhir4ds/cql/tests/unit/loader/ -v`
- **Zero-dep default:** `python3 -c "import fhir4ds"` succeeds without
  `[fhir4ds,ner]` installed.
- **Regression (mandatory):** `python3 conformance/scripts/run_all.py` → still **2822/2822**.
- **Phase 2 + Phase 3 regression:** All existing tests pass unchanged
  through the `auto_coder.py` refactor.
- **Integration (if live medterm4ds + medspacy):**
  `MEDTERM4DS_TEST_URL=http://127.0.0.1:8001 pytest fhir4ds/cql/tests/integration/test_notes_ner_loader.py -v`
- **Performance gate:** single-note latency ≤ 330 ms (10% slack on 300 ms target).

## 7. Out of scope

- Phase 5 (streaming-readiness hardening) — separate FDD.
- Phase 4.5 follow-on: plumbing `ner_config=` through
  `evaluate_measure()` / `execute_cql()` for top-level ergonomics.
- v2 fine-tuned Bio_ClinicalBERT NER — Phase 5.
- Browser-side NER (Transformers.js + WASM) — research track only.
- Multiprocessing batch coordination logic — Phase 5 (recipe documented
  only).

## 8. Handoff

Pre-approved by `USER_DIRECTIVES.md` Phase 4 section. Engineer may
proceed to implementation without further approval. Update
`evolution.json` to `phase: "implementation"` on first code change.

The user will pause before implementation to consider Open Questions
1-6 in §9 of the FDD. None block implementation start — defaults are
documented for each.
