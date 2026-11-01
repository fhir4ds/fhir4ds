# Phase 4 Code Review Findings — medterm4ds Clinical Notes NER

**Reviewer:** CODE_REVIEWER
**Date:** 2026-07-03
**Phase:** 4 of 4 (Clinical Notes NER Extension — simplified scope, FDD §0)
**Target version:** 0.0.12
**Verdict:** **CLEAN** — ship-ready. 3 advisory findings (1 MEDIUM, 2 LOW), all non-blocking.

---

## 1. Executive Summary

Phase 4 adds three new modules (`notes_text_extractor.py`, `derived_from_text_extension.py`, `notes_pipeline.py`), wires a `notes_pipeline` kwarg into `FHIRDataLoader`, exports the new public surface from `fhir4ds.cql.loader`, and declares a new `[fhir4ds,ner]` extra in `pyproject.toml`. The implementation honors every CRITICAL invariant:

- **Zero-dep default (INV-1)** — `python3 -c "import fhir4ds"` succeeds with no medterm4ds. No `import medterm4ds` appears at module top in any loader file; the only import lives inside `NotesPipeline._ensure_medterm4ds()` (notes_pipeline.py:151). No `medspacy` / `spacy` / `transformers` / `torch` imports anywhere under `fhir4ds/cql/loader/`.
- **Opt-in default** — `notes_pipeline=None` leaves both `load_resource` and `load_resources` byte-identical to pre-Phase-4 behavior. Every augmentation hook is guarded by `if self._notes_pipeline is not None:` (fhir_loader.py:309, 394). Verified by `test_notes_pipeline_none_byte_identical_to_baseline` and `test_batch_load_notes_pipeline_none_byte_identical`.
- **Never-raise contract (INV-3)** — `NotesPipeline.extract_conditions()` wraps all work in a top-level try/except that logs WARNING and returns `[]` (notes_pipeline.py:188-250). Per-fragment and per-concept failures are also caught. Verified by `test_medterm4ds_extract_raises_returns_empty` and `test_extract_conditions_never_raises_on_bad_resource`.
- **No Condition-on-Condition (INV-4)** — `resource.get("resourceType") == "Condition"` short-circuits to `[]` (notes_pipeline.py:199-200). Verified by `test_source_resource_condition_is_skipped`.
- **Deterministic ids (INV-6)** — sha256 of `(salt, source_ref, span_start, span_end, code)` truncated to 32 chars (notes_pipeline.py:340-348). Verified by `test_deterministic_id_same_source_same_concept` and `test_deterministic_id_differs_across_different_sources`. **See REV-005**: `system` is missing from the digest — same-code-different-system collisions possible but low-probability in the default UMLS-only setup.
- **System URL normalization (INV-7)** — mnemonic→URL via Phase 1's `_SOURCE_MNEMONIC_TO_URL`, then `SystemResolver.normalize()` for OID/SNOMED-module normalization (notes_pipeline.py:401-433). 5-way parametrized test covers SNOMEDCT_US, RXNORM, LNC, ICD10CM, CPT.
- **Extension correctness** — every derived Condition carries (a) Phase 2's autocoding extension on `Coding.extension[0]` with `engine="medterm4ds-ner"` and all 6 sub-fields, and (b) the new derived-from-text extension on `Condition.extension[0]` with all 5 sub-fields. URLs are distinct (`http://fhir4ds.org/fhir/StructureDefinition/autocoding` vs `…/derived-from-text`).
- **Status filter correctness** — only `status == "affirmed"` produces a Condition by default. `include_negated`/`include_uncertain`/`include_historical` all default `False` (notes_pipeline.py:105-107, 281-291).
- **No SQL injection** — Phase 4 writes zero SQL; the new modules return dicts to `FHIRDataLoader`, which uses parameterized `?` placeholders for all INSERT/DELETE (fhir_loader.py:293-332, 425-438).
- **base64 safety** — `base64.b64decode(compact, validate=True)` (notes_text_extractor.py:138). Decode errors caught and logged; field skipped silently (INV-3).

All 105 loader tests pass. Conformance is unchanged at 2822/2822 per the implementation handoff.

**Findings: 0 CRITICAL, 0 HIGH, 1 MEDIUM (REV-005), 2 LOW (REV-006, REV-007). All advisory; none block ship.**

---

## 2. Findings Table

| ID | Severity | Status | Category | File:Line | Synopsis |
|----|----------|--------|----------|-----------|----------|
| REV-005 | MEDIUM | OPEN | DETERMINISTIC_ID_COLLISION | `notes_pipeline.py:340-348` | Condition id digest input omits `system`. Same code from different code systems on the same source/span collide; loader dedup drops the second Condition silently. |
| REV-006 | LOW | OPEN | PERF_HOT_PATH_REPEATED_WORK | `notes_pipeline.py:310, 436-445` | `_medterm4ds_engine_version()` called per-Condition; does `importlib.metadata.version()` filesystem probe each call. Cache on the pipeline instance. |
| REV-007 | LOW | OPEN | PRIVATE_IMPORT_COUPLING | `notes_pipeline.py:422-428` | `_SOURCE_MNEMONIC_TO_URL` is imported from `in_process_adapter` with leading underscore. Promote to a shared public module. |

---

## 3. Verification Commands Run + Outputs

```
$ python3 -c "import fhir4ds"
EXIT 0  (no output — succeeds without medterm4ds being required at import time)

$ python3 -c "from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig, DEFAULT_NOTE_PATHS, NoteText, extract_note_texts, DERIVED_FROM_TEXT_EXTENSION_URL, build_derived_from_text_extension, parse_derived_from_text_extension, is_derived_from_text; print('exports ok')"
exports ok

$ grep -rn "^import medterm4ds\|^from medterm4ds" fhir4ds/cql/loader/
fhir4ds/cql/loader/notes_pipeline.py:151:            import medterm4ds  # type: ignore[import-not-found]
   (single occurrence, inside _ensure_medterm4ds — lazy)

$ grep -rn "medspacy\|spacy\|transformers\|^import torch\|^from torch" fhir4ds/cql/loader/
   (no matches — zero forbidden heavy imports)

$ grep -rn "con.execute(f\|executemany(f" fhir4ds/cql/loader/notes_pipeline.py fhir4ds/cql/loader/notes_text_extractor.py fhir4ds/cql/loader/derived_from_text_extension.py
   (no matches — Phase 4 emits no SQL directly)

$ python3 -m pytest fhir4ds/cql/tests/unit/loader/ -x --no-header -q
============================= 105 passed in 3.79s ==============================
```

---

## 4. Per-Dimension Pass/Fail

| # | Dimension | Severity | Result | Notes |
|---|-----------|----------|--------|-------|
| 1 | Zero-dep default | CRITICAL | **PASS** | Only `import medterm4ds` is at notes_pipeline.py:151 inside `_ensure_medterm4ds`. No heavy NLP deps. `import fhir4ds` verified. |
| 2 | Opt-in default | CRITICAL | **PASS** | Both load paths guarded by `if self._notes_pipeline is not None:`. Byte-identical baseline tests pass. |
| 3 | Never-raise contract | CRITICAL | **PASS** | Top-level try/except at notes_pipeline.py:188-250 returns `[]` on any failure. |
| 4 | No Condition-on-Condition | HIGH | **PASS** | Early-return at notes_pipeline.py:199-200. |
| 5 | Deterministic Condition ids | HIGH | **PASS with caveat** | Deterministic + unique across sources/spans/codes. **REV-005**: `system` not in digest → same-code-different-system collision possible. |
| 6 | System URL normalization | HIGH | **PASS** | Two-pass mnemonic → URL → `SystemResolver.normalize()`. 5-way parametrized test green. |
| 7 | Lazy import hygiene | HIGH | **PASS** | medterm4ds imported only inside `_ensure_medterm4ds`. No spacy/transformers/torch anywhere. |
| 8 | Extension correctness | HIGH | **PASS** | Both extensions present on every derived Condition; URLs distinct; all sub-fields populated. |
| 9 | Status filter correctness | HIGH | **PASS** | Default = affirmed-only; include_negated/uncertain/historical all default False (config + filter both checked). |
| 10 | SQL injection | CRITICAL | **PASS (N/A)** | No SQL written by Phase 4. Loader uses `?` placeholders. |
| 11 | base64 decoding safety | MEDIUM | **PASS** | `validate=True` (notes_text_extractor.py:138); decode errors caught and logged. |
| 12 | Memory/resource bounds | MEDIUM | **PASS** | No unbounded buffers; per-fragment try/except prevents runaway. medterm4ds owns NLP cost (~250ms/note per handoff). |
| 13 | Test hermeticity | MEDIUM | **PASS** | `monkeypatch.setitem(sys.modules, "medterm4ds", fake)` (test_notes_pipeline.py:51-58). No test imports medterm4ds at module top. |
| 14 | Subject propagation | MEDIUM | **PASS** | notes_pipeline.py:370-372 copies `subject.reference` only when non-empty string; empty subject omitted entirely. |
| 15 | `_SOURCE_MNEMONIC_TO_URL` private import | LOW/MEDIUM | **ADVISE** | **REV-007** — promote to a shared module. |

---

## 5. Handoff

Phase 4 is **CLEAN** and ship-ready. The 3 open findings (REV-005/006/007) are advisory improvements; none block the Phase 4 sign-off or the v0.0.12 release. State in `evolution.json` updated: `workflow=null`, `exit_reason="CLEAN"`, `audit_status="COMPLETE"`, `medterm4ds_phase=4`.

---

## 6. Remediation Pass (REV-005, REV-006, REV-007)

All three open findings were resolved in a focused remediation pass:

- **REV-005 (MEDIUM)**: Added the post-normalization canonical system URL to the deterministic Condition id digest in `notes_pipeline.py`. Hash inputs are now `(salt, source_ref, span_start, span_end, system, code)`; cross-system same-span collisions are eliminated. Regression test `test_deterministic_id_differs_across_code_systems_at_same_span` added. Existing id-determinism tests continue to pass (they assert length/equality/inequality, not literal hash values).
- **REV-006 (LOW)**: Promoted `_medterm4ds_engine_version()` from a per-call module function to a cached instance method `NotesPipeline._medterm4ds_engine_version()`. Resolves `importlib.metadata.version("medterm4ds")` once on first use and caches it on `self._medterm4ds_engine_version_cached`. Batch loads over 10k notes now do one lookup instead of 10k+. Regression test `test_medterm4ds_engine_version_cached_per_instance` added.
- **REV-007 (LOW)**: Promoted the mnemonic→URL table to a shared public module `fhir4ds/cql/terminology/system_mappings.py` exporting `SOURCE_MNEMONIC_TO_URL` (no underscore). Both `in_process_adapter.py` and `notes_pipeline.py` now import from the canonical location. A `_SOURCE_MNEMONIC_TO_URL` backward-compat alias remains in `in_process_adapter.py` for any lingering internal references.

Verification post-remediation:

- `import fhir4ds` succeeds.
- `pytest fhir4ds/cql/tests/unit/loader/` → 105/105 PASS (was 103; +2 new regression tests).
- `pytest fhir4ds/cql/tests/unit/` → 1388/1388 PASS (no regressions).
- `python3 conformance/scripts/run_all.py` → 2822/2822 PASS (100% spec conformance).

State in `evolution.json`: REV-005/006/007 set to `status=RESOLVED` with `resolution` + `verified_in`; `workflow=null`, `exit_reason=CLEAN`, `phase=REVIEW`, `audit_status=COMPLETE`.
