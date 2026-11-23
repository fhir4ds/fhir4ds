---
id: matching
title: fhir4ds.matching
sidebar_label: matching
description: "API reference for fhir4ds.matching: deterministic patient and identity-entity matching over DuckDB — rules, P(collision) budgets, name embeddings, corpus passes, Linkage output and audit."
---

# `fhir4ds.matching`

The `fhir4ds.matching` module implements deterministic, probabilistic patient matching: CMS Category-1 rules with P(collision) budgets, fuzzy comparators, a pinned name-embedding model, corpus passes with connected components, and FHIR R4 `Linkage` output. It never merges source data — every decision is auditable evidence.

```python
import fhir4ds.matching as m
```

---

## 1. Single-record matching

### `match_patient(...)`

```python
match_patient(conn, patient_resource, exclude=frozenset(), *,
              use_embedding=True) -> MatchResult
```

| Parameter | Type | Description |
|---|---|---|
| `conn` | `duckdb.DuckDBPyConnection` | Connection holding the `field_values` index. |
| `patient_resource` | `dict` | A FHIR Patient resource. |
| `exclude` | `frozenset[str]` | Patient ids dropped from every candidate pool (ingest/corpus determinism). |
| `use_embedding` | `bool` | Evaluate the additive E1–E3 embedding rules (inert when the artifact is absent). |

### `match_fields(...)`

The generalized entry point (`fhir4ds.matching.engine.match_fields`) — same engine, any entity type and rule table:

```python
match_fields(conn, fields, exclude=frozenset(), *,
             rules=CATEGORY1_RULES, entity_type="Patient",
             approval_threshold=None) -> MatchResult
```

For non-Patient entities, an `approval_threshold` (explicit or from a `RuleSet`) is **enforced** (CR-002): an over-budget rule links a candidate only when additional exactly-agreeing independent fields bring the combined probability back under budget. The decision is recorded on `MatchResult.threshold_enforcement` and in the audit evidence.

### `MatchResult`

| Field | Type | Description |
|---|---|---|
| `outcome` | `str` | `'match'` \| `'no_match'` \| `'ambiguous'`. |
| `rule_id` | `str \| None` | The firing rule. |
| `confidence` | `float \| None` | Rule P(collision). |
| `matched_ids` | `tuple[str, ...]` | Linked candidate ids. |
| `evidence` | `dict[str, str]` | Per-field audit (e.g. `'first': 'mohammed~muhummad\|band=mid\|model=name-embed-v1@bbafd8fb'`). |
| `match_type` | `str` | `'exact'` \| `'fuzzy'`. |
| `threshold_enforcement` | `dict \| None` | CR-002 decision (non-Patient entities only). |

## 2. Rules and probabilities

| Export | Description |
|---|---|
| `CATEGORY1_RULES` | The 29-rule CMS Category-1 table. |
| `FIELD_U_PROBS` | Per-field (exact, fuzzy) u-probabilities. |
| `APPROVAL_THRESHOLD` | The Patient-table product budget (`2e-12`). |
| `MatchRule` | Rule dataclass (field modes, P(collision), guards, `band_u_values`). |
| `EMBED` | The name-embedding field mode. |
| `BAND_EDGES` / `BAND_U_VALUES` | Calibrated embedding distance bands (tight/mid/loose) and their u-values. |
| `embedding_rules()` | The additive E1–E3 rules (empty when the artifact is absent/corrupt). |
| `patient_rules_with_embedding()` | `CATEGORY1_RULES` + E-rules, ordered Category-1-first. |
| `p_collision` | Helper computing a rule's evidence product. |
| `evaluate_rule(...)` | Evaluate one rule against a field map (diagnostics). |

Identity-entity rule tables (each a `RuleSet` with an enforced `approval_threshold`): `PRACTITIONER_RULES`, `ORGANIZATION_RULES`, `LOCATION_RULES` (+ their `*_APPROVAL_THRESHOLD` constants and `extract_practitioner_fields` / `extract_organization_fields` / `extract_location_fields`).

## 3. Name embedding

`fhir4ds.matching.name_embedding` is the pure-NumPy runtime for the pinned `name_embed_v1` artifact (hash-checked at load; warn-once degradation):

| Function | Description |
|---|---|
| `embed(name) -> ndarray` | 16-dim unit embedding. |
| `distance(a, b) -> float` | Clamped cosine distance. |
| `name_distance_band(a, b)` | The calibrated band — `'tight'`/`'mid'`/`'loose'` — or `None` when the pair is not close enough for any band (non-Latin names never band). |

## 4. Fuzzy comparators and normalizers

| Export | Description |
|---|---|
| `damerau_le1(a, b)` | Damerau-Levenshtein ≤ 1 test (names ≥ `FUZZY_NAME_MIN_LEN`). |
| `name_fuzzy_match(a, b)` | Nickname ∪ prefix-abbrev ∪ DL≤1 name equivalence. |
| `dob_fuzzy_matches(a, b)` | DOB ± 1 day. |
| `norm_date` / `norm_phone` / `norm_text` / `norm_name_parts` | CMS A–D normalizers. |
| `nickname_set(name)` | Nickname-group expansion. |
| `parse_suffix` / `suffix_conflict` | Name-suffix handling and negation guard. |
| `extract_patient_fields(resource)` | Patient resource → normalized field map. |

## 5. Index and store

| Export | Description |
|---|---|
| `create_matching_tables(conn)` | Idempotent DDL for `field_values`. |
| `index_patient(conn, resource)` | Extract + index one Patient (idempotent per id). |
| `index_entity(conn, entity_type, resource, fields)` | Index a pre-extracted entity. |
| `exact_candidates(conn, field, value, entity_type)` | Exact candidate ids for one field value. |
| `register_matching_macros(conn)` | Ad-hoc SQL helper macro. |

## 6. Corpus pass and membership

| Export | Description |
|---|---|
| `match_corpus(conn, run_id, *, rules, entity_type) -> CorpusReport` | Every indexed entity vs the full corpus (self excluded); audits + Linkage upserts. |
| `CorpusReport.counts` | Property: evaluated / match / ambiguous / no_match / links_created / unique_pairs. |
| `build_membership(conn)` | Connected components → `patient_membership` (member → individual id). |
| `individual_context_patients(conn)` | Individual ids with > 1 member. |
| `individual_patients_view(conn)` | Creates the `individual_patients` view. |
| `find_contradictions(conn)` | Hard contradictions inside matched clusters (surfaced, never auto-split). |
| `match_related_persons(conn, run_id, related_persons, *, membership)` | RelatedPerson dedup (RP1) + Linkage/audit. |

## 7. Linkage and audit

| Export | Description |
|---|---|
| `MATCHING_EXTENSION_URL` | Linkage extension carrying rule/model evidence. |
| `canonical_pair_key(a, b)` | Deterministic pair identity. |
| `build_linkage_resource(result, new_id, existing_id, entity_type)` | FHIR R4 Linkage dict. |
| `create_linkage_tables(conn)` / `upsert_linkage(...)` | Idempotent linkage storage. |
| `load_linkage_resources(conn)` | Read back Linkage rows as resources. |
| `create_audit_tables(conn)` / `record_match_audit(...)` | Decision audit (every outcome, including refusals). |

## 8. Ingest hook

| Export | Description |
|---|---|
| `match_on_ingest(conn, resources, run_id, link_threshold={"match"})` | Match each Patient before indexing it; create Linkage per outcome in `link_threshold`. |
| `maybe_match_on_ingest(conn, resources, *, enabled, run_id)` | Flag-gated wrapper; `enabled=False` is a strict no-op. |
| `IngestReport` | Matched ids, created links, decisions. |
