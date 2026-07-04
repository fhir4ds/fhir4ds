# FEATURE DESIGN — medterm4ds Phase 2: Auto-Coding Loader

**Status:** APPROVED (pre-approved via `USER_DIRECTIVES.md`; architecture self-audit complete — see `fhir4ds-private/docs/prompts/.ai_loop/ARCHITECT_REVIEW.md`)
**Source plan:** `fhir4ds-private/docs/plans/medterm4ds-integration.md` (Phase 2 section, lines 183-201)
**Verified against codebase:** 2026-07-03 (post Phase 1 landing; `fhir4ds/cql/terminology/` exists with real `TerminologyEndpoint`, `CodeRef`, `SearchResult` API)
**Target version:** 0.0.11
**Scope:** Phase 2 ONLY. Phases 3 (subsumption correctness) and 4 (clinical notes NER) are deferred to later FDDs.

---

## 1. Objective

Augment FHIR resources whose `CodeableConcept` fields carry `text` but no
`coding[]` by running the text through medterm4ds and writing the top-k
ranked matches back into `coding[]`, each tagged with a structured
`autocoding` extension. This brings text-only EHR legacy data into the
addressable universe of ValueSet- and code-based CQL retrieves.

The phase introduces four new artifacts and modifies one existing module:

| Path | Action | Purpose |
|------|--------|---------|
| `fhir4ds/cql/loader/auto_coder.py` | NEW | `AutoCoder`, `AutoCoderConfig`, `augment_resource()` |
| `fhir4ds/cql/loader/autocoding_extension.py` | NEW | Extension URL constant, builder, parser, predicate |
| `fhir4ds/cql/loader/category.py` | NEW | resource-type → category map + text normalizer |
| `fhir4ds/cql/tests/unit/loader/` | NEW | unit tests for the three modules above |
| `fhir4ds/cql/tests/fixtures/conditions_text_only.ndjson` | NEW | integration test fixture (10 mixed Conditions) |
| `fhir4ds/cql/loader/fhir_loader.py` | MODIFY | add `auto_coder` kwarg to `FHIRDataLoader`; inline augmentation hook |

**Phase 2 success criterion (matches master plan Exit Criteria):** Loading
`conditions_text_only.ndjson` populates `Condition.code.coding[]` for every
resource that has `text`, every auto-coded Coding carries the `autocoding`
extension with all six sub-extension fields, and a second load with the same
data hits the cache 100%.

---

## 2. Spec Alignment

### 2a. FHIR R4 CodeableConcept

HL7 [CodeableConcept](https://hl7.org/fhir/R4/datatypes.html#CodeableConcept):
`text` is "a human language representation of the concept(s)" and `coding[]`
holds the formal code(s). Both MAY coexist; Phase 2 preserves `text`
unchanged (INV-2) and only adds Codings to `coding[]`.

### 2b. FHIR R4 Coding.userSelected

HL7 [Coding.userSelected](https://hl7.org/fhir/R4/datatypes-definitions.html#Coding.userSelected):
"Set to `true` if the user selected this coding from a list". Auto-coded
entries are by definition NOT user-selected; every Coding written by Phase 2
sets `userSelected=false` (INV-6). This is the FHIR-standard "non-user-authored"
marker and the refresh handle for Phase 5 staleness sweeps.

### 2c. FHIR R4 Extensions on Codings

HL7 [Extension](https://hl7.org/fhir/R4/extensibility.html) allows arbitrary
structured extensions on any element. FHIR R4 permits extensions on `Coding`
(`Coding.extension 0..*`). Phase 2 attaches a single complex extension to
each auto-coded Coding with the canonical URL
`http://fhir4ds.org/fhir/StructureDefinition/autocoding` and six
sub-extensions (URLs and value types fixed by `autocoding_extension.py` —
see §3d for exact shape, INV-5).

### 2d. FHIR R4 JSON Serializability

Auto-coded resources must remain valid FHIR JSON. The `_serialize_resource`
helper in `fhir_loader.py` (line 63) uses `json.dumps(allow_nan=False)` —
the `score` decimal must be a finite `float`, never `NaN`/`Infinity`. The
extension builder normalizes through `float(score)` and rejects non-finite
with `ValueError`.

---

## 3. Architecture

### 3a. Integration Point — `FHIRDataLoader`

Current code (verified 2026-07-03, `fhir_loader.py`):

| Method | Line | Role |
|--------|------|------|
| `__init__(con, table_name="resources", create_table=True)` | 131 | construct; register UDF cache |
| `load_resource(resource)` | 244 | single resource, delete-before-insert |
| `load_resources(resources)` | 274 | batch path, dedup last-write-wins |
| `load_bundle(bundle)` | 346 | delegates to `load_resources` |
| `load_file(path)` | 385 | dispatches to `load_resource` or `load_bundle` |
| `load_ndjson(path, strict=True)` | 407 | parses NDJSON, delegates to `load_resources` |
| `load_directory(path)` | 460 | walks directory, delegates to `load_file` |

**Phase 2 change (additive only):**
1. `__init__` gains `auto_coder: Optional["AutoCoder"] = None` (TYPE_CHECKING forward-quoted import). Stored as `self._auto_coder`. AutoCoder owns its own `autocoding_cache` table and constructs it in its own `__init__`; the loader does not need a separate cache-init step.
2. The augmentation hook is invoked at the top of the per-resource loop in BOTH `load_resource` and `load_resources`, BEFORE `_validate_resource_identity` / `_extract_patient_ref` / `_serialize_resource`. With `auto_coder=None`, the call site is skipped — byte-identical to current behavior (INV-1).
3. `load_file`, `load_bundle`, `load_ndjson`, `load_directory`, `load_from_url` all funnel through `load_resource` / `load_resources`, so the augmentation hook is exercised exactly once per resource regardless of entry point.

**Decision (master plan Open Question 1 — inline vs post-load):** AUGMENT INLINE. The master plan's Open Question 1 explicitly recommends inline ("Inline is simpler... Post-load requires re-reading and rewriting rows. Recommend inline."). Post-load would require re-reading rows and re-writing the `resource` JSON column — strictly more work and a second failure surface. Inline keeps one call site and one serialization. No drift from the original plan.

### 3b. Relationship to Phase 1 `TerminologyEndpoint`

`AutoCoder` consumes the Phase 1 API surface (verified — these symbols exist in `fhir4ds/cql/terminology/`):

- `endpoint.search_batch(queries: list[tuple[str, str]], *, mode: str) -> list[list[SearchResult]]` — primary call path (batch-friendly).
- `endpoint.search_text(query, category, *, mode)` — used ONCE for the index-version probe (§3c step 3).
- `SearchResult` fields consumed (all six flow into the extension): `system`, `code`, `display`, `score`, `match_grade`, `search_mode`, `index_version`.

`AutoCoder` does NOT use `expand` / `expand_intensional` (those are Phase 3 concerns). The Phase 1 endpoint is a structural Protocol, so a stub doubles cleanly in unit tests.

### 3c. Cache Strategy — `autocoding_cache` DuckDB Table

Lives in the same DuckDB connection as the `resources` table (one connection, one transactional scope). Schema (per master plan §5):

```sql
CREATE TABLE IF NOT EXISTS autocoding_cache (
    text_hash      VARCHAR,      -- sha256(normalized_text)
    category       VARCHAR,      -- condition | lab | medication | procedure | vaccine | body_structure
    search_mode    VARCHAR,      -- lexical | hybrid | semantic
    index_version  VARCHAR,      -- from SearchResult.index_version (or "unknown")
    result_json    VARCHAR,      -- JSON-encoded list[SearchResult] (dict form)
    cached_at      TIMESTAMP,
    PRIMARY KEY (text_hash, category, search_mode, index_version)
);
```

**Lookup sequence (the contract that satisfies INV-7 and INV-8):**

1. **Normalize text**: lowercase, NFKC normalize, replace runs of whitespace/punctuation with single space, strip ends. Function: `category.normalize_text(text) -> str`. No fuzzy matching — that's the search engine's job.
2. **Hash**: `text_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()`.
3. **Index-version pinning (one-shot probe-and-pin)**: If `AutoCoderConfig.index_version` is set explicitly, use it. Otherwise, the AutoCoder resolves the live index version via a single `endpoint.search_text("diabetes", "condition", mode=...)` probe at first use and pins it for the rest of the run. Cheap (~110ms once) and prevents cache pollution if the underlying SapBERT/BM25 index rotates mid-run.
4. **Cache lookup**:
   ```sql
   SELECT result_json FROM autocoding_cache
   WHERE text_hash   = ?
     AND category     = ?
     AND search_mode  = ?
     AND index_version = ?;
   ```
5. **On miss**: call `endpoint.search_batch([(text, category)], mode=self._config.search_mode)`, take `result[0]`, filter by `match_grade` threshold, truncate to `top_k`, write the FULL pre-filter result to cache (so threshold/top_k changes don't force cache misses).
6. **Write cache**:
   ```sql
   INSERT OR REPLACE INTO autocoding_cache
   VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
   ```
7. **Attach to resource**: build Codings via the extension builder, append to `CodeableConcept.coding`.

**Cache hit determinism (INV-7):** Identical `(text_hash, category, search_mode, index_version)` returns byte-identical `result_json`. Coding construction from a fixed `result_json` is deterministic (fixed field order, `score` formatted via `float()`). Same-day same-input same-output guaranteed.

**Cache invalidation (INV-8):** A SapBERT or BM25 index refresh changes `index_version`, which changes the PK, so old rows are simply not hit and new rows are written. No manual invalidation needed.

### 3d. Autocoding Extension Shape (exact, copy from master plan §2)

```json
{
  "url": "http://fhir4ds.org/fhir/StructureDefinition/autocoding",
  "extension": [
    {"url": "engine",          "valueString":  "medterm4ds"},
    {"url": "engine-version",  "valueString":  "<engine_version>"},
    {"url": "search-mode",     "valueCode":    "hybrid"},
    {"url": "score",           "valueDecimal": 0.87},
    {"url": "match-grade",     "valueCode":    "certain"},
    {"url": "index-version",   "valueString":  "2026AA-bm25-v3"}
  ]
}
```

| Sub-extension | URL | Value type | Source |
|---------------|-----|-----------|--------|
| engine | `engine` | `valueString` | constant `"medterm4ds"` (only one engine in v1) |
| engine-version | `engine-version` | `valueString` | `AutoCoderConfig.engine_version` (default `"0.0.1"`) |
| search-mode | `search-mode` | `valueCode` | `SearchResult.search_mode` (`lexical`/`hybrid`/`semantic`) |
| score | `score` | `valueDecimal` | `SearchResult.score` (finite `float`; non-finite rejected) |
| match-grade | `match-grade` | `valueCode` | `SearchResult.match_grade` (`certain`/`probable`/`ambiguous`/`no-match`) |
| index-version | `index-version` | `valueString` | `SearchResult.index_version` or `"unknown"` |

All six fields are ALWAYS present (INV-5). The `index-version` falls back to `"unknown"` when the endpoint does not report one (still written so the field exists for downstream consumers / Phase 5 staleness sweeps).

### 3e. Category Mapping (resource-type → category)

`category.py` owns a single static dict, validated at import time:

```python
RESOURCE_TYPE_TO_CATEGORY: dict[str, str] = {
    "Condition":           "condition",
    "Observation":         "lab",         # default — Observation.code can be lab, vital, or survey
    "MedicationRequest":   "medication",
    "MedicationStatement": "medication",
    "Medication":          "medication",
    "Procedure":           "procedure",
    "Immunization":        "vaccine",
    "BodyStructure":       "body_structure",
}
```

`AutoCoderConfig.category_overrides: dict[str, str]` lets users override the default per-resource-type. Unknown resource types are skipped with DEBUG log (no crash).

**Audit finding (SKEPTIC — does `resolver.py` or `fhir_loader.py` already define a `category` concept?):** Verified by grep 2026-07-03 — neither file defines a terminology-discovery `category` concept. `CQLErrorCategory` in `fhir_server/types.py` is a different namespace (error categorization) and must NOT be reused. Define `category.py` cleanly as a new module.

### 3f. CodeableConcept Path Targeting

`AutoCoderConfig.codeable_paths: dict[str, list[str]]` maps resource types to one or more CodeableConcept-bearing field paths. Default (covers the common text-only cases):

```python
DEFAULT_PATHS: dict[str, list[str]] = {
    "Condition":           ["code"],
    "Observation":         ["code"],
    "MedicationRequest":   ["medicationCodeableConcept"],
    "MedicationStatement": ["medicationCodeableConcept"],
    "Procedure":           ["code"],
    "Immunization":        ["vaccineCode"],
    "BodyStructure":       ["image.site"],
}
```

Path resolution: a tiny dotted-path walker. Each segment is a key lookup; `None` at any level short-circuits. On miss (path absent, value is not a CodeableConcept dict), skip with DEBUG.

**v1 limitation:** `BodyStructure.image` is `0..*` in FHIR R4 (a list). The dotted walker treats `image` as a dict, so `BodyStructure.image.site` only resolves when the resource has a single image object (not a list). Multi-image BodyStructure is uncommon in text-only EHR migration data; defer to Phase 4. The walker returns `None` for list-valued intermediates (no exception), so the resource is simply skipped.

---

## 4. Implementation Plan (file-level tasks)

### 4.1 Create `fhir4ds/cql/loader/category.py`

- Static dict `RESOURCE_TYPE_TO_CATEGORY` (see §3e).
- `resolve_category(resource_type: str, overrides: dict[str, str] | None = None) -> str | None` — returns the medterm4ds discovery category for a resource type, or `None` if unknown.
- `normalize_text(text: str) -> str` — NFKC normalize, lowercase, replace runs of whitespace/punctuation with single space, strip ends. Engineer: use Python `re` + `string.punctuation` (NOT the third-party `regex` module) to avoid a new dependency.

### 4.2 Create `fhir4ds/cql/loader/autocoding_extension.py`

- `AUTOCODING_EXTENSION_URL = "http://fhir4ds.org/fhir/StructureDefinition/autocoding"`.
- `build_autocoding_extension(*, engine, engine_version, search_mode, score, match_grade, index_version) -> dict` — raises `ValueError` on non-finite `score`.
- `parse_autocoding_extension(coding: dict) -> dict | None` — inverse; returns the 6 fields as a dict, or `None` if extension absent.
- `is_autocoded(coding: dict) -> bool` — convenience predicate (returns True iff coding carries the autocoding extension).

### 4.3 Create `fhir4ds/cql/loader/auto_coder.py`

```python
@dataclass(frozen=True)
class AutoCoderConfig:
    enabled: bool = True
    search_mode: str = "hybrid"               # lexical | hybrid | semantic
    min_match_grade: str = "certain"          # threshold (master plan §4 — strict by default)
    top_k: int = 3                            # max Codings per CodeableConcept
    engine_version: str = "0.0.1"             # medterm4ds release version (configurable)
    index_version: Optional[str] = None       # None => probe-and-pin on first batch
    codeable_paths: dict[str, list[str]] = field(default_factory=lambda: dict(DEFAULT_PATHS))
    category_overrides: dict[str, str] = field(default_factory=dict)
```

`AutoCoder` class:
- `__init__(self, endpoint: TerminologyEndpoint, con, *, config: AutoCoderConfig | None = None)` — stores refs, calls `_ensure_cache_table()`.
- `augment_resource(self, resource: dict) -> dict` — top-level entry; wraps `_augment_resource_inner` in `try/except Exception` (INV-9: never raises). Mutates `resource` in place; returns it.
- `_augment_resource_inner` — category lookup + path walk + delegation to `_augment_codeable_concept`.
- `_augment_codeable_concept` — normalize, hash, lookup-or-search, filter by `min_match_grade`, sort by score desc, take `top_k`, append Codings.
- `_resolve_index_version` — one-shot probe-and-pin (§3c step 3).
- `_ensure_cache_table` / `_cache_lookup` / `_cache_write` — DuckDB cache plumbing.
- `_walk_path(resource, dotted_path)` — dotted-path walker for §3f.
- `_result_to_dict(result)` — `dataclasses.asdict` on `SearchResult`.

`TYPE_CHECKING` import of `TerminologyEndpoint` (no runtime dep on Phase 1 module beyond what the caller passes in — preserves Phase 1's INV-1 zero-dep default).

### 4.4 Modify `fhir4ds/cql/loader/fhir_loader.py` (additive)

- New `TYPE_CHECKING` block at top: forward-import `AutoCoder`.
- `__init__` signature gains `auto_coder: "Optional[AutoCoder]" = None`; stored as `self._auto_coder`.
- Inside `load_resource`, BEFORE `_validate_resource_identity`:
  ```python
  if self._auto_coder is not None:
      self._auto_coder.augment_resource(resource)
  ```
- Inside `load_resources`'s for-loop, BEFORE `_validate_resource_identity`:
  ```python
  if self._auto_coder is not None:
      self._auto_coder.augment_resource(resource)
  ```
- No changes to `load_file`, `load_bundle`, `load_ndjson`, `load_directory`, `load_from_url` — they all delegate.

### 4.5 Out-of-Phase-2 (deferred)

- Plumbing `auto_coder=` through `evaluate_measure(...)` and `execute_cql(...)` in `fhir4ds/cql/__init__.py` — Phase 2.5 follow-on (mirrors Phase 1's deferred top-level plumbing pattern).
- Per-Coding refresh sweep on index update — Phase 5 (streaming readiness).
- Async batch — Phase 5.
- Multi-image BodyStructure (list-valued `image[]` resolution) — Phase 4 NER pipeline.

---

## 5. Test Strategy

### 5.1 Unit tests — `fhir4ds/cql/tests/unit/loader/`

- **`test_autocoding_extension.py`**
  - `build_autocoding_extension(...)` produces exactly the 6 sub-extensions with the documented URLs and value types.
  - Non-finite `score` (`NaN`, `inf`, `-inf`) raises `ValueError`.
  - `parse_autocoding_extension` round-trips through `build`.
  - `is_autocoded` returns True for a coding carrying the extension, False for a plain one.
- **`test_category.py`**
  - `resolve_category("Condition")` returns `"condition"`; unknown type returns `None`.
  - Override map takes precedence.
  - `normalize_text` is idempotent and strips punctuation/case/whitespace.
- **`test_auto_coder_unit.py`** — uses a stub endpoint (no `medterm4ds`):
  - INV-1: with `auto_coder=None`, `FHIRDataLoader` is byte-identical (regression — capture before/after row JSON).
  - INV-2: `text` field is preserved unchanged after augmentation.
  - INV-3: resource with `text=null` or `text=""` or whitespace-only is untouched.
  - INV-4: resource with a manual `coding[]` entry is NOT re-coded.
  - INV-5: every appended Coding has all 6 sub-extension fields with documented URLs + value types.
  - INV-6: every appended Coding has `userSelected == False`.
  - INV-7: identical input produces identical `coding[]` bytes across two runs.
  - INV-8: changing pinned `index_version` produces a cache MISS (forces re-search).
  - INV-9: stub endpoint raising mid-batch leaves the resource unchanged; `augment_resource` does not raise.
  - Threshold filtering: results below `min_match_grade` are dropped.
  - Top-k truncation: only `top_k` Codings are appended.
  - Cache write/read round-trip produces identical `SearchResult` dict form.

### 5.2 Extend `fhir4ds/cql/tests/unit/test_fhir_loader.py`

- New `auto_coder=None` regression: existing tests pass unchanged (zero behavior change).
- New `auto_coder=<stub>` test: feeding a text-only Condition appends a Coding to `code.coding[]` and the `resource` JSON column reflects it.

### 5.3 Integration tests — `fhir4ds/cql/tests/integration/test_autocoding_loader.py`

- Auto-skip if `MEDTERM4DS_TEST_URL` env var is unset.
- Build `HTTPTerminologyEndpoint(MEDTERM4DS_TEST_URL)`, `AutoCoder(endpoint, con, config=AutoCoderConfig(index_version=None))`.
- Load `conditions_text_only.ndjson` fixture (§5.5).
- Assert: every text-only Condition now has non-empty `coding[]`, every coding has the autocoding extension with all 6 fields, `userSelected=false`.
- Assert: loading the same NDJSON a second time produces 100% cache hits — verified by counting `autocoding_cache` rows vs. unique normalized text count (cache row count == unique normalized text count, NOT total resource count).

### 5.4 Regression — conformance baseline

`python3 conformance/scripts/run_all.py` MUST remain **2822/2822** (per `USER_DIRECTIVES.md` and `PROC_VALIDATION.md` baseline 2026-04-24). Phase 2 is purely additive (`auto_coder=None` is the default), so the risk surface is the modified `load_resource`/`load_resources` code path. The no-op branch MUST be byte-identical to current code — the regression test in §5.2 enforces this.

### 5.5 Fixture — `fhir4ds/cql/tests/fixtures/conditions_text_only.ndjson`

Engineer MUST create this NDJSON with ~10 mixed lines covering every invariant:
- 3 Conditions with `code.text` only (no `coding[]`) — SHOULD be auto-coded.
- 2 Conditions with `code.text` + a manual `coding[]` entry — SHOULD NOT be re-coded (INV-4).
- 2 Conditions with `code.coding[]` only (no `text`) — SHOULD be untouched (INV-3).
- 1 Condition with `code.text = ""` — SHOULD be skipped (INV-3).
- 1 Condition with `code.text = "Type 2 Diabetes Mellitus"` (duplicate of another line) — verifies cache dedup (INV-7).
- 1 Patient resource (non-Condition) — verifies category skip.

---

## 6. Validation Commands

The implementation engineer MUST run, in order:

1. `python3 -m pytest fhir4ds/cql/tests/unit/loader/ -v`
2. `python3 -m pytest fhir4ds/cql/tests/unit/test_fhir_loader.py -v`
3. Zero-dep default check (Phase 2 must not break Phase 1's INV-1 guarantee):
   ```bash
   python3 -c "from fhir4ds.cql.loader.auto_coder import AutoCoder, AutoCoderConfig; print('OK')"
   ```
   Must succeed with NO `httpx`, NO `medterm4ds` installed.
4. `python3 conformance/scripts/run_all.py 2>&1 | tail -50`
   Expected: **2822/2822** (no regression).
5. (If live medterm4ds available)
   ```bash
   MEDTERM4DS_TEST_URL=http://127.0.0.1:8001 \
     python3 -m pytest fhir4ds/cql/tests/integration/test_autocoding_loader.py -v
   ```

---

## 7. Architectural Invariants (from self-audit)

Phase 2 MUST preserve these 9 falsifiable invariants. Each is testable in isolation (see §5.1):

| ID | Invariant | Test |
|----|-----------|------|
| INV-1 | With `auto_coder=None`, `FHIRDataLoader` behavior is byte-identical to current. | Capture before/after row JSON, assert byte-equality. |
| INV-2 | Original `CodeableConcept.text` is preserved unchanged. | Deep-copy input, assert `text` field unchanged. |
| INV-3 | Resources without text (missing/None/empty/whitespace) are untouched. | Feed four text-absent variants, assert no mutation. |
| INV-4 | Resources with existing manual `coding[]` are NOT re-coded. | Feed manual coding + text, assert no second Coding appended. |
| INV-5 | Every auto-coded Coding carries all 6 sub-extension fields with documented URLs + value types. | Walk appended Codings, assert extension shape. |
| INV-6 | All auto-coded Codings have `userSelected == False`. | Assert `coding["userSelected"] is False`. |
| INV-7 | Cache hit returns byte-identical appended Codings (deterministic). | Run augmentation twice, serialize, assert byte-equality. |
| INV-8 | Cache key includes `index_version`; PK change forces MISS. | Pin v1, populate; switch to v2; assert search_batch is called. |
| INV-9 | `augment_resource` never raises (any input, any underlying exception). | Inject raising endpoint, malformed resource; assert no exception escapes. |

---

## 8. Deferred / Open Questions

1. **Top-level plumbing through `execute_cql` / `evaluate_measure`** — Phase 2.5 follow-on (mirrors Phase 1's deferral pattern).
2. **Multi-image BodyStructure (`image[]` list)** — Phase 4 NER pipeline will exercise list-valued paths; Phase 2 ships a dict-only walker and skips list cases silently.
3. **Observation category ambiguity** — `Observation.code` can be lab, vital, or survey. v1 maps to `"lab"` by default; users override via `category_overrides={"Observation": "vital"}`. Phase 4 NER will introduce per-resource-type LOINC-class detection.
4. **Concurrent loader instances on the same connection** — `WeakKeyDictionary` for the valueset UDF cache already handles this; the `autocoding_cache` table is per-connection (DuckDB) and idempotent (`CREATE TABLE IF NOT EXISTS`), so concurrent instances are safe.
5. **Cache row growth** — `autocoding_cache` grows unbounded across runs. Acceptable for batch backfill (millions of rows is fine in DuckDB). LRU eviction is a Phase 5 streaming-readiness concern.
