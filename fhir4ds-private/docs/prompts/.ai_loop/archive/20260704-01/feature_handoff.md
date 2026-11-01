# Feature Handoff - medterm4ds Phase 4: Clinical Notes NER Extension

**Handoff date:** 2026-07-03
**Phase:** 4 of 4 (Clinical Notes NER Extension)
**Target version:** 0.0.12
**FDD:** `docs/architecture/plans/FEATURE_MEDTERM4DS_PHASE4_NER.md` (SCOPE REDUCTION block §0 governs scope)
**Conformance:** 2822/2822 (zero regression — INV-1 satisfied)

---

## 1. Files added

| File | Purpose | LOC |
|------|---------|-----|
| `fhir4ds/cql/loader/notes_text_extractor.py` | `DEFAULT_NOTE_PATHS`, `NoteText` dataclass, `extract_note_texts(resource, note_paths=None)` — dotted-path walker with `.data` base64-decode, `[N]` indexing, `[]` wildcard fan-out | ~280 |
| `fhir4ds/cql/loader/derived_from_text_extension.py` | `DERIVED_FROM_TEXT_EXTENSION_URL`, `build_derived_from_text_extension(...)`, `parse_derived_from_text_extension(resource)`, `is_derived_from_text(resource)` — 5-field provenance extension (source-ref, source-path, span-start, span-end, matched-text) | ~165 |
| `fhir4ds/cql/loader/notes_pipeline.py` | `NotesPipelineConfig`, `NotesPipeline` — orchestrator: lazy-loads medterm4ds, calls `extract(text, format="codes", ...)`, wraps affirmed concepts in Conditions with both Phase 2 autocoding (engine=`medterm4ds-ner`) and Phase 4 derived-from-text extension. Deterministic id via sha256(`salt, source_ref, span_start, span_end, code`)[:32]. Source mnemonic → FHIR URL normalization reuses Phase 1's `_SOURCE_MNEMONIC_TO_URL` map | ~340 |
| `fhir4ds/cql/tests/unit/loader/test_notes_text_extractor.py` | 13 unit tests — plain path, nested base64, list wildcard, missing path, missing intermediate key, resource-type-not-in-map, custom override, source-ref provenance, out-of-bounds index, invalid base64 | ~205 |
| `fhir4ds/cql/tests/unit/loader/test_derived_from_text_extension.py` | 7 unit tests — exact shape, round-trip, all-5-fields-present, absence, predicate, negative-offset rejection, int-like coercion | ~125 |
| `fhir4ds/cql/tests/unit/loader/test_notes_pipeline.py` | 16 unit tests (incl. 5-way parametrized system normalization) — affirmed/negated/uncertain filtering, include_negated opt-in, Condition-on-Condition skip (INV-4), medterm4ds-extract-raises containment (INV-3), deterministic id (same + different sources), system normalization, both extensions present, distinct URLs | ~225 |
| `fhir4ds/cql/tests/unit/loader/test_fhir_loader_notes_integration.py` | 7 integration tests — `notes_pipeline=None` byte-identical baseline (CRITICAL invariant), default is None, batch-path byte-identical, load_resource/load_resources both append derived Conditions, disabled-pipeline degrades to no-op | ~155 |

## 2. Files modified

| File | Change |
|------|--------|
| `fhir4ds/cql/loader/fhir_loader.py` | Added `notes_pipeline: Optional[NotesPipeline] = None` kwarg to `__init__`. Wired `extract_conditions` into both `load_resource` (single-row path) and `load_resources` (batch path). Derived Conditions participate in same dedup-by-(id, resourceType) as source resources. With `notes_pipeline=None`, both paths are byte-identical to pre-Phase-4 (CRITICAL invariant — verified by `test_notes_pipeline_none_byte_identical_to_baseline`). NotesPipeline imported only under `TYPE_CHECKING`. |
| `fhir4ds/cql/loader/__init__.py` | Exported `NotesPipeline`, `NotesPipelineConfig`, `DEFAULT_NOTE_PATHS`, `NoteText`, `extract_note_texts`, `DERIVED_FROM_TEXT_EXTENSION_URL`, `build_derived_from_text_extension`, `parse_derived_from_text_extension`, `is_derived_from_text` |
| `pyproject.toml` | Added `[fhir4ds,ner]` extra = `medterm4ds[extraction]`. No new direct deps on medspacy/spacy/transformers/torch. |

## 3. Test pass counts

| Suite | Before | After | Δ |
|-------|--------|-------|---|
| `fhir4ds/cql/tests/unit/loader/` | 70 | **105** | +35 (new) |
| `fhir4ds/cql/tests/unit/` (full regression) | 1351 | **1386** | +35 (no regressions) |
| Conformance (ViewDefinition + FHIRPath + CQL + DQM) | 2822 | **2822** | 0 |

All new tests run without medterm4ds installed (medterm4ds is mocked via `monkeypatch.setitem(sys.modules, ...)`). The `import fhir4ds` smoke test also runs without medterm4ds.

## 4. Conformance before/after

Before: **2822/2822** (100.0%) — ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47.
After: **2822/2822** (100.0%) — identical. Zero regression.

## 5. Invariants satisfied

* **INV-1 (zero-dep default)**: `python3 -c "import fhir4ds"` succeeds with no medterm4ds installed. `medterm4ds` imported only inside `NotesPipeline._ensure_medterm4ds()`.
* **INV-3 (never raise from extract_conditions)**: All exceptions caught, logged WARNING, return `[]`. Verified by `test_medterm4ds_extract_raises_returns_empty`, `test_extract_conditions_never_raises_on_bad_resource`.
* **INV-4 (no Condition-on-Condition)**: `resourceType == "Condition"` short-circuits to `[]`. Verified by `test_source_resource_condition_is_skipped`.
* **INV-6 (deterministic Condition ids)**: sha256(`salt, source_ref, span_start, span_end, code`)[:32]. Verified by `test_deterministic_id_same_source_same_concept` and `test_deterministic_id_differs_across_different_sources`.
* **INV-7 (system URL normalization)**: `SNOMEDCT_US → http://snomed.info/sct`, `RXNORM → http://www.nlm.nih.gov/research/umls/rxnorm`, `LNC → http://loinc.org`, `ICD10CM → http://hl7.org/fhir/sid/icd-10-cm`, `CPT → http://www.ama-assn.org/go/cpt` (parametrized test, 5 cases).
* **CRITICAL (notes_pipeline=None byte-identical)**: Verified by `test_notes_pipeline_none_byte_identical_to_baseline` — full SQL row dump matches baseline exactly.
* **No new direct heavy deps**: pyproject `ner` extra pulls only `medterm4ds[extraction]`; medspacy/spacy/transformers/torch remain transitive through medterm4ds.

## 6. Deviations from FDD

* **Mnemonic map reuse**: FDD §0 INV-7 says "use Phase 1's mnemonic→URL logic via `SystemResolver`." The actual mnemonic map lives in `fhir4ds/cql/terminology/in_process_adapter._SOURCE_MNEMONIC_TO_URL` (Phase 1 REV-003 remediation), not on `SystemResolver` directly. `NotesPipeline._normalize_system()` imports that map and then flows through `SystemResolver.normalize()` for OID/SNOMED-module normalization — same logical two-pass behavior as `InProcessTerminologyEndpoint._normalize_system`. Justification: avoid duplicating UMLS-specific terminology knowledge in two modules.
* **`_DISABLED_SENTINEL`**: When medterm4ds is missing on first call, `extract_conditions` logs once and caches a sentinel so subsequent calls short-circuit without re-trying the import. This keeps batch loads fast when the pipeline is misconfigured but preserves the no-op-on-failure invariant (INV-3).
* **`base64.b64decode(validate=True)`**: Initial implementation used `validate=False` (lenient — drops non-alphabet chars silently); `validate=True` is required to actually reject malformed payloads as the FDD requires. Fixed after `test_base64_invalid_payload_is_skipped_silently` flagged it.
* **Empty subject copy**: When the source resource has no `subject` field, the derived Condition omits `subject` entirely (rather than writing `subject: {}`). Subject is only attached when `subject.reference` is a non-empty string.
* **Index-version probe**: `NotesPipeline._ensure_medterm4ds` looks for `medterm4ds.__index_version__` then `medterm4ds.get_index_version()`. If neither exists, the autocoding extension falls back to `index_version="unknown"` (consistent with Phase 2 behavior).

## 7. Known issues for reviewer

* **REV-001 candidate (LOW)** — `notes_pipeline.py:_normalize_system` imports `_SOURCE_MNEMONIC_TO_URL` (underscore-prefixed = private) from `in_process_adapter`. This couples Phase 4 to a Phase 1 implementation detail. Consider promoting the mnemonic map to a shared location (e.g. `fhir4ds/cql/terminology/mnemonics.py`) in a future refactor so both consumers import from a stable public surface.
* **REV-002 candidate (LOW)** — `_medterm4ds_engine_version()` calls `importlib.metadata.version("medterm4ds")` on every Condition build. Cheap, but in a tight loop building thousands of Conditions, cache it once on the pipeline instance.
* **`extract_note_texts` path grammar**: Supports `.`, `[N]`, `[]`. Does NOT support FHIRPath-style predicates like `code=...` or descendant traversal. Sufficient for the FDD's configured paths; document if extended.
* **No live medterm4ds smoke test**: All pipeline tests mock medterm4ds. A live integration test belongs in medterm4ds's own suite (per the SCOPE REDUCTION, medterm4ds owns the NLP cascade). fhir4ds's responsibility is the wiring, which is fully covered.

## 8. Self-check commands (all green)

```
$ python3 -c "import fhir4ds"
$ python3 -c "from fhir4ds.cql.loader.notes_pipeline import NotesPipeline, NotesPipelineConfig; print('ok')"
ok
$ python3 -m pytest fhir4ds/cql/tests/unit/loader/ -v
============================= 105 passed ==============================
$ python3 -m pytest fhir4ds/cql/tests/unit/ 2>&1 | tail -1
============================ 1386 passed =============================
$ python3 conformance/scripts/run_all.py 2>&1 | tail -1
SUCCESS: 100% Spec Conformance Achieved!   (2822/2822)
```
