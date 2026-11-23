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

### Category-1 rules and P(collision)

The default table `CATEGORY1_RULES` is the 29-rule CMS Category-1 set. Each rule is a conjunction of field modes — `EXACT`, `FUZZY` (Damerau-Levenshtein ≤ 1 on names ≥ 5 chars, nickname groups, prefix abbreviations; DOB ± 1 day) — with a P(collision) derived from per-field u-probabilities:

```python
from fhir4ds.matching import CATEGORY1_RULES, FIELD_U_PROBS, APPROVAL_THRESHOLD

len(CATEGORY1_RULES)              # 29
APPROVAL_THRESHOLD                # 2e-12
FIELD_U_PROBS["dob"]              # (0.0001, None) — (exact, fuzzy) u-values
FIELD_U_PROBS["first"]            # (0.02, 0.03)
```

A rule fires only when every field matches *and* the evidence product stays under budget, so weak evidence (a fuzzy name alone) never links two records — the hard anchors (DOB, SSN4, phone, address) must corroborate.

### Name-embedding E-rules (v0.0.26)

Edit distance cannot see transliterations (`Mohammed` → `Muhummad`, DL ≥ 2). fhir4ds 0.0.26 ships a small **purpose-trained char-level name embedding** (~85k params, 16-dim, trained with triplet loss on equivalent-name pairs; pure-NumPy inference — no torch, ~350 KB artifact pinned by hash):

```python
from fhir4ds.matching import (
    embedding_rules, patient_rules_with_embedding, name_distance_band,
)

embedding_rules()                      # the additive E1-E3 rules
len(patient_rules_with_embedding())    # 32 = 29 Category-1 + 3 E-rules
name_distance_band("mohammed", "muhummad")  # 'tight' — a calibrated band, or None
```

Each E-rule embeds one or both name fields; the cosine distance falls into a **calibrated band** (tight / mid / loose) whose u-value was measured over ~1M distinct-name pairs, exactly like the upstream Table-3 values. A band that cannot appear in an approvable rule product ships in no rule — the same discipline as Category-1. E-rules are additive and ordered *after* the Category-1 table, so they only ever fire on pairs the exact/fuzzy comparators already rejected.

Adoption was gated on two referees (see `fhir4ds/matching/evaluation/` for the harness): on the ONC real-corpus benchmark (14,295 pairs) **precision stays 1.0000 with zero new false positives** while recall rises 0.9380 → 0.9394; on a transliteration-heavy held-out set, **recall rises 0.05 → 0.71**.

Disable per call with `match_patient(conn, patient, use_embedding=False)`; if the artifact is absent or fails its hash check, the engine logs one warning and behaves exactly as `CATEGORY1_RULES`.

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
