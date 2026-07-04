# FEATURE DESIGN — medterm4ds Phase 4: Clinical Notes NER Extension

**Status:** APPROVED (pre-approved via `USER_DIRECTIVES.md`; architecture self-audit complete — see `fhir4ds-private/docs/prompts/.ai_loop/ARCHITECT_REVIEW.md`)
**Source plan:** `fhir4ds-private/docs/plans/medterm4ds-integration.md` (Phase 4 §, lines 220-278; Open Questions, lines 279-303)
**Verified against codebase:** 2026-07-03 (post Phase 1 + Phase 2 + Phase 3 landing)
**Target version:** 0.0.12
**Scope:** Phase 4 ONLY. Phase 5 (streaming-readiness) deferred.

---

## 0. SCOPE REDUCTION — 2026-07-03 (author)

**The NLP pipeline moved to medterm4ds.** medterm4ds now ships a public
`extract()` API that runs the full medspaCy + NER + SapBERT cascade and returns
typed `ExtractedConcept` objects. Phase 4 in fhir4ds collapses to **three
responsibilities**:

1. **Text extraction** from configured FHIR note paths (base64 decode + walker).
2. **Call `medterm4ds.extract(text, format="codes", ...)`** — one function call.
3. **Wrap results in FHIR Condition resources** with the autocoding extension
   (reuse Phase 2's `autocoding_extension` builder) plus a new
   `derived-from-text` provenance extension.

**What fhir4ds NO LONGER builds (was in the original FDD below):**
- `notes_ner.py` with `ClinicalNoteNER`, `NERConfig`, `extract_spans()`
- `section_allowlist.py` (medspaCy Sectionizer lives in medterm4ds)
- Direct medspaCy / HuggingFace / SapBERT integration
- NER-type → category mapping (medterm4ds handles this internally)
- Token-merging post-processing (medterm4ds handles this)

**What stays the same:**
- FHIR text-path extraction (`notes_text_extractor.py`)
- Derived-Condition construction (`build_condition()` helper)
- `derived-from-text` extension builder
- Opt-in `note_paths` kwarg on `FHIRDataLoader`
- `[fhir4ds,ner]` extra (now depends on `medterm4ds[extraction]`, not
  `medspacy` / `spacy` directly)
- Zero-dep default (`fhir4ds` core imports without medterm4ds)

**medterm4ds.extract contract** (`src/medterm4ds/services/extraction.py:480`):

```python
def extract(
    text: str,
    *,
    format: str = "codes",          # "codes" -> ExtractedConcept; "terms" -> FilteredSpan
    categories: list[str] | None = None,   # ["condition", "medication", "lab", ...]
    mode: str | None = None,        # "lexical" | "semantic" | "hybrid"
    min_grade: str | None = None,   # "certain" | "probable" | "possible"
    include_negated: bool = False,
    include_uncertain: bool = False,
    include_historical: bool = False,
) -> list[ExtractedConcept]:
    ...
```

`ExtractedConcept` fields used by fhir4ds: `code`, `source` (UMLS mnemonic —
already covered by Phase 1's `_SOURCE_MNEMONIC_TO_URL` map), `display`,
`matched_text`, `status`, `section`, `confidence`, `match_grade`, `category`,
`span_start`, `span_end`, plus `.system_label` shortcut.

**Defaults used by fhir4ds (configurable via `NotesPipelineConfig`):**
- `format="codes"`
- `categories=None` (all)
- `mode=None` (medterm4ds default = hybrid)
- `min_grade="certain"`
- `include_negated=False`, `include_uncertain=False`, `include_historical=False`
- Only `concept.status == "affirmed"` concepts generate Conditions.

The rest of this FDD is the **original Phase 4 design** and is retained for
context. Sections marked **[SUPERSEDED]** below are no longer in fhir4ds scope.

---


## 1. Objective

Extend auto-coding from `CodeableConcept.text` to **clinical note bodies** —
narrative text fields like `DocumentReference.content[].attachment.data`,
`ClinicalImpression.summary`, `DiagnosticReport.presentedForm[].data`, and the
six other text-bearing paths enumerated in the master plan. The pipeline:

```
extract note text → medspaCy (Sectionizer + ConText) → token-classification
NER (d4data/biomedical-ner-all) → section + assertion filter → SapBERT
linking via medterm4ds (Phase 1 endpoint) → CodeableConcept construction
(Phase 2 extension shape) → NEW derived Condition resources → DuckDB load
```

Each derived `Condition` carries provenance via `Condition.evidence.detail`
referencing the source `{resourceType}/{id}`. Source resources are NEVER
mutated (INV-6) — derived Conditions are separate new resources.

**Phase 4 success criteria (matches master plan Exit Criteria):**

1. Loading a bundle of `DocumentReference` resources with note text produces
   derived codings for positive-affirmed entity mentions.
2. Negated mentions ("no history of diabetes") are NOT coded — ConText
   precision ≥ 95% on the synthetic test set.
3. Cache hits on duplicate note text within section + sentence boundaries.
4. End-to-end pipeline runs at ≤ 300 ms/note on CPU
   (medspaCy ~30 ms + NER ~150 ms + SapBERT ~100 ms).

Phase 4 builds on Phase 1 (terminology endpoint) and Phase 2 (autocoding
infrastructure — the per-Coding extension shape and search-result
filter/truncate logic are reused verbatim).

| Path | Action | Purpose |
|------|--------|---------|
| `fhir4ds/cql/loader/section_allowlist.py` | NEW | Default allow-list + context excludes (data) |
| `fhir4ds/cql/loader/derived_from_text_extension.py` | NEW | URL constant, builder, parser for the per-Condition `derived-from-text` extension |
| `fhir4ds/cql/loader/notes_ner.py` | NEW | `ClinicalNoteNER`, `NERConfig`, `extract_spans()` (medspaCy + token NER) |
| `fhir4ds/cql/loader/notes_pipeline.py` | NEW | `ClinicalNotesPipeline`, `ClinicalNotesConfig`, `derive_conditions()` (orchestration) |
| `fhir4ds/cql/loader/search_helpers.py` | NEW | Shared SapBERT lookup + filter/truncate helpers (extracted from `AutoCoder`) |
| `fhir4ds/cql/loader/fhir_loader.py` | MODIFY | Add `notes_pipeline` kwarg; insert derived Conditions in same batch as source |
| `fhir4ds/cql/loader/auto_coder.py` | MODIFY (refactor) | Delegate to `search_helpers` instead of private helpers |
| `pyproject.toml` | MODIFY | Add `[fhir4ds,ner]` extra |

---

## 2. Spec Alignment

### 2a. FHIR R4 Condition — derived shape

HL7 [Condition](https://hl7.org/fhir/R4/condition.html):

- `Condition.code` `0..1 CodeableConcept` — the auto-coded concept (one
  CodeableConcept, with `coding[]` populated by the Phase 2 AutoCoder
  shape, each Coding carrying the autocoding extension with
  `engine="medterm4ds-ner"`).
- `Condition.subject` `1..1 Reference(Patient|Group|...)` — same as the
  source resource's subject.
- `Condition.evidence.detail` `0..* Reference(Any)` — the provenance
  handle: `{source_resourceType}/{source_id}`. `Reference(Any)` is what
  makes source-type-agnostic derivation legal — `DocumentReference`,
  `ClinicalImpression`, `Encounter`, `Observation`, `AllergyIntolerance`,
  `MedicationRequest`, `DiagnosticReport`, `CarePlan` are all valid
  sources.
- `Condition.evidence.code` `0..* CodeableConcept` — mirrors
  `Condition.code` for queryable evidence; populated by the same
  auto-coded CodeableConcept.
- `Condition.clinicalStatus` `0..1 CodeableConcept` — bounded by the
  `http://terminology.hl7.org/CodeSystem/condition-clinical` valueset;
  Phase 4 default `"active"` (configurable).
- `Condition.verificationStatus` `0..1 CodeableConcept` — bounded by
  `http://terminology.hl7.org/CodeSystem/condition-ver-status`; Phase 4
  default `"unconfirmed"`. Marks auto-derived vs clinician-confirmed.
- `Condition.meta.tag` — Phase 4 adds a tag with system
  `http://fhir4ds.org/CodeSystem/condition-provenance`, code
  `auto-derived` so downstream retrieves can filter derived Conditions.
- `Condition.extension` — Phase 4 adds a `derived-from-text` marker
  extension (private URL `http://fhir4ds.org/fhir/StructureDefinition/derived-from-text`)
  with sub-extensions: `source-path`, `section-title`, `span-start`,
  `span-end`, `ner-model`, `sectionizer-version`. Used for debugging and
  for re-derivation sweeps in Phase 5.

### 2b. medspaCy Sectionizer + ConText

- **Sectionizer** (`medspacy.section_detection`) tags each sentence with
  a section title (Assessment, PMH, Allergies, etc.). Title synonyms are
  matched by medspaCy's built-in rule set; Phase 4 restricts to the
  configured allow-list (default: Assessment, Assessment and Plan, Past
  Medical History, Problem List, Diagnosis, Diagnoses).
- **ConText** (`medspacy.context`) tags each entity with semantic
  modifiers: `NEGATED_EXISTENCE` ("no history of"), `UNCERTAIN`
  ("possible", "may have"), `HISTORICAL` ("resolved", "in remission").
  Phase 4 default excludes `negated`, `uncertain`, `history-of` from
  problem coding.

### 2c. HuggingFace token-classification NER

- `d4data/biomedical-ner-all` is a token-classification transformer
  (~400-500 MB on disk) trained on a union of biomedical corpora
  (BC5CDR, NCBI, etc.). Multi-type output: disease, chemical/drug, gene,
  protein.
- Phase 4 wraps it behind a `ClinicalNoteNER` interface with
  `NERConfig.model_name` (default `"d4data/biomedical-ner-all"`) — the
  pipeline is model-agnostic so v2 can swap in a fine-tuned
  Bio_ClinicalBERT token classifier without changes to the surrounding
  pipeline.
- Loads lazily on first `extract_spans()` call; cached on the
  `ClinicalNoteNER` instance for the lifetime of the loader.

### 2d. Zero-dependency default (Phase 1 INV-1, preserved)

`fhir4ds` core MUST import without `medspacy`/`spacy`/`transformers`/
`torch`. Every NER-specific import is inside `__init__` or method
bodies, never at module top level. The `[fhir4ds,ner]` extra installs
the runtime deps; without it, importing
`fhir4ds.cql.loader.notes_pipeline` succeeds but instantiating
`ClinicalNotesPipeline` raises a clear `ImportError` with an install
hint.

---

## 3. Architecture

### 3a. Pipeline invocation point (Decision a)

**Inside `FHIRDataLoader`, after Phase 2 augmentation, before validation.
Derived Conditions join the same DuckDB batch as their source.**

Rationale:

- One call site. All entry points (`load_resource`, `load_resources`,
  `load_bundle/load_file/load_ndjson/load_directory/load_from_url`)
  delegate to the two batch paths — same pattern as Phase 2's
  `auto_coder` hook.
- One transaction. Derived Conditions and the source resource are
  written atomically; if the loader crashes mid-batch, neither survives.
- Pre-validation placement. The pipeline reads the raw resource dict
  (before `_validate_resource_identity` would reject it); derived
  Conditions go through their own validation (subject reference is
  present, id is a non-empty string).
- Cache reuse. The pipeline shares the `autocoding_cache` table with
  Phase 2's `AutoCoder` (single DuckDB connection, idempotent
  `CREATE TABLE IF NOT EXISTS`). SapBERT search results cache under the
  same `(text_hash, category, search_mode, index_version)` PK; note
  that the text fed into SapBERT here is the *span text* (e.g.
  "diabetes"), not the note — so spans reuse Phase 2 cache rows
  naturally.

### 3b. Note path resolution (Decision b)

**base64-decoding is encoded in a helper inside
`notes_pipeline._extract_text()`, not in the path DSL.**

Path spec is plain dotted notation with `[]` suffix for list-valued
segments, matching the Phase 4-introduced list-aware walker. The
helper inspects the resource type + path and applies decoding when the
path is one of the known base64-encoded paths:

```python
_BASE64_PATHS = {
    ("DocumentReference", "content[].attachment.data"),
    ("DiagnosticReport", "presentedForm[].data"),
}
```

Why not in the path spec:

- The base64 paths are finite and known at module load; a tuple-keyed
  dict is faster than parsing a path DSL.
- List-valued intermediates (`content[]`, `presentedForm[]`,
  `note[]`, `finding[]`, `reason[]`, `reaction[]`) need list-aware
  resolution (Phase 2 v1 limitation called out as deferred to Phase 4).
  Phase 4 introduces `_walk_path_list_aware()` which collects all
  list-element matches; this is the same code path for base64 and
  non-base64 lists.

### 3c. NER model loading (Decision c)

Heavy models (medspaCy + scispaCy ~1-2 GB, biomedical-ner-all
~400-500 MB) load **lazily on first `extract_spans()` call**.

- The `ClinicalNoteNER.__init__` constructs `None` placeholders for
  `_nlp` (medspaCy pipeline), `_sectionizer`, `_context`, `_ner_pipe`
  (HuggingFace pipeline).
- First `extract_spans()` triggers a one-time
  `_ensure_models_loaded()` that imports `medspacy` / `spacy` /
  `transformers` inside the method body (lazy import) and instantiates
  the pipelines.
- Subsequent calls reuse the cached pipelines on the instance.
- A multi-process batch runner constructs one `ClinicalNoteNER` per
  worker — model memory is not shared across processes (acceptable;
  DuckDB writes are serialized through a single writer connection
  anyway).

### 3d. Section allow-list as data (Decision d)

```python
# fhir4ds/cql/loader/section_allowlist.py
DEFAULT_SECTION_ALLOWLIST: list[str] = [
    "Assessment",
    "Assessment and Plan",
    "Past Medical History",
    "Problem List",
    "Diagnosis",
    "Diagnoses",
]

DEFAULT_CONTEXT_EXCLUDES: list[str] = [
    "NEGATED_EXISTENCE",
    "UNCERTAIN",
    "HISTORICAL",
]
```

medspaCy's Sectionizer handles synonym matching (e.g. "PMH" → "Past
Medical History"). Overridable via
`ClinicalNotesConfig.section_allowlist` /
`ClinicalNotesConfig.context_excludes`. Empty list (`[]`) disables
filtering entirely (codes everything) — documented as a footgun, not
the default.

### 3e. Category mapping table (Decision e)

```python
# fhir4ds/cql/loader/notes_pipeline.py
NER_TYPE_TO_CATEGORY: dict[str, str | None] = {
    "Disease":                 "condition",
    "Disease_disorder":        "condition",
    "Problem":                 "condition",
    "Sign_symptom":            "condition",
    "Chemical":                "medication",
    "Chemical_drug":           "medication",
    "Drug":                    "medication",
    "Pharmacologic_substance": "medication",
    "Lab":                     "lab",
    "Diagnostic_procedure":    "procedure",
    "Therapeutic_procedure":   "procedure",
    "Procedure":               "procedure",
    "Body_part":               "body_structure",
    "Gene":                    None,  # skip — no medterm4ds gene category in v1
    "Protein":                 None,
}
```

NER output labels are normalized (lowercased, `_` → ` `, prefix-stripped)
before lookup so "Disease_disorder" and "DISEASE_DISORDER" both resolve.
Unknown labels log DEBUG and are skipped. Overridable via
`ClinicalNotesConfig.ner_type_overrides`.

### 3f. Derived Condition id generation (Decision f)

**Deterministic hash of
`(source_resourceType, source_id, span_start, span_end)`.**

```python
derived_id = "der-" + hashlib.sha256(
    f"{source_type}/{source_id}#{span_start}-{span_end}".encode("utf-8")
).hexdigest()[:16]
```

Rationale:

- **Idempotent re-runs.** Loading the same source resource twice
  produces the same derived Condition id; DuckDB's
  delete-before-insert dedups cleanly. No orphans, no duplicates.
- **Collision-safe.** 16 hex chars (64 bits) is enough for any
  realistic source-resource count; the PK includes both the derived
  id and `resourceType="Condition"`, so collisions across derived
  types are impossible (Phase 4 only emits Conditions).
- **Debuggable.** The `derived-from-text` extension carries the
  source path + span offsets explicitly; the id is opaque but the
  extension is human-readable.

### 3g. Reuses Phase 2's autocoding extension (Decision g)

Every derived Condition's `code.coding[]` entries carry the same
6-field autocoding extension from Phase 2
(`http://fhir4ds.org/fhir/StructureDefinition/autocoding`), with
`engine="medterm4ds-ner"` to distinguish NER-derived codings from
`CodeableConcept.text`-derived codings (`engine="medterm4ds"`).

This means downstream consumers can route on `engine` to find
NER-derived codings for re-derivation sweeps or audits.

### 3h. Search helper extraction (audit S1)

The Phase 2 `AutoCoder` private methods `_lookup_or_search`,
`_filter_and_truncate`, `_result_to_dict`, and `_resolve_index_version`
are promoted to a new shared module
`fhir4ds/cql/loader/search_helpers.py`. Phase 2's `AutoCoder` and
Phase 4's `ClinicalNotesPipeline` both consume them.

```python
# fhir4ds/cql/loader/search_helpers.py
def lookup_or_search(
    *, endpoint, con, cache_enabled, cache_table,
    text, text_hash, category, search_mode, index_version,
    config,  # AutoCoderConfig-shaped
) -> list[dict]: ...

def filter_and_truncate(
    results: list[dict], min_match_grade: str, top_k: int,
) -> list[dict]: ...

def resolve_index_version(
    endpoint, config, *, pinned_state: tuple[Optional[str], bool],
) -> tuple[Optional[str], bool, str]: ...

def result_to_dict(result: Any) -> dict: ...
```

Phase 2's `AutoCoder` delegates to these helpers (minimal refactor —
the methods become thin wrappers). This removes the private-API
coupling the audit flagged (S1).

### 3i. `derived-from-text` extension (audit S5)

New module `fhir4ds/cql/loader/derived_from_text_extension.py`,
mirroring `autocoding_extension.py`:

```python
DERIVED_FROM_TEXT_EXTENSION_URL = (
    "http://fhir4ds.org/fhir/StructureDefinition/derived-from-text"
)

# Sub-extensions (URL, value type):
#   source-path          valueString
#   section-title        valueString
#   span-start           valueInteger
#   span-end             valueInteger
#   ner-model            valueString
#   sectionizer-version  valueString

def build_derived_from_text_extension(
    *, source_path, section_title, span_start, span_end,
    ner_model, sectionizer_version,
) -> dict: ...

def parse_derived_from_text_extension(condition: dict) -> dict | None: ...
```

URL constants and value types are pinned at module level for test
discovery and downstream parsers.

### 3j. Failure isolation (INV-8)

`ClinicalNotesPipeline.derive_conditions(resource)` MUST NEVER raise out
of the loader. All exceptions are caught, logged at WARNING, and the
pipeline returns `[]` (no derived Conditions for that resource). A
single bad note (truncated UTF-8, NER model OOM, SapBERT timeout) does
not break the load. Mirrors Phase 2's INV-9.

### 3k. Loop prevention (audit S6)

The pipeline instance tracks visited `(resourceType, id)` pairs in a
`set` (per-instance, in-memory). Derived Conditions flow through
`load_resource` but their ids are added to the visited set on
construction, so a future code path that adds `Condition` to
`note_paths` cannot trigger re-derivation of derived Conditions.

---

## 4. Implementation Plan (file-by-file)

### 4.1 Create `fhir4ds/cql/loader/section_allowlist.py`

Stdlib only. Two module-level constants (`DEFAULT_SECTION_ALLOWLIST`,
`DEFAULT_CONTEXT_EXCLUDES`). ~30 lines.

### 4.2 Create `fhir4ds/cql/loader/derived_from_text_extension.py`

Stdlib only. URL constant, `build_derived_from_text_extension()`,
`parse_derived_from_text_extension()`. Mirrors Phase 2's
`autocoding_extension.py` structure exactly. ~120 lines.

### 4.3 Create `fhir4ds/cql/loader/search_helpers.py`

Stdlib only. Extracted from `AutoCoder`:
`lookup_or_search`, `filter_and_truncate`, `resolve_index_version`,
`result_to_dict`. The helpers take a `config` object (duck-typed — works
with both `AutoCoderConfig` and any Phase 4 config that exposes
`search_mode`, `min_match_grade`, `top_k`, `index_version`). ~180 lines.

### 4.4 Refactor `fhir4ds/cql/loader/auto_coder.py`

- `AutoCoder._lookup_or_search` → delegates to
  `search_helpers.lookup_or_search`.
- `AutoCoder._filter_and_truncate` → delegates to
  `search_helpers.filter_and_truncate`.
- `AutoCoder._resolve_index_version` → delegates to
  `search_helpers.resolve_index_version` (probe-and-pin state stays on
  the `AutoCoder` instance).
- `AutoCoder._result_to_dict` → static method delegates to
  `search_helpers.result_to_dict`.

Phase 2 tests MUST pass unchanged — the refactor is a behavior-preserving
extraction.

### 4.5 Create `fhir4ds/cql/loader/notes_ner.py`

```python
@dataclass(frozen=True)
class NERConfig:
    model_name: str = "d4data/biomedical-ner-all"
    medspacy_model: str = "en_core_sci_sm"  # scispaCy small model
    section_allowlist: list[str] = field(
        default_factory=lambda: list(DEFAULT_SECTION_ALLOWLIST)
    )
    context_excludes: list[str] = field(
        default_factory=lambda: list(DEFAULT_CONTEXT_EXCLUDES)
    )
    batch_size: int = 32  # HuggingFace token-classification batch size


@dataclass(frozen=True)
class EntitySpan:
    text: str
    start: int
    end: int
    entity_type: str  # raw NER label
    section_title: str
    context_flags: tuple[str, ...]  # ("NEGATED_EXISTENCE", "HISTORICAL", ...)


class ClinicalNoteNER:
    def __init__(self, config: NERConfig) -> None:
        self._config = config
        self._nlp = None            # lazy
        self._sectionizer = None    # lazy
        self._context = None        # lazy
        self._ner_pipe = None       # lazy

    def extract_spans(self, note_text: str) -> list[EntitySpan]: ...
        # 1. _ensure_models_loaded()  (lazy)
        # 2. doc = self._nlp(note_text)
        # 3. for each ent in doc.ents:
        #      section = self._sectionizer.get_section(ent.sent) or ""
        #      context = self._context.get_context(ent, window="sentence")
        #      skip if section not in allowlist
        #      skip if any flag in context_excludes present
        #      emit EntitySpan(...)
        # 4. return spans

    def _ensure_models_loaded(self) -> None:
        # All medspacy/spacy/transformers imports happen HERE, inside the
        # method body. Module top-level imports stay stdlib-only.
        ...

    @classmethod
    def preload_models(cls, config: "NERConfig") -> "ClinicalNoteNER":
        """Explicit warm-up helper. Constructs, loads, returns."""
        ...
```

Zero-dep at module import time. `medspacy`/`spacy`/`transformers`
imports live inside `_ensure_models_loaded`.

### 4.6 Create `fhir4ds/cql/loader/notes_pipeline.py`

```python
NER_TYPE_TO_CATEGORY: dict[str, str | None] = {...}  # §3e

DEFAULT_NOTE_PATHS: dict[str, list[str]] = {
    "DocumentReference":   ["content[].attachment.data"],
    "ClinicalImpression":  ["summary", "finding[].basis"],
    "Encounter":           ["reason[].valueString",
                            "hospitalization.dischargeDisposition.text"],
    "Observation":         ["note[].text"],
    "AllergyIntolerance":  ["reaction[].description"],
    "MedicationRequest":   ["note[].text"],
    "DiagnosticReport":    ["presentedForm[].data"],
    "CarePlan":            ["note[].text"],
}

_BASE64_PATHS = {
    ("DocumentReference", "content[].attachment.data"),
    ("DiagnosticReport", "presentedForm[].data"),
}


@dataclass(frozen=True)
class ClinicalNotesConfig:
    enabled: bool = True
    ner_config: NERConfig = field(default_factory=NERConfig)
    autocoder_config: AutoCoderConfig = field(default_factory=AutoCoderConfig)
    note_paths: dict[str, list[str]] = field(
        default_factory=lambda: dict(DEFAULT_NOTE_PATHS)
    )
    ner_type_overrides: dict[str, str | None] = field(default_factory=dict)
    derived_clinical_status: str = "active"
    derived_verification_status: str = "unconfirmed"
    engine_version: str = "0.0.1"


class ClinicalNotesPipeline:
    def __init__(
        self,
        endpoint: "TerminologyEndpoint",
        con: Any,
        *,
        config: ClinicalNotesConfig | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._con = con
        self._config = config or ClinicalNotesConfig()
        self._ner = ClinicalNoteNER(self._config.ner_config)
        # Reuse the autocoding_cache table from Phase 2 (idempotent CREATE).
        self._cache_enabled = self._ensure_cache_table()
        # Probe-and-pin state, shared with search_helpers.resolve_index_version.
        self._pinned_index_version: Optional[str] = None
        self._index_version_resolved = False
        # Loop prevention (audit S6).
        self._visited: set[tuple[str, str]] = set()

    def derive_conditions(self, resource: dict) -> list[dict]:
        """INV-8: never raises; returns [] on any failure."""
        try:
            if not self._config.enabled:
                return []
            return self._derive_inner(resource)
        except Exception as exc:  # noqa: BLE001
            _logger.warning(...)
            return []

    def _derive_inner(self, resource: dict) -> list[dict]: ...
        # 1. Resolve (resource_type, resource_id). Skip if visited.
        # 2. Walk note_paths[resource_type]; collect texts via
        #    _walk_path_list_aware + _extract_text.
        # 3. For each text: spans = self._ner.extract_spans(text).
        # 4. Dedup spans by normalized text.
        # 5. For each span:
        #      a. category = NER_TYPE_TO_CATEGORY.get(span.entity_type)
        #         skip if None.
        #      b. results = search_helpers.lookup_or_search(...)
        #      c. filtered = search_helpers.filter_and_truncate(...)
        #      d. if filtered: build CodeableConcept (Phase 2 extension
        #         with engine="medterm4ds-ner") + build derived Condition.
        # 6. Mark (resource_type, resource_id) visited.
        # 7. Return list[dict] of derived Conditions.


def _build_derived_condition(
    *,
    source_resource: dict,
    span: EntitySpan,
    codeable_concept: dict,
    clinical_status: str,
    verification_status: str,
    engine_version: str,
) -> dict: ...
```

### 4.7 Modify `fhir4ds/cql/loader/fhir_loader.py` (additive)

- New `TYPE_CHECKING` block at top: forward-import `ClinicalNotesPipeline`.
- `__init__` signature gains
  `notes_pipeline: "Optional[ClinicalNotesPipeline]" = None`; stored as
  `self._notes_pipeline`.
- Inside `load_resource`, AFTER `auto_coder.augment_resource(resource)`
  but BEFORE `_validate_resource_identity`:
  ```python
  if self._notes_pipeline is not None:
      derived = self._notes_pipeline.derive_conditions(resource)
      for d in derived:
          self._insert_resource(d)
  ```
- Inside `load_resources`'s for-loop: same hook, BUT append derived
  Conditions to the row list being built (audit S2 — batch insert),
  not per-row INSERT.
- No changes to `load_file`, `load_bundle`, `load_ndjson`,
  `load_directory`, `load_from_url` — they delegate.

**INV-2 (zero-regression):** With `notes_pipeline=None` (default), no
code path is entered. Behavior is byte-identical to pre-Phase-4.

### 4.8 Modify `pyproject.toml`

```toml
[project.optional-dependencies]
# ... existing extras ...
ner = [
    "medspacy>=0.2.0",
    "spacy>=3.7.0",
    "transformers>=4.36.0",
    "torch>=2.1.0",
]
all = [
    "fhir4ds[terminology,ner]",
]
```

Note: `medspacy` and `spacy` pull in their own model-download logic at
runtime; the user must run `python -m spacy download en_core_sci_sm`
and `python -m medspacy download` separately (documented in
`docs/getting-started/ner.md` — Engineer creates this).

### 4.9 Out of Phase 4 (deferred)

- Plumbing `ner_config=` through `evaluate_measure(...)` and
  `execute_cql(...)` — Phase 4.5 follow-on.
- Async / multiprocessing batch coordination logic — Phase 5.
- v2 fine-tuned Bio_ClinicalBERT NER — Phase 5.
- Browser-side NER (Transformers.js + WASM) — research track only.

---

## 5. Test Strategy

### 5.1 Unit tests — `fhir4ds/cql/tests/unit/loader/`

**`test_section_allowlist.py`** (stdlib only):

- `DEFAULT_SECTION_ALLOWLIST` contains the 6 documented sections.
- `DEFAULT_CONTEXT_EXCLUDES` contains the 3 documented modifier classes.
- Allergies, Social History, Family History, Review of Systems NOT in
  default allow-list. INV-7.

**`test_derived_from_text_extension.py`** (stdlib only):

- `build_derived_from_text_extension(...)` produces the 6 sub-extensions
  with documented URLs and value types.
- `parse_derived_from_text_extension` round-trips through `build`.
- Integer span offsets serialize as `valueInteger`.

**`test_search_helpers.py`** (stdlib only, stubbed endpoint):

- `lookup_or_search` cache-hit path: identical call returns identical
  bytes (INV-7 from Phase 2, preserved through extraction).
- `filter_and_truncate` respects `min_match_grade` and `top_k`.
- `resolve_index_version` probe-and-pin: first call probes, second call
  reuses pinned value.
- `result_to_dict` accepts both dataclass and dict inputs.

**`test_notes_ner_unit.py`** (requires `[fhir4ds,ner]` extra; skipped
via `pytest.importorskip("medspacy")` at module top):

- `test_negation_filter`: "Patient has no history of diabetes.
  Assessment: hypertension." → diabetes NOT in spans; hypertension IN
  spans. INV-3.
- `test_section_allowlist_excludes_allergies`: "Allergies: penicillin"
  → penicillin NOT coded. INV-7.
- `test_uncertain_filter`: "Patient may have CKD." → CKD NOT in spans.
- `test_history_filter`: "History of MI in 2018." → MI NOT in spans by
  default; override `context_excludes=[]` → MI IN spans.
- `test_model_lazy_load`: `ClinicalNoteNER(config)` does NOT import
  medspacy at construction; first `extract_spans()` call does. INV-1.

**`test_notes_pipeline_unit.py`** (uses stubbed `TerminologyEndpoint`,
stubbed `ClinicalNoteNER` returning canned spans):

- `test_derived_condition_shape`: derived Condition has
  `code` (auto-coded CodeableConcept), `subject` (source subject),
  `evidence.detail` (`{source_type}/{source_id}`), `clinicalStatus="active"`,
  `verificationStatus="unconfirmed"`, `meta.tag` with `auto-derived`.
  INV-4, INV-5.
- `test_category_mapping_disease`: NER span with entity_type="Disease"
  → category="condition" → search called with `category="condition"`.
  INV-9.
- `test_category_mapping_drug`: entity_type="Chemical_drug" →
  category="medication".
- `test_unknown_ner_type_skipped`: entity_type="Gene" → no search call,
  no derived Condition.
- `test_derived_id_deterministic`: same source + same span offsets →
  same derived Condition id (idempotency).
- `test_source_resource_not_mutated`: pipeline runs, source resource
  dict is deep-equal to pre-pipeline snapshot. INV-6.
- `test_pipeline_never_raises`: stubbed NER raising mid-extract →
  `derive_conditions` returns `[]`, no exception escapes. INV-8.
- `test_derived_from_text_extension`: every derived Condition carries
  the `derived-from-text` extension with all 6 sub-extensions.
- `test_loop_prevention`: derived Condition fed back as input is
  skipped (visited set). Audit S6.

**`test_fhir_loader_ner_integration.py`** (stubbed pipeline):

- `test_notes_pipeline_none_default`: with `notes_pipeline=None`,
  loader behavior is byte-identical (regression). INV-2.
- `test_derived_conditions_loaded_alongside_source`: small DocumentReference
  fixture → 2 derived Conditions appear in the resources table alongside
  the source.
- `test_idempotent_rerun`: loading the same DocumentReference twice
  produces the same derived Condition id (no duplicates in DuckDB).

### 5.2 Integration test — `fhir4ds/cql/tests/integration/test_notes_ner_loader.py`

Auto-skip if `MEDTERM4DS_TEST_URL` env var unset OR `medspacy` not
installed. Build a small synthetic bundle of 5 DocumentReference
resources with mixed content (positive findings, negated mentions,
uncertain mentions, all-in-different-sections). Assert:

- Derived Conditions created only for positive-affirmed problem-list
  mentions.
- Cache hits on duplicate span text within a single load.
- Total wall time per note ≤ 300 ms (10% slack: 330 ms).

### 5.3 Regression — conformance baseline

```bash
python3 conformance/scripts/run_all.py
```

Required: still **2822/2822**. Phase 4 is purely additive
(`notes_pipeline=None` is the default); the `auto_coder.py` refactor
(search-helpers extraction) is behavior-preserving and Phase 2 tests
must pass unchanged.

### 5.4 Regression — Phase 2 + Phase 3 tests unchanged

All existing Phase 2 tests (`test_auto_coder_unit.py`,
`test_autocoding_extension.py`, `test_category.py`,
`test_fhir_loader.py` autocoding tests) and Phase 3 tests
(`test_closure.py`, `test_subsumption.py`) MUST pass unchanged. Phase 4
adds a new sibling path and refactors `auto_coder.py` via extraction;
no behavior change is permitted.

### 5.5 Fixtures — `fhir4ds/cql/tests/fixtures/notes/`

- `synthetic_notes.ndjson` — 5 DocumentReference resources covering:
  1. Positive affirmed problem ("Assessment: Type 2 Diabetes Mellitus")
  2. Negated mention ("no history of diabetes")
  3. Uncertain ("possible CKD")
  4. Allergies section ("Allergies: penicillin")
  5. Multiple sections with mixed problems
- `expected_spans.json` — manual annotation of expected spans for the
  unit-test precision check (INV-3).

### 5.6 Validation commands

```bash
# 1. Unit tests (stubbed endpoint; medspacy required for NER tests)
python3 -m pytest fhir4ds/cql/tests/unit/loader/ -v

# 2. Zero-dep default (Phase 1 INV-1 preserved)
python3 -c "import fhir4ds; print('OK')"
# Must succeed with NO medspacy/spacy/transformers/torch installed.

python3 -c "from fhir4ds.cql.loader.notes_pipeline import ClinicalNotesPipeline"
# Must succeed at IMPORT time (lazy). Instantiation without medspacy
# raises ImportError with install hint at __init__ time, NOT import time.

# 3. Conformance baseline
python3 conformance/scripts/run_all.py 2>&1 | tail -50
# Expected: 2822/2822

# 4. Integration (if live medterm4ds + medspacy available)
MEDTERM4DS_TEST_URL=http://127.0.0.1:8001 \
  python3 -m pytest fhir4ds/cql/tests/integration/test_notes_ner_loader.py -v

# 5. Performance gate (single-note latency)
python3 -m pytest fhir4ds/cql/tests/integration/test_notes_ner_loader.py \
  -v -k perf --perf-gate-ms=330
```

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Model download is ~2-3 GB; first-run UX is slow | Document `python -m medspacy download` and `python -m spacy download en_core_sci_sm` as separate setup steps. Provide `ClinicalNoteNER.preload_models()` helper for explicit warm-up. |
| Token-classification NER precision < 90% out-of-box | Default `match_grade="certain"` (Phase 2 strict threshold) filters out low-confidence SapBERT matches. ConText + section allow-list filters out wrong-section and negated mentions before SapBERT. Combined precision target ≥ 95% on synthetic test. |
| medspaCy + scispaCy model version skew | Pin `medspacy>=0.2.0`, `spacy>=3.7.0` in `[fhir4ds,ner]` extra. Document the tested model version in `docs/getting-started/ner.md`. |
| Base64-decoded note text is binary garbage (PDF embedded) | `_extract_text()` validates UTF-8 decodability; non-decodable content is skipped with DEBUG log. No exception (INV-8). |
| Subject reference missing on source resource | `_derive_inner` checks `source.get("subject")` before constructing derived Condition; missing subject → no derived resource, logged at INFO (not WARNING — common for non-clinical resources). |
| Performance: SapBERT ~100 ms × N spans × N notes = slow at scale | (a) Cache reuse via Phase 2 `autocoding_cache` table; (b) dedup spans within a note before search; (c) document multiprocessing recipe in `docs/getting-started/ner.md`. |
| Derived Condition id collision across source types | Hash includes `{source_type}/{source_id}` prefix, so DocumentReference/123 and Observation/123 produce different ids. |
| `auto_coder.py` refactor breaks Phase 2 tests | Extraction is behavior-preserving; Phase 2 tests run unchanged (regression gate §5.4). |

---

## 7. Performance Budget

Per master plan Exit Criteria: ≤ 300 ms/note on CPU single-threaded.

| Stage | Target | Notes |
|-------|--------|-------|
| `_extract_text` + base64 decode | 1 ms | stdlib only |
| medspaCy pipeline (sectionize + ConText) | 30 ms | `en_core_sci_sm` small model |
| HuggingFace token-classification NER | 150 ms | `d4data/biomedical-ner-all`, CPU, batch_size=32 |
| Section + ConText filter | 1 ms | in-memory |
| Span dedup | 1 ms | in-memory |
| SapBERT search (avg 3 spans × 100 ms) | 100 ms | Phase 1 InProcessTerminologyEndpoint |
| Derived Condition construction | 1 ms | dict-building |
| DuckDB INSERT (batch) | 16 ms | batch write |
| **Total** | **300 ms** | matches Exit Criteria |

Cache-hit fast path: span text seen before → ~5 ms total (skip SapBERT
search). Expected after first ~1000 notes due to boilerplate repetition.

---

## 8. Architectural Invariants (from self-audit)

Phase 4 MUST preserve these 9 falsifiable invariants. Each is testable
in isolation (see §5):

| ID | Invariant | Test |
|----|-----------|------|
| INV-1 | `python3 -c "import fhir4ds"` succeeds WITHOUT medspacy/spacy/transformers/torch installed. | Fresh venv, install only core deps, run import. |
| INV-2 | `notes_pipeline=None` (default) preserves existing FHIRDataLoader behavior byte-identically. | Capture before/after row JSON, assert byte-equality. |
| INV-3 | Negated spans ("no history of X") NOT coded — ConText precision ≥ 95% on synthetic test set. | 10-note synthetic bundle, manual annotation, count false positives. |
| INV-4 | Every derived Condition carries `evidence.detail` referencing source `{resourceType}/{id}`. | Walk derived Conditions, assert each has the reference. |
| INV-5 | Every derived Condition has `verificationStatus="unconfirmed"` + `clinicalStatus="active"` (configurable). | Walk derived Conditions, assert both fields. |
| INV-6 | Source resources are NOT mutated — derived Conditions are separate new resources. | Deep-copy source, run pipeline, deep-equal check. |
| INV-7 | Section allow-list default excludes Allergies, social history (unless overridden). | Synthetic note with Allergies section → no derived Conditions from that section. |
| INV-8 | NER pipeline never raises out of the loader — single bad note doesn't break the load. | Inject raising NER, malformed note, missing subject; assert no exception escapes. |
| INV-9 | Category mapping is data-driven (table in `notes_pipeline.py`), overridable via `ClinicalNotesConfig`. | Override map, verify override takes precedence. |

---

## 9. Open Questions (for user pause)

1. **Model cache sharing across multiple `ClinicalNotesPipeline` instances
   on the same process.** Recommended YES (module-level `_MODEL_CACHE`)
   for the multi-worker case where workers share models via fork.
2. **`derived-from-text` extension URL: public or private?** Master plan
   says private for v1 (mirrors Phase 2's `autocoding` extension
   posture). FDD adopts private; confirm during pause.
3. **`meta.tag=auto-derived` marker.** Useful for "give me only
   clinician-authored Conditions" retrieves. FDD includes it;
   confirm during pause.
4. **Source-is-Condition loop case.** FDD implements visited-set loop
   prevention (§3k). Confirm during pause.
5. **Should derived Conditions respect source `verificationStatus`?**
   FDD says NO — derived Conditions always start `unconfirmed`.
6. **Cache key for spans: include section title?** FDD says NO (audit
   S4) — SapBERT search is purely lexical+semantic on span text;
   section-based filtering happens BEFORE SapBERT, so cache key
   correctly omits section.
