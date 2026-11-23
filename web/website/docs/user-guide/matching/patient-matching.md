---
id: patient-matching
title: Patient Matching
sidebar_label: Patient Matching
description: "Deterministic, probabilistic patient matching in DuckDB: CMS Category-1 rules with P(collision) budgets, fuzzy comparators, name-embedding E-rules, corpus passes, FHIR Linkage output and the ingest hook."
---

# Patient Matching

Real corpora arrive fragmented: the same human exists as `Patient/p1` in the EHR feed and `Patient/99` in the lab feed. The `fhir4ds.matching` package links those records with a **deterministic, rule-based engine** whose decisions are auditable, reproducible, and written as standard FHIR `Linkage` resources — it **never merges or mutates** your source data.

Three properties distinguish the engine:

1. **Probabilistic budgets.** Every rule carries a P(collision) — the probability that two *different* people would satisfy the rule (upstream CMS Table-3 u-probability products). A pair links only when a rule's whole evidence product stays under the approval budget (`2e-12`).
2. **Full determinism.** No wall-clock, no RNG, no model drift: the same corpus produces byte-identical decisions, Linkage resources, and audit rows on every run.
3. **Evidence, not mutation.** Output is a `Linkage` resource per matched pair plus a match-decision audit table; downstream systems decide what to do with the graph.

## 1. Install

```bash
pip install fhir4ds-v2
```

Patient matching is part of the core package (pure Python + DuckDB).

## 2. Quickstart: match one patient against a corpus

```python
import duckdb
from fhir4ds.matching import index_patient, match_patient

conn = duckdb.connect()

# Build the corpus: index the patients you already have.
index_patient(conn, {
    "resourceType": "Patient", "id": "p1",
    "name": [{"family": "Montavon", "given": ["Joel"]}],
    "birthDate": "1966-05-18",
    "identifier": [{"system": "http://hl7.org/fhir/sid/us-ssn",
                    "value": "123-45-6789"}],
})

# Match a new arrival (a nickname of the given name, same anchors).
result = match_patient(conn, {
    "resourceType": "Patient", "id": "p2",
    "name": [{"family": "Montavon", "given": ["Joe"]}],
    "birthDate": "1966-05-18",
    "identifier": [{"system": "http://hl7.org/fhir/sid/us-ssn",
                    "value": "123-45-6789"}],
})

result.outcome     # 'match' | 'no_match' | 'ambiguous'
result.rule_id     # 'E1' — the name-embedding rule fired here
result.matched_ids # ('p1',)
result.evidence    # {'first': 'joe~joel|band=mid|model=name-embed-v1@860f1f59',
                   #  'last': 'montavon', 'dob': '1966-05-18', ...}
```

`match_patient` normalizes the resource (names, dates, phones, addresses), finds exact and fuzzy candidates in the `field_values` index, evaluates every rule, and returns the first (lowest-P) rule that links the pair.

## 3. The rule engine

The engine implements the **CMS-approved probabilistic matching methodology** — the Category-1 rule table and its evidence budgets, used as specified. fhir4ds adds exactly one deliberate extension (name embeddings for transliterated names, below), built to the same standard; everything else follows the methodology as published.

### The rule table

Probabilistic matching does not compare whole records — it compares them through a table of **rules**, each naming a small combination of fields that, when they *all* agree, is strong enough evidence on its own that two records describe the same person. The CMS methodology publishes its rule table ("Category-1"); fhir4ds ships it unchanged as `CATEGORY1_RULES`. A few of its 29 rules, to make the shape concrete:

- first name (exact) + date of birth + phone number
- first + last name (fuzzy) + date of birth (± 1 day) + street address
- first + last name (fuzzy) + date of birth + email address
- last name (fuzzy) + date of birth + insurance member ID

Two ideas do the work:

- **Some agreement is strong, some is weak.** An exact phone number or matching date of birth is strong evidence; a fuzzy name match alone is weak. Every field carries a measured weight for how likely two *different* people are to agree on it — a fuzzy first name agrees by chance far more often than a phone number does.
- **A rule is only as strong as its whole combination.** A rule fires only when *every* field agrees **and** the combined chance of coincidence stays under a strict budget. That is why the table never contains a names-only rule: weak evidence must always be corroborated by a hard anchor (date of birth, SSN4, phone, address, or an identifier).

```python
from fhir4ds.matching import CATEGORY1_RULES

len(CATEGORY1_RULES)   # 29 — the CMS Category-1 table, unchanged
```

Name "fuzzy" means a near match: one typo of edit distance, a nickname (Bill/William), or a common prefix abbreviation — with birth dates allowed one day either side. The full field weights and the budget constant are documented in the [API reference](/docs/api-reference/matching/).

### Name-embedding rules (our one deliberate extension)

The CMS rule set is built on exact and edit-distance name comparison, which cannot see transliterations — `Mohammed` and `Muhummad` are the same name to a human but two edits apart to the algorithm. This is the one place fhir4ds deliberately extends the approved methodology: three additional rules compare names through a small **purpose-trained name embedding** that recognizes equivalent spellings across writing systems.

The extension follows the same discipline as the CMS table itself, so it does not weaken the methodology:

- **Calibrated like any other field.** Name similarity becomes a field value with measured false-match rates (computed the same way the CMS u-values are), and the same approval budget applies — a rule only ships if its whole evidence product fits under it.
- **Additive and last.** The embedding rules sit *after* the CMS table and only ever see pairs the standard comparators already rejected — they can never change an existing decision, only recover misses.
- **Validated, not assumed.** On a real-record benchmark, adding the embedding rules produced **zero new false matches** while recovering substantially more true matches; on a deliberately transliteration-heavy set, recall went from near-zero to roughly seven in ten.
- **Safely optional.** Pass `use_embedding=False` to `match_patient` to disable it; if the model artifact is missing, the engine warns once and silently falls back to the standard rule table.

```python
from fhir4ds.matching import match_patient

match_patient(conn, patient)                     # embedding rules active
match_patient(conn, patient, use_embedding=False)  # CMS table only
```

### Threshold enforcement for identity entities

For non-Patient entities (Practitioner, Organization, Location) the rule tables are `RuleSet`s carrying an explicit `approval_threshold`, **enforced**: a rule whose effective P exceeds the budget links a candidate only when additional exactly-agreeing *independent* fields bring the combined probability back under it (CR-002). Enforcement decisions are recorded on `MatchResult.threshold_enforcement` and in the audit evidence. Patient matching never enforces a threshold — the CMS table has none.

## 4. Corpus pass: everyone vs everyone

```python
from fhir4ds.matching import (
    match_corpus, build_membership, individual_patients_view,
    find_contradictions,
)

report = match_corpus(conn, run_id="corpus-2026-11-22")
report.counts    # {'patients_evaluated': ..., 'match': ..., ...} (property)

# Connected components -> individual_id per patient id.
build_membership(conn)
individual_patients_view(conn)   # creates view `individual_patients`

# Hard contradictions inside a matched cluster (v1: surfaced, never auto-split).
contradictions = find_contradictions(conn)
```

The pass evaluates every indexed patient against the full corpus (self excluded), audits each decision under `run_id`, and upserts one Linkage per matched pair. Because each decision sees the complete corpus, re-running over an unchanged corpus re-audits but creates no new rows.

## 5. Ingest hook

Match new arrivals as they load, before they are indexed:

```python
from fhir4ds.matching import match_on_ingest, maybe_match_on_ingest

report = match_on_ingest(conn, [new_patient_resource], run_id="ingest-001")
report.matched          # ids that linked to an existing patient

# Flag-gated (strict no-op when disabled):
maybe_match_on_ingest(conn, resources, enabled=True, run_id="ingest-002")
```

Pass `link_threshold={"match", "ambiguous"}` to also link ambiguous pairs for human-review workflows.

## 6. FHIR Linkage and audit output

Every `match` upserts a deterministic FHIR R4 `Linkage` resource into the `linkage` table (canonical pair keys — no timestamps, so re-runs are idempotent), and every decision (including refusals) is audited:

```python
from fhir4ds.matching import (
    create_audit_tables, create_linkage_tables, upsert_linkage,
    build_linkage_resource, MATCHING_EXTENSION_URL,
)

create_linkage_tables(conn)
create_audit_tables(conn)
upsert_linkage(conn, result, "p2", "p1")
# {"action": "created", "linkage_id": "...", "resource": {...Linkage...}}
```

The firing rule id and — for E-rules — the model name and version ride in the Linkage extension (`MATCHING_EXTENSION_URL`), so embedding-driven links are identifiable and reversible by deletion.

## 7. Identity entities and RelatedPerson

The same engine matches Practitioners, Organizations and Locations through per-type extractors and rule tables, and deduplicates `RelatedPerson` records by piggybacking on patient membership:

```python
from fhir4ds.matching.engine import match_fields
from fhir4ds.matching import (
    extract_practitioner_fields, PRACTITIONER_RULES, match_related_persons,
)

match_fields(
    conn, extract_practitioner_fields(practitioner_resource),
    entity_type="Practitioner", rules=PRACTITIONER_RULES,
)

report = match_related_persons(conn, run_id="rp-001", related_persons=rps)
```

See the [Matching API Reference](/docs/api-reference/matching/) for the full surface.

## 8. Where to go next

- [Resource Deduplication](/docs/user-guide/matching/resource-dedup/) — temporal duplicate resources (Observations, Conditions, Encounters) inside one patient's record.
- [Terminology Service](/docs/user-guide/terminology/terminology-service/) — the code-system knowledge that dedup's canonical tier resolves against.
