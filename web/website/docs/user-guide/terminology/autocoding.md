---
id: autocoding
title: Auto-Coding Text-Only Concepts
sidebar_label: Auto-Coding
---

# Auto-Coding Text-Only Concepts

Legacy EHR data routinely ships `CodeableConcept`s with a free-text `text` field and no `coding[]` — `"code": {"text": "Type 2 diabetes mellitus"}`. CQL retrieves against `[Code: <valueset>]` cannot match these rows. The `AutoCoder` (`fhir4ds.cql.loader.auto_coder`) augments text-only CodeableConcepts with coded Codings drawn from a Phase 1 [Terminology Service](./terminology-service.md), turning your unstructured backlog into the addressable universe of code-based CQL retrieves.

## 1. Install

```bash
pip install 'fhir4ds-v2[terminology]'
```

Same extra as Phase 1 — auto-coding is a pure-Python pipeline that drives an endpoint you've already configured.

## 2. Quickstart

```python
import fhir4ds
from fhir4ds.cql import FHIRDataLoader
from fhir4ds.cql.loader import AutoCoder, AutoCoderConfig
from fhir4ds.cql.terminology import TerminologyConfig, get_terminology_endpoint

con = fhir4ds.create_connection()
endpoint = get_terminology_endpoint(
    TerminologyConfig(mode="http", url="http://127.0.0.1:8001/fhir")
)

coder = AutoCoder(endpoint, con)

# Augment a single resource (mutates in place, returns the same dict)
resource = {
    "resourceType": "Condition",
    "id": "cond-1",
    "code": {"text": "Type 2 diabetes mellitus"},
}
coder.augment_resource(resource)

# resource["code"]["coding"] is now populated:
# [
#   {
#     "system": "http://snomed.info/sct",
#     "code": "44054006",
#     "display": "Type 2 diabetes mellitus (disorder)",
#     "userSelected": False,
#     "extension": [{
#       "url": "https://fhir4ds.com/fhir/StructureDefinition/autocoding",
#       "extension": [
#         {"url": "engine", "valueString": "medterm4ds"},
#         {"url": "engine-version", "valueString": "0.0.1"},
#         {"url": "index-version", "valueString": "2024-01"},
#         {"url": "match-grade", "valueString": "certain"},
#         {"url": "search-mode", "valueString": "hybrid"},
#         {"url": "search-score", "valueDecimal": 0.92},
#         {"url": "result-text-hash", "valueString": "<sha256>"}
#       ]
#     }]
#   }
# ]
```

For batch loads, hand the `AutoCoder` to a `FHIRDataLoader` and the loader applies it to every resource:

```python
loader = FHIRDataLoader(con, terminology_endpoint=endpoint, auto_coder=coder)
loader.load_ndjson("conditions.ndjson")
```

## 3. Resource-type → category mapping

`AutoCoder` translates a FHIR resource type into one of the coarse discovery categories understood by `TerminologyEndpoint.search_text` — the `category` parameter of medterm4ds's `$search` operation. The default map lives in `fhir4ds.cql.loader.category.RESOURCE_TYPE_TO_CATEGORY`:

| Resource type | Category |
|---|---|
| `Condition` | `condition` (SNOMEDCT_US) |
| `Observation` | `lab` (LNC) |
| `MedicationRequest` | `medication` (RXNORM) |
| `MedicationStatement` | `medication` |
| `Medication` | `medication` |
| `Procedure` | `procedure` |
| `Immunization` | `vaccine` |
| `BodyStructure` | `body_structure` |

Override or extend via `AutoCoderConfig.category_overrides={"Observation": "vital"}`. Unknown resource types are skipped with a DEBUG log — they do not raise.

## 4. Text normalization

Before the search call, the input text is normalized via `fhir4ds.cql.loader.category.normalize_text`:

1. **NFKC** Unicode normalization — folds fullwidth digits, ligatures, superscripts.
2. **Lowercase** — case-insensitive cache key.
3. **Whitespace/punctuation collapse** — `"T2DM!"`, `"t2dm"`, and `"T2DM, "` all hash identically.
4. **Strip** leading/trailing whitespace.

Idempotent: `normalize_text(normalize_text(x)) == normalize_text(x)`. This is the cache key, so two resources with visually identical text get identical Codings.

## 5. Deterministic IDs and cache safety

The AutoCoder pins a per-instance cache table (`autocoding_cache`) in the same DuckDB connection as the resources table. Cache keys hash `(text, resource_type, search_mode, index_version)` — bumping the terminology index automatically invalidates stale rows.

**Safety invariants** (verified by the unit-test suite):

- **Original `CodeableConcept.text` is preserved unchanged.**
- **Resources with existing `coding[]` are NOT re-coded.**
- **Every auto-coded Coding has `userSelected == False`.**
- **Cache hit determinism** — same key returns byte-identical `result_json`.
- **Cache key pins `index_version`** — a version bump invalidates old rows.
- **`augment_resource` NEVER raises.** All exceptions are caught, logged at WARNING, and the resource is returned unchanged.

## 6. Configuration

`AutoCoderConfig` exposes knobs for ranking, thresholding, and batch behavior:

```python
from fhir4ds.cql.loader import AutoCoder, AutoCoderConfig

config = AutoCoderConfig(
    enabled=True,                  # master toggle (False = no-op)
    search_mode="hybrid",          # "lexical" / "semantic" / "hybrid"
    min_match_grade="certain",     # "certain" / "probable" / "ambiguous" / "no-match"
    top_k=3,                       # max Codings per CodeableConcept
    engine_version="0.0.1",        # written into the autocoding extension
    category_overrides={"Observation": "vital"},
)

coder = AutoCoder(endpoint, con, config=config)
```

Lower `min_match_grade` to `"probable"` for higher recall at the cost of precision. Raise `top_k` to keep more candidates per Coding set.

## 7. Batch augmentation

For large loads, `AutoCoder.augment_resources(resources)` batches the terminology searches via `search_batch`. Combined with the loader's parallel mode this saturates the terminology endpoint without losing the deterministic-output guarantee. Per-batch sizing is controlled at the loader level, not the AutoCoder.

## 8. Audit extension

Every derived Coding carries a structured [autocoding extension](https://fhir4ds.com/fhir/StructureDefinition/autocoding) recording:

- `engine` — `"medterm4ds"`
- `engine-version` — the medterm4ds release that produced the Coding
- `index-version` — the terminology index version (pinned at first call)
- `match-grade` — `certain` / `probable` / `ambiguous` / `no-match`
- `search-mode` — `lexical` / `semantic` / `hybrid`
- `search-score` — the raw score from the search call
- `result-text-hash` — sha256 of the normalized input text

This is the audit trail: downstream consumers can filter, re-rank, or strip auto-coded entries by `engine`, `match-grade`, or `index-version` without re-running the pipeline.

## 9. See also

- [Terminology Service](./terminology-service.md) — the endpoint abstraction AutoCoder drives
- [Notes Pipeline](./notes-pipeline.md) — derive Conditions from free-text notes (Phase 4 NER)
