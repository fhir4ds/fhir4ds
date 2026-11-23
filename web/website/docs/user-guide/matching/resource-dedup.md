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

**Medication references are resolved when present.** MedicationRequest, MedicationDispense and MedicationAdministration may carry `medication[x]` as a `medicationReference` instead of an inline code. The resolver works strictly within the input corpus, contained-first (`#<id>` fragments against the same resource's `contained` list — the dominant real-world pattern), then corpus-wide (`Medication/<id>`, anchored-tail matched, `_history`-stripped). A resolved Medication's codings join the resource's key with provenance `reference_resolved` (a hybrid-tier participant — see §3). An unresolved reference never unions: the record stays a singleton and lands in the curation queue as `unresolved_medication_reference`. Immunization carries its `vaccineCode` inline, so no resolution applies.

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

## 3. The tiered code cascade

When two resources in the same patient/temporal/value bucket carry *disjoint* code sets, dedup coalesces every resource onto **one match key** through a three-tier cascade (AMUX-145 design; see `fhir4ds/dedup/concept_index.py`):

| Priority | Tier | Rule | Merge provenance |
|---|---|---|---|
| **1** | Canonical | Literal `(system, code)` set intersection. Intersecting code sets never fall through to lower tiers. | `canonical` |
| **2** | Hybrid | The resource's display text is resolved against the bundled concept index (LOINC, SNOMED, RxNorm, CVX — built deterministically from the expanded ValueSet fixtures) using hybrid retrieval = **BM25 + character-trigram fuzzy**, no model artifact. A *confident* resolution (top-1 score at or above the threshold AND a clear margin over the runner-up) assigns the resolved canonical concept to the resource's key — so a LOINC/SNOMED twin pair merges through ordinary partitioning. Unconfident resolution falls through. | `hybrid` (+ index version, score, and margin in the audit trail) |
| **3** | Text | Still-unresolved resources key on the conservative normalized display text (casefold, NFKC, punctuation, UCUM unit aliases — no stemming, no synonyms: "Hemoglobin" must never bucket with "Hemoglobin A1c"). Resolved concepts **outrank** display equality: equal text with different confident canonical keys never merges. | `text` |

Medication resources whose concept arrives by **reference resolution** (a `medicationReference` dereferenced to a `Medication.code`) participate through the hybrid tier; `code_fallback="off"` restricts matching to the canonical tier only while still counting reference-resolved records.

Anything the cascade cannot decide lands in the deterministic curation queue (§6) for human/terminology review — proposals may only *add* queue entries. Control the fallback tiers with `code_fallback="on" | "audit_only" | "off"`:

```python
result = run_dedup(resources, run_id="dedup-002", code_fallback="audit_only")
```

## 4. Resources without codes

Encounters, Practitioners, Organizations and Locations have **no code to put in an event key** — each gets a strategy chosen by what the resource *does* uniquely have: encounters on time, identity resources on identifiers. Both strategies feed the same survivorship, curation and audit machinery as the coded pass.

### Encounters — matched by time

Encounters are deduplicated by **temporal overlap** — one visit split into overlapping segments. As with patient matching, a patient-membership map from [patient matching](/docs/user-guide/matching/patient-matching/) can be supplied so cross-patient encounters can never merge.

Overlap alone merges (≥80% shared period, or a ≤15-minute handoff gap on the same day); beyond the temporal core, the scorer adds **identity-style corroboration from the encounter's own references** — a shared practitioner participant, the same organization (`serviceProvider`), or a shared location each add evidence (references compared by their trailing id, the same convention used throughout matching):

| Signal | Contribution |
|---|---|
| Period overlap ≥ 80% | merges on its own (temporal core) |
| Handoff gap ≤ 15 min, same local day | temporal core (ED-to-admit) |
| ≥ 1 shared practitioner / same organization / shared location | corroborating evidence |
| Identical class, service type, or shared reason codes | minor corroboration |

**Known-distinct guard:** two emergency-department visits for the same patient with disjoint periods ≥ 2 hours apart are treated as genuinely separate visits — they never merge directly, *and* a chain of merges that would indirectly pull them into one cluster is refused. Refused merges are recorded for review (`encounter_edge_refused` curation entries) rather than silently dropped.

```python
from fhir4ds.dedup import run_encounter_dedup

result = run_encounter_dedup(encounters, run_id="enc-001")
result.stats   # clusters, refused edges, merges
```

### Practitioners, organizations, locations — matched by identifiers

**Practitioner**, **Organization**, and **Location** duplicates are resolved through the *matching engine* with per-entity rule sets (`fhir4ds/matching/entity_rules.py`), not through `run_dedup`'s code cascade:

```python
import duckdb
from fhir4ds.matching import (
    index_entity, match_corpus,
    extract_practitioner_fields,
    PRACTITIONER_RULES,
)

con = duckdb.connect()
prac = {"resourceType": "Practitioner", "id": "prac-1",
        "identifier": [{"system": "http://hl7.org/fhir/sid/us-npi",
                        "value": "1234567890"}],
        "name": [{"family": "Chalmers", "given": ["Peter"]}]}

index_entity(con, "Practitioner", prac,
             extract_practitioner_fields(prac))   # shared field-value index
# ... index every practitioner, then one corpus pass:
report = match_corpus(con, "run-prac-001",
                      rules=PRACTITIONER_RULES,
                      entity_type="Practitioner")
report.counts   # audited matches -> one FHIR Linkage per matched pair
```

Three design rules distinguish entity matching from patient matching:

- **A strict evidence bar is enforced.** Unlike patient matching — where a borderline link is left for review — entity matching *refuses* a candidate unless the evidence clears a fixed bar: either a strong identifier agrees on its own (an NPI, a shared phone-plus-name-plus-address combination), or a weaker match is backed by additional fields that agree exactly. The bar is set per entity type (strictest for practitioners and organizations, slightly looser for locations) and is deliberately higher than what it takes to merge two records for the *same* patient — mis-merging two different clinics or providers is costlier than a missed duplicate.
- **Name-only NEVER links an entity.** A surname is shared across one facility's practitioners and every city has an "Imaging Center" — every rule anchors on at least one hard identifier (NPI, phone, address, email, geo coordinates).
- **Strong identifiers link on their own.** Two practitioners sharing an NPI are the same person — NPIs are issued unique, so no further agreement is needed. Organization and location rules combine phone, address and geo-coordinate anchors, with fuzzy agreement on names and guards against near-miss look-alikes.

The O5 organization rule (shared chain-pharmacy phone pools) ships **disabled** — enable only if measurement on real corpora shows recall loss.

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

- [Patient Matching](/docs/user-guide/matching/patient-matching/) — the identity layer that groups records into individuals before resource dedup runs.
- [Dedup API Reference](/docs/api-reference/dedup/) — normalizers, partition/escalate primitives, and the full runner surface.
