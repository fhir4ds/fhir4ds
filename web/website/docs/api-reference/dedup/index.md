---
id: dedup
title: fhir4ds.dedup
sidebar_label: dedup
description: "API reference for fhir4ds.dedup: temporal resource deduplication — normalizers, coded/lexical/encounter strategies, survivorship, curation queue, Linkage output and audit over DuckDB."
---

# `fhir4ds.dedup`

The `fhir4ds.dedup` module clusters duplicate clinical resources (Observations, Conditions, Procedures, Immunizations, Medications, Encounters) deterministically: code identity + temporal signature partitioning, a conservative lexical fallback, overlap-based encounter merging, survivorship with field-level merge, FHIR Linkage output and a JSONL curation queue for what cannot be decided.

```python
from fhir4ds.dedup import run_dedup, run_encounter_dedup
```

---

## 1. Runners

### `run_dedup(...)`

The full coded-strategy pass:

```python
run_dedup(resources, run_id, *,
          conn=None,
          include_singletons_in_audit=False,
          default_tz=DEFAULT_TZ,
          code_fallback="on",
          concept_index=None,
          medication_resolver=None,
          output_dir=None,
          dedup_proposer=None) -> DedupRunResult
```

| Parameter | Type | Description |
|---|---|---|
| `resources` | `list[dict]` | FHIR resources (coded types). |
| `run_id` | `str` | Caller-supplied audit run identifier (no wall-clock). |
| `conn` | `DuckDBPyConnection \| None` | Optional connection for `dedup_linkage`/`dedup_audit` (fresh in-memory when omitted). |
| `code_fallback` | `str` | `"on"` (default) \| `"audit_only"` \| `"off"` — the tier-2 lexical cascade. |
| `concept_index` | `ConceptIndex \| None` | Concept display index for tier-2 hybrid resolution (default: the versioned in-repo index). |
| `medication_resolver` | optional | Bounded medication-reference resolver (default: same-corpus `MedicationIndex`). |
| `output_dir` | `str \| None` | When given, the curation queue is written to `<output_dir>/dedup_curation_queue.jsonl`. |
| `dedup_proposer` | `DedupCodeProposer \| None` | Default-off proposal hook — may only APPEND queue entries, never affect merges. |

Returns a `DedupRunResult`: `survivors` (sorted by survivor id), `linkage_resources` (sorted by dedup id), `stats`, `curation_queue_path`, and the `dedup_ids` property. Idempotent — re-running the same corpus upserts identical rows.

### `run_encounter_dedup(...)`

The temporal (overlap) strategy for Encounters — same back end, `window_rule="encounter:overlap"`:

```python
run_encounter_dedup(resources, run_id, *,
                    conn=None, include_singletons_in_audit=False,
                    default_tz=DEFAULT_TZ, membership=None,
                    output_dir=None) -> EncounterRunResult
```

`membership` maps member patient id → master individual id (e.g. from patient-matching `build_membership`); grouping happens before any pairing, so cross-patient encounters never merge. Merge edges are admitted under the CR-003 veto constraint — refused edges are audit-recorded (`encounter_edge_refused`).

### Lower-level passes

| Export | Description |
|---|---|
| `dedup_pass(resources, *, default_tz, code_fallback, concept_index, medication_resolver)` | Partition + escalate → `DedupResult` (clusters + parallel edge evidence). |
| `partition(records, *, code_fallback, ...)` | Stage-1 bucketing (code components / patient / temporal / value). |
| `escalate(group, *, default_tz)` | Stage-2 clustering inside one bucket. |
| `encounter_pass(resources, *, default_tz, membership)` | The Encounter strategy pass → `DedupResult`. |

## 2. Records and normalization

| Export | Description |
|---|---|
| `DedupRecord` | Per-resource normalized record; `DedupRecord.from_resource(resource)` builds one. |
| `categorize(resource)` / `Category` | VITAL / LAB / OTHER classification (vendored US Core vitals LOINC list in `US_CORE_VITAL_LOINC`). |
| `normalize_code` / `normalize_codes` | Code-system canonicalization (`SystemResolver` + UMLS mnemonics). |
| `normalize_value` | Value partition key with UCUM cross-unit canonicalization. |
| `normalize_temporal` / `NormalizedDate` / `Signature` | Authored-precision temporal signatures; UTC instants where determined. |
| `period_overlap` / `overlap_fraction` / `secondary_timestamp` | Temporal primitives. |
| `normalize_lexical_text` / `tier2_text_set` | The conservative tier-2 lexical normalizer. |
| `ConceptIndex` / `default_concept_index` / `Resolution` | Versioned concept display index. |
| `MedicationIndex` / `LazyMedicationIndex` / `resolve_medication_reference` | Bounded medication-reference resolution. |
| `POC_TROPONIN` / `VITAL_EXTENDED_WINDOW_LOINC` | Category-rule content tables. |

## 3. Survivorship

| Export | Description |
|---|---|
| `select_survivor(cluster)` | Deterministic winner (`SURVIVOR_SIGNATURE_RANK`, `survivor_rule_tuple`). |
| `merge_resources(cluster, survivor)` | Field-level merged survivor resource. |
| `survivor_dedup_id(cluster)` | Stable cluster identity. |
| `survivor_ranking_key(record)` | The ranking key (richness keys in `RICHNESS_KEYS`). |
| `DEDUP_EXTENSION_URL` | Survivor/alternate Linkage extension. |

## 4. Linkage, audit, curation

| Export | Description |
|---|---|
| `create_dedup_linkage_table(conn)` / `upsert_dedup_linkage(...)` | Idempotent dedup Linkage storage (`DEDUP_LINKAGE_DDL`, `TEMPORAL_DEDUP_EXTENSION_URL`). |
| `load_dedup_linkage_resources(conn)` | Read back Linkage resources. |
| `delete_linkage(...)` / `infer_window_rule(cluster)` | Linkage maintenance and window-rule labeling. |
| `create_dedup_audit_table(conn)` / `record_dedup_audit(...)` / `load_dedup_audit(conn, run_id)` | Audit surface (`DEDUP_AUDIT_DDL`). |
| `write_curation_queue(path, entries)` | Deterministic JSONL queue writer (`CURATION_QUEUE_FILENAME`). |
| `DedupCodeProposer` | Versioned, default-off proposal Protocol (`PROPOSER_INTERFACE_VERSION`). |
