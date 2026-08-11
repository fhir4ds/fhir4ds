---
id: notes-pipeline
title: Clinical Notes NER Pipeline
sidebar_label: Notes Pipeline
---

# Clinical Notes NER Pipeline

The `NotesPipeline` (`fhir4ds.cql.loader.notes_pipeline`) derives structured FHIR Condition resources from free-text clinical notes. It extracts text from configured note paths on a FHIR resource, runs each fragment through `medterm4ds.extract()` (a medspaCy + GLiNER + SapBERT cascade), and wraps every affirmed concept in a synthetic Condition carrying both [Auto-Coding](./autocoding.md)'s autocoding extension (`engine="medterm4ds-ner"`) and a `derived-from-text` extension for full audit.

This is Phase 4 of the medterm4ds integration. The reference NER backend is documented in the [medterm4ds extraction service](https://github.com/joelmontavon/medterm4ds).

## 1. Install

```bash
pip install 'fhir4ds-v2[ner]'
```

The `ner` extra pulls `medterm4ds[extraction]` transitively, which brings in medspaCy, GLiNER, transformers, and torch. fhir4ds itself **never** imports any of these directly — the heavy ML deps are owned by medterm4ds so the core `import fhir4ds` path stays zero-dependency.

The first call to `extract_conditions()` will fetch model weights from the `fhir4ds/medterm4ds` HuggingFace repo (revision `v0.0.1`). Subsequent calls reuse the cached weights.

## 2. Quickstart

```python
from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig

pipeline = NotesPipeline(
    NotesPipelineConfig(
        min_grade="probable",   # loosen from strict "certain" default
    )
)

note_text = (
    "Patient is a 54-year-old male with a history of type 2 diabetes mellitus, "
    "hypertension, and hyperlipidemia. Presents with fatigue and polyuria. "
    "Assessment: uncontrolled diabetes. Plan: start metformin."
)

resource = {
    "resourceType": "ClinicalImpression",
    "id": "ci-001",
    "subject": {"reference": "Patient/test-patient"},
    "summary": note_text,
}

conditions = pipeline.extract_conditions(resource)
# → list of derived Condition dicts
```

Each derived Condition looks like:

```json
{
  "resourceType": "Condition",
  "id": "<deterministic sha256-based ID>",
  "subject": {"reference": "Patient/test-patient"},
  "code": {
    "coding": [{
      "system": "http://snomed.info/sct",
      "code": "73211009",
      "display": "Diabetes mellitus (disorder)",
      "userSelected": false,
      "extension": [{
        "url": "https://fhir4ds.com/fhir/StructureDefinition/autocoding",
        "extension": [
          {"url": "engine", "valueString": "medterm4ds-ner"},
          {"url": "engine-version", "valueString": "0.0.1"},
          {"url": "match-grade", "valueString": "certain"},
          ...
        ]
      }]
    }],
    "text": "Diabetes mellitus"
  },
  "verificationStatus": {
    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "unconfirmed"}]
  },
  "clinicalStatus": {
    "coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]
  },
  "extension": [{
    "url": "https://fhir4ds.com/fhir/StructureDefinition/derived-from-text",
    "extension": [
      {"url": "source-ref", "valueString": "ClinicalImpression/ci-001"},
      {"url": "source-path", "valueString": "summary"},
      {"url": "span-start", "valueInteger": 47},
      {"url": "span-end", "valueInteger": 76},
      {"url": "matched-text", "valueString": "type 2 diabetes mellitus"}
    ]
  }]
}
```

## 3. Default note paths

`DEFAULT_NOTE_PATHS` covers the common FHIR R4 resources that carry free text:

| Resource type | Note paths |
|---|---|
| `DocumentReference` | `content[].attachment.data` |
| `ClinicalImpression` | `summary`, `finding[].basis` |
| `Encounter` | `reason[].valueString`, `hospitalization.dischargeDisposition.text` |
| `Observation` | `note[].text` |
| `AllergyIntolerance` | `reaction[].description` |
| `MedicationRequest` | `note[].text` |
| `DiagnosticReport` | `presentedForm[].data` |
| `CarePlan` | `note[].text` |

Dotted-path syntax supports `[N]` indexing and `[]` wildcard (e.g. `content[].attachment.data` walks every element of the `content` array). Override per-resource-type via `NotesPipelineConfig.note_paths={"Encounter": ["my-custom-path"]}`.

## 4. Configuration

`NotesPipelineConfig` exposes:

```python
from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig

config = NotesPipelineConfig(
    note_paths={...},              # override DEFAULT_NOTE_PATHS (merged, not replaced)
    mode="hybrid",                 # "lexical" / "semantic" / "hybrid" — None = medterm4ds default
    min_grade="certain",           # "certain" / "probable" / "possible" — concepts below this are dropped
    include_negated=False,         # also emit Conditions for negated concepts (status=negated)
    include_uncertain=False,       # also emit Conditions for uncertain concepts
    include_historical=False,      # also emit Conditions for historical (past) concepts
    verification_status="unconfirmed",  # default for derived Conditions
    clinical_status="active",      # default for derived Conditions
    batch_size=1,                  # batch size for parallel augmentation
    workers=1,                     # worker processes for parallel augmentation
)
```

Strict-by-default: only affirmed concepts at-or-above `"certain"` match grade generate Conditions. Loosen `min_grade="probable"` for higher recall; set `include_negated=True` if you also want the "no CKD" to produce a (negated) Condition.

## 5. Deterministic Condition IDs

The derived Condition `id` is `sha256(<ID_SALT>:<source_ref>:<span_start>:<span_end>:<system>:<code>)` truncated to 32 characters, where `<system>` is the **post-normalization** FHIR canonical URL. Two consequences:

- **Re-runs are byte-identical.** Running the pipeline twice on the same source produces the same Conditions — no deduplication needed downstream.
- **Different code systems at the same span don't collide.** A SNOMED and an ICD10 coding at the same span produce different Conditions.

## 6. Audit: derived-from-text extension

Every derived Condition carries a `derived-from-text` extension with:

- `source-ref` — the source resource reference (e.g. `"ClinicalImpression/ci-001"`)
- `source-path` — the dotted path the text came from (e.g. `"summary"`)
- `span-start` / `span-end` — character offsets into the extracted fragment
- `matched-text` — the verbatim text span that produced this concept

This is the audit trail: a clinician reviewing a derived Condition can click straight through to the exact sentence in the source note that generated it.

## 7. Invariants

The pipeline is built to fail safe under batch load pressure:

- **NEVER raises.** Every exception is caught, logged at WARNING, and `extract_conditions` returns `[]`. A single bad resource cannot break the batch.
- **No Condition-on-Condition derivation.** If the source `resourceType` is `"Condition"`, the pipeline returns `[]` — prevents infinite loops when derived Conditions get re-fed into the loader.
- **System URL normalization.** medterm4ds returns UMLS mnemonics (`SNOMEDCT_US`); the pipeline expands them to FHIR canonical URLs (`http://snomed.info/sct`) via the same map used by the [Terminology Service](./terminology-service.md).
- **Deterministic output.** Same source + same medterm4ds index → byte-identical Conditions. Re-running the pipeline is a no-op.

## 8. Batch loading

For ETL workloads, use `extract_conditions_batch(resources)`:

```python
from fhir4ds.cql.loader import NotesPipeline, NotesPipelineConfig

pipeline = NotesPipeline(
    NotesPipelineConfig(
        min_grade="probable",
        batch_size=100,
        workers=4,
    )
)

all_conditions = pipeline.extract_conditions_batch(list_of_resources)
```

With `workers > 1`, the pipeline spawns a `multiprocessing.Pool` with module-level worker functions (no `self` closure — fork-safe). Each worker imports `medterm4ds.extract` once and pre-warms the NLP pipeline. The pipeline emits a WARNING if `workers * 5GB` exceeds available virtual memory — medspaCy + SapBERT is ~5GB per worker.

## 9. What this pipeline is NOT

- It is **not** a substitute for clinician review. Derived Conditions ship with `verificationStatus=unconfirmed` by design.
- It does **not** handle every FHIR resource — only the 8 types in `DEFAULT_NOTE_PATHS`. Add custom paths for other types.
- It does **not** run in the browser. The medspaCy + transformers + SapBERT stack is WASM-incompatible and the model weights are ~400MB. For a server-backed live demo, host medterm4ds alongside the pipeline; for an offline demo, pre-compute and ship the results as JSON.

## 10. See also

- [Terminology Service](./terminology-service.md) — the endpoint abstraction the pipeline uses for system URL normalization
- [Auto-Coding](./autocoding.md) — Phase 2's text-CodeableConcept auto-coder (the same autocoding extension, different `engine` label)
