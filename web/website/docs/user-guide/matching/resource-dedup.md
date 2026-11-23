---
id: resource-dedup
title: Resource Deduplication
sidebar_label: Resource Dedup
description: "Temporal resource deduplication in pure Python over DuckDB: coded/lexical/identity/encounter strategies, deterministic survivorship, FHIR Linkage output and a curation queue for what cannot be decided."
---

# Resource Deduplication

Beyond duplicate *patients*, real feeds carry duplicate *resources*: the same lab result reported twice (exact re-transmission and near-miss variants), the same condition restated by two source systems, one encounter split into overlapping segments. The `fhir4ds.dedup` package clusters these temporal duplicates deterministically, materializes a **survivor** resource per cluster, and writes standard FHIR `Linkage` evidence — sources are always retained.

Two properties hold across every strategy:

1. **Determinism.** Same corpus → byte-identical clusters, survivors, Linkage resources, audit rows and curation queue. No wall-clock, no RNG, no floating-point order dependence.
2. **Evidence, not mutation.** Deduplication never deletes or rewrites source rows; it produces survivors (new resources), Linkage resources, audit rows, and — for what it cannot decide — a **curation queue** for human review.

## 1. Install

```bash
pip install fhir4ds-v2
```

## 2. Quickstart: the coded strategy

The main pass (`run_dedup`) covers the coded resource types — Observation, Condition, Procedure, Immunization, MedicationRequest and peers. Two resources are duplicates when their **code identity** and **temporal signature** agree:

```python
from fhir4ds.dedup import run_dedup

base = {
    "resourceType": "Observation",
    "status": "final",
    "subject": {"reference": "Patient/p1"},
    "code": {"coding": [{
        "system": "http://loinc.org", "code": "2345-7",
        "display": "Glucose Ser/Plas MCnc Pt Qn",
    }]},
}

result = run_dedup([
    {**base, "id": "obs-a",
     "effectiveDateTime": "2026-01-15T10:30:00-07:00",
     "valueQuantity": {"value": 126, "unit": "mg/dL"}},
    {**base, "id": "obs-b",                      # same test, same instant,
     "effectiveDateTime": "2026-01-15T10:30:00-07:00",  # re-transmitted
     "valueQuantity": {"value": 126, "unit": "mg/dL"}},
    {**base, "id": "obs-c",                      # same day, DIFFERENT test
     "code": {"coding": [{"system": "http://loinc.org", "code": "4548-4",
                          "display": "Hemoglobin [Mass/volume] in Blood"}]},
     "effectiveDateTime": "2026-01-15T10:30:00-07:00",
     "valueQuantity": {"value": 13.5, "unit": "g/dL"}},
], run_id="dedup-001")

result.dedup_ids        # one dedup id per cluster with 2+ members
result.survivors        # merged survivor resource per cluster
result.stats            # per-rule counts, singleton/near-miss stats
```

`obs-a`/`obs-b` cluster (same LOINC code, same temporal signature, same normalized value); `obs-c` stays a singleton — same bucket, but a disjoint code set is a different test, never a duplicate.

### What "temporal signature" means

Dedup compares authored-precision date signatures: `1966-05` vs `1966-05-18` are *uncertain-equal* (one side is coarser), not unequal. Naive authored-local components are used for partition dates (no timezone inference), UTC instants only where the authored value determines them, and every resource type has a documented primary timestamp (`effectiveDateTime` / `performedDateTime` / `onsetDateTime` / …) plus secondary fallbacks. Temporal windows differ by category: labs collapse at the exact instant, vitals get an extended window (the same manually-keyed BP within minutes is a duplicate), and value partition keys canonicalize UCUM units (`mg` vs `g`) through the engine's quantity conversion surface.

## 3. The three-tier code cascade

When two resources in the same patient/temporal/value bucket carry *disjoint* code sets, dedup resolution cascades:

| Tier | Rule | Provenance |
|---|---|---|
| **1 — canonical** | Code sets intersect through (canonical system, code). | `canonical` |
| **2 — lexical** | Conservative normalized display-text sets intersect (casefold, NFKC, punctuation, UCUM unit aliases) **and** patient + temporal signature + normalized value all agree. | `lexical` |
| **3 — stop** | Everything else lands in the curation queue for human/terminology review. Proposals may only *add* queue entries. | — |

Tier 2 is deliberately conservative — no word-order normalization, no stemming, no synonyms: "Hemoglobin" must never bucket with "Hemoglobin A1c". Control it with `code_fallback="on" | "audit_only" | "off"`:

```python
result = run_dedup(resources, run_id="dedup-002", code_fallback="audit_only")
```

## 4. The Encounter strategy

Encounters are deduplicated by **temporal overlap**, not codes — one visit split into overlapping segments. The pass is grouping-first (a patient-membership map from [patient matching](/docs/user-guide/matching/patient-matching) can be supplied so cross-patient encounters can never merge), then merges edges under a scoring table over overlap/adjacency signals with EMER (emergency-department) hard negatives as vetoes:

```python
from fhir4ds.dedup import run_encounter_dedup

result = run_encounter_dedup(encounters, run_id="enc-001")
result.stats   # clusters, refused edges, merges
```

**Single-encounter semantics (CR-003):** a merge edge whose admission would place a vetoed pair inside one cluster is refused (edges admitted in sorted order — deterministic) and audit-recorded as a `encounter_edge_refused` curation entry. Direct vetoes and veto-free clusters are unaffected.

## 5. Survivorship

Each cluster materializes one survivor: the richest signature (fuller code sets, values, timestamps win, deterministically ranked), with field-level **merge** filling gaps from alternates. Survivor and alternates are recorded in a dedup Linkage (extension `TEMPORAL_DEDUP_EXTENSION_URL`) with the window rule that merged them:

```python
from fhir4ds.dedup import select_survivor, merge_resources, survivor_dedup_id

survivor = select_survivor(cluster)       # deterministic winner
merged = merge_resources(cluster, survivor)  # field-level merged resource
dedup_id = survivor_dedup_id(cluster)     # stable cluster identity
```

## 6. The curation queue

Everything dedup cannot decide is written to a deterministic JSONL queue — cross-bucket near-miss pairs, tier-3 unresolved codes, refused encounter edges — sorted, `sort_keys=True`, no wall-clock:

```python
result = run_dedup(resources, run_id="dedup-003", output_dir="/tmp/dedup")
result.curation_queue_path   # /tmp/dedup/dedup_curation_queue.jsonl
```

Machine proposals (e.g. from a terminology $search service) may only **append** `proposal` entries through the versioned, default-off `DedupCodeProposer` interface — a proposer can never affect merge decisions:

```python
from fhir4ds.dedup import DedupCodeProposer  # Protocol: version + propose()

result = run_dedup(resources, run_id="dedup-004",
                  output_dir="/tmp/dedup", dedup_proposer=my_proposer)
```

## 7. Audit surface

Every cluster decision is written to the `dedup_audit` table (idempotent upserts; re-running the same corpus is a no-op):

```python
from fhir4ds.dedup import create_dedup_audit_table, load_dedup_audit

create_dedup_audit_table(conn)          # call once on your connection
rows = load_dedup_audit(conn, run_id="dedup-001")
```

Pass `include_singletons_in_audit=True` to also record one row per non-duplicate resource.

## 8. Where to go next

- [Patient Matching](/docs/user-guide/matching/patient-matching) — the identity layer that groups records into individuals before resource dedup runs.
- [Dedup API Reference](/docs/api-reference/dedup/) — normalizers, partition/escalate primitives, and the full runner surface.
