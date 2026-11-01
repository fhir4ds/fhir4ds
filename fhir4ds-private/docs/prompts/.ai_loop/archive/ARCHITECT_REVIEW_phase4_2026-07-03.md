# ARCHITECT SELF-AUDIT — medterm4ds Phase 4 (Clinical Notes NER Extension)

**Audited:** `FEATURE_PLAN_DRAFT.md` (Phase 4) against current `dev` codebase
(post-Phase-1 + Phase-2 + Phase-3)
**Date:** 2026-07-03
**Standards:** `ROLE_ARCHITECT.md`, `GLOBAL_RULES.md`, master plan §Phase 4 + Open Questions 1-5

---

## Falsifiable Invariants

The Phase 4 implementation MUST preserve every one of the following.
Each invariant is stated so that a single test can prove or disprove it.

### INV-1 — Zero-dependency default (Phase 1 INV-1 preserved)
**Statement:** `python3 -c "import fhir4ds"` succeeds in a fresh venv
with only core dependencies installed (no `medspacy`, `spacy`,
`transformers`, `torch`, `httpx`). Module-level imports of
`fhir4ds.cql.loader.notes_ner`,
`fhir4ds.cql.loader.notes_pipeline`, and
`fhir4ds.cql.loader.section_allowlist` also succeed (all NER-specific
imports are lazy — inside `__init__` or method bodies).
**Test:** Fresh venv, `pip install -e .` (core only), run
`python3 -c "from fhir4ds.cql.loader.notes_pipeline import ClinicalNotesPipeline; print('OK')"`.
Must succeed. Instantiating `ClinicalNotesPipeline(...)` without
`[fhir4ds,ner]` raises `ImportError` with install hint.

### INV-2 — `notes_pipeline=None` is byte-identical to pre-Phase-4
**Statement:** When `notes_pipeline=None` (the default),
`FHIRDataLoader.load_resource` / `load_resources` produce
byte-identical DuckDB rows to the current `dev` HEAD on every
existing fixture and conformance test.
**Test:** Capture resource-table JSON before and after the Phase 4
diff with `notes_pipeline=None`; assert bytewise equality.
**Failure signal:** any conformance test count change other than the
new NER-gated suite.

### INV-3 — Negation filter precision ≥ 95% on synthetic test set
**Statement:** On the synthetic test bundle
(`fhir4ds/cql/tests/fixtures/notes/synthetic_notes.ndjson`), at most
1 of every 20 expected-negated spans slips through to a derived
Condition. ConText modifier tagging + section allow-list together
filter ≥ 95% of negated/uncertain/historical mentions.
**Test:** Run the pipeline over the synthetic bundle; for each
derived Condition, check the source span against
`expected_spans.json`; count false positives; assert
`fp / total_expected_negated ≤ 0.05`.
**Caveat:** The synthetic test set is small (~10 notes). The 95%
target is measured against this set, not against real clinical text.
The FDD documents this as a synthetic-precision gate, not a
production-precision claim.

### INV-4 — Every derived Condition carries `evidence.detail`
**Statement:** Every Condition produced by
`ClinicalNotesPipeline.derive_conditions()` has a non-empty
`evidence.detail` list with at least one entry of the form
`{"reference": "{source_resourceType}/{source_id}"}`. The reference
resolves to a resource that exists in the same DuckDB load batch.
**Test:** Walk derived Conditions from a small DocumentReference
fixture; assert each has `evidence.detail[0].reference ==
f"DocumentReference/{source_id}"`.

### INV-5 — Every derived Condition has verificationStatus + clinicalStatus
**Statement:** Every derived Condition has
`verificationStatus.coding[0].code == "unconfirmed"` (system
`http://terminology.hl7.org/CodeSystem/condition-ver-status`) AND
`clinicalStatus.coding[0].code == "active"` (system
`http://terminology.hl7.org/CodeSystem/condition-clinical`). Both
fields are configurable via `ClinicalNotesConfig.derived_clinical_status`
/ `derived_verification_status`; the defaults are the documented
values.
**Test:** Walk derived Conditions; assert both fields match the
defaults; then change the config and assert both fields track the
config.

### INV-6 — Source resources are NOT mutated
**Statement:** After `ClinicalNotesPipeline.derive_conditions(resource)`
returns, `resource` (the input dict) is deep-equal to its pre-call
snapshot. The pipeline reads from the source but writes only to NEW
derived Condition dicts. Source resources reach DuckDB unchanged.
**Test:** Deep-copy source resource before pipeline call; run
pipeline; assert `snapshot == resource` (deep equality).

### INV-7 — Section allow-list excludes Allergies / social history by default
**Statement:** `DEFAULT_SECTION_ALLOWLIST` does NOT contain "Allergies",
"Social History", "Family History", "Review of Systems", or any other
section where entity mentions would produce false-positive problem
coding. Mentions in those sections produce zero derived Conditions
under default config.
**Test:** Synthetic note with an "Allergies: penicillin" section →
no derived Condition with `code.coding[0].display` matching
"penicillin". Override the allow-list to include "Allergies" →
penicillin IS coded.

### INV-8 — NER pipeline never raises out of the loader
**Statement:** `ClinicalNotesPipeline.derive_conditions(resource)`
catches all exceptions, logs at WARNING, and returns `[]`. No input
— truncated UTF-8, missing subject, malformed dict, NER model OOM,
SapBERT timeout, DuckDB write failure — causes an exception to
escape into `FHIRDataLoader.load_resource`. A single bad note does
not break the load. Mirrors Phase 2 INV-9.
**Test:** Inject a NER instance whose `extract_spans()` raises
`RuntimeError`; inject a resource missing `subject`; inject a
resource that is not a dict; assert `derive_conditions` returns
`[]` in each case with a WARNING log.

### INV-9 — Category mapping is data-driven and overridable
**Statement:** The NER-type → medterm4ds-category mapping is a
module-level dict in `notes_pipeline.py` (`NER_TYPE_TO_CATEGORY`).
`ClinicalNotesConfig.ner_type_overrides` merges into the default
map at instance construction. Unknown NER types log DEBUG and are
skipped (no derived Condition).
**Test:** Override `ner_type_overrides={"Gene": "condition"}`;
verify a span with `entity_type="Gene"` is now mapped to
`category="condition"` and produces a derived Condition.

---

## Skeptical Notes

**S1. The `AutoCoder` private helpers (`_lookup_or_search`,
`_filter_and_truncate`, `_result_to_dict`) are reused by the NER
pipeline but are private (`_`-prefixed).**

Two options for the Engineer:

- **Option A (minimal churn):** The NER pipeline holds an `AutoCoder`
  instance and accesses `_lookup_or_search` etc. directly. Works but
  couples Phase 4 to Phase 2's private API.
- **Option B (cleaner):** Extract the shared helpers into a new module
  `fhir4ds/cql/loader/search_helpers.py` and have both `AutoCoder`
  and `ClinicalNotesPipeline` import from it. Slight Phase 2
  refactor; preserves the public surface.

**Recommendation:** Option B. The extraction is small (~80 lines),
removes a private-API coupling, and makes future Phase 5 work (refresh
sweeps over both auto-coding paths) cleaner. Engineer confirms.

**S2. The pipeline produces derived Conditions inside the loader's
per-resource loop. What if a source resource produces 50 derived
Conditions (a long note with many spans)?**

The current FDD has the loader insert each derived Condition via
`_insert_resource(d)` inside the loop. For a 50-span note, this is 50
DuckDB writes per source resource — slow under DuckDB's per-row INSERT
cost.

**Mitigation:** Batch the derived Conditions into the same
`load_resources` row list as the source. Engineer: instead of
`self._insert_resource(d)` per derived Condition, append derived
Conditions to the row list being built in `load_resources`, then
single bulk INSERT. The FDD already implies this ("derived Conditions
MUST be added to the same batch list") — make it explicit in the
implementation.

**S3. The base64-decode path in `_extract_text()` couples Phase 4 to
specific resource shapes. What if a DocumentReference has multiple
`content[]` entries?**

The `_walk_path_list_aware()` helper must collect ALL list-element
matches, not just the first. For `content[].attachment.data` with
3 entries, all 3 are base64-decoded and concatenated with `\n\n`
separators before NER. Engineer confirms the list-aware walker
handles 0, 1, and N list elements correctly.

**S4. Cache key for SapBERT span search: should it include section
title?**

The Phase 2 cache key is `(text_hash, category, search_mode,
index_version)`. Span text is normalized before hashing. The same
span text ("diabetes") in different sections hashes to the same key —
so a cache hit returns the same SapBERT result regardless of section.

This is correct: the SapBERT search is purely lexical+semantic on the
span text; section context doesn't change what concept "diabetes"
maps to. Section-based filtering happens BEFORE SapBERT (in the
ConText + section-allow-list stage), so the cache key correctly omits
section.

Open Question 6 in the FDD raises this; the audit confirms: omit
section from cache key. Engineer implements accordingly.

**S5. The `derived-from-text` extension shape isn't fully specified.**

The FDD lists 6 sub-extensions (`source-path`, `section-title`,
`span-start`, `span-end`, `ner-model`, `sectionizer-version`). The
audit recommends pinning the exact URLs and value types in a new
module `fhir4ds/cql/loader/derived_from_text_extension.py` (mirrors
Phase 2's `autocoding_extension.py`):

| Sub-extension | URL | Value type |
|---------------|-----|-----------|
| source-path | `source-path` | `valueString` |
| section-title | `section-title` | `valueString` |
| span-start | `span-start` | `valueInteger` |
| span-end | `span-end` | `valueInteger` |
| ner-model | `ner-model` | `valueString` |
| sectionizer-version | `sectionizer-version` | `valueString` |

Engineer creates this module parallel to `autocoding_extension.py`.

**S6. Recursive load: derived Conditions may themselves match
`note_paths`.**

Derived Conditions have no note-bearing paths (they have `code`,
`subject`, `evidence` — none of which are in `DEFAULT_NOTE_PATHS`).
So the recursive load is safe — derived Conditions flow through
`load_resource` cleanly, the pipeline sees no note paths for them,
and no further derivation happens.

**Defensive measure:** Track visited `(resourceType, id)` pairs in
the pipeline instance to break any future loop. Engineer adds a
`WeakSet` on the pipeline.

**S7. Performance budget is tight (300 ms/note). The audit
re-validates the breakdown:**

| Stage | Target | Risk |
|-------|--------|------|
| `_extract_text` + base64 decode | 1 ms | stdlib, deterministic |
| medspaCy pipeline | 30 ms | depends on `en_core_sci_sm`; if user installs `en_core_sci_lg` (~700 MB), this jumps to ~80 ms. Document. |
| HuggingFace NER | 150 ms | `d4data/biomedical-ner-all` is the tested model. Swapping models changes this. Document. |
| SapBERT search × avg 3 spans | 100 ms | cache amortizes; first-load is slower |
| DuckDB INSERT | 16 ms | batch path; per-row would be ~5 ms × N |

The audit confirms the 300 ms budget is achievable on the tested
models. The performance test (§5.6) gates at 330 ms (10% slack).

**S8. Multi-process parallelism — FDD defers to docs. The audit
confirms this is acceptable for v1:**

The DuckDB connection is single-writer; multi-process would need a
writer lock or partitioned connections. The FDD's recommendation
(one `ClinicalNoteNER` per worker, serialized DuckDB writes) is
correct. Document the recipe; do not implement coordination logic in
v1.

---

## Verdict

**APPROVE for refinement to v2.** All 9 invariants are testable. The
two material findings (S1 helper extraction, S2 batch insert) are
implementation-level refinements that the FDD permits; the audit
recommends Option B (helper extraction) and explicit batch-insert
wording. No design-level defects.

Open Questions 1-6 in the FDD are appropriate user-pause material;
none block implementation start (defaults are documented).
