# ONC 2017 Real-Corpus Matching Results (AMUX-134)

Real-data measurement of the fhir4ds matching engine against the upstream
ONC-derived labeled pair set
(`icanbwell/cms-hte-patient-matching-test-set` tag `0.0.6`,
`sample_labeled_pairs.jsonl` — 14,295 labeled pairs, fetched by
`fhir4ds.matching.scripts.fetch_onc_test_data`, gitignored).

Method: **pairwise evaluation** (each pair an isolated two-patient decision —
index both, match the source with `exclude={source_id}`, target is the only
candidate). Outcome `match` = predicted positive; `ambiguous` = not matched
(recall miss, never a false positive — same convention as the synthetic
golden gate; in practice zero ambiguous outcomes occurred). Full set, no
sampling: 227 s wall clock (~16 ms/pair) on one shared connection with
per-pair row deletion (verified isolation-equivalent to a fresh connection
per pair, which measures ~6.5 min).

## Headline numbers (2026-11-17, branch `dev` @ 5a8138164aa)

| metric    | value  |
|-----------|--------|
| cases     | 14,295 (13,721 expected-match / 574 expected-non-match) |
| TP / FP / FN / TN | 12,416 / **0** / 1,305 / 574 |
| **precision** | **1.0000** |
| **recall**    | **0.9049** |
| F1        | 0.9501 |
| ambiguous outcomes | 0 (all misses are outright `no_match`) |
| engine crashes | 0 |

The engine made **zero false positives** across all 574 negatives — including
every adversarial family (sibling negatives with age gaps, name-collision
negatives, placeholder-collision negatives). Specificity is perfect on this
corpus. The cost of that conservatism is recall: 1,305 missed duplicates.

## False negatives by rationale family

| family | misses / total | miss rate |
|---|---|---|
| compound_variant (two mutations) | 884 / 1,801 | 49.1% |
| fuzzy_variant (single mutation) | 285 / 1,804 | 15.8% |
| phone_churn | 48 / 961 | 5.0% |
| placeholder | 30 / 285 | 10.5% |
| marriage_variant | 21 / 2,000 | 1.1% |
| surname_address_change | 11 / 166 | 6.6% |
| surname_change | 9 / 303 | 3.0% |
| ssn_dropped | 9 / 1,504 | 0.6% |
| normalization_edge_case | 5 / 3,929 | 0.1% |
| email_churn | 2 / 499 | 0.4% |
| address_move | 1 / 365 | 0.3% |

## Top miss families — what the engine can't catch

1. **Given-name abbreviation is the dominant miss driver by far.** 809 of
   1,305 misses (62%) contain a `given_abbreviate` mutation
   ("KATHERINE" → "KATHY" class), at a ~68% miss rate in isolation
   (`fuzzy_variant/given_abbreviate`: 142/213 missed) and 50–85% miss rates
   in every compound variant it participates in. The fuzzy first-name
   comparators do not model abbreviation/nickname equivalence.
2. **Given-name nickname** is the second single-mutation family
   (`fuzzy_variant/given_nickname`: 52/96 missed, 54%). Together,
   abbreviation + nickname account for **1,006 of 1,305 misses (77%)**.
3. **Compound variants** (any two simultaneous mutations, e.g.
   `family_typo + given_abbreviate`, `dob_year + given_abbreviate`) miss at
   ~49% overall — mostly because one of the two mutations is usually a
   given-name variant (see 1–2); pure family/dob compounds miss at only
   ~5–15%.
4. **Phone churn** (dropped/replaced numbers, 48 misses) — when both phone
   and another field changed, no rule's field set survives.
5. Smaller tails: `placeholder` values (30 — placeholder given/phone strings
   are not treated as missing/wildcard), `marriage_variant` surname changes
   without name history (21), `surname_address_change` (11).

## What works well

- SSN-dropped pairs still match at 99.4% (fallback rules carry them).
- Normalization edge cases (punctuation, diacritics) match at 99.9%.
- Address moves, email churn, and single phone changes are essentially free.
- All negative families — including the hard sibling/collision negatives —
  are correctly rejected with no false positives and no ambiguity.

## Crash safety on ONC data shapes

None found: 0 exceptions across 14,295 pairs (real ONC Patient shapes —
SSN identifiers with v2-0203 coding, ranked telecom, structured addresses —
all pass through `extract_patient_fields`/`index_patient`/`match_patient`
cleanly). No engine guards were needed.

## Gate semantics

`tests/test_matching_onc_gate.py::test_onc_real_corpus_regression_gate`
(slow-marked, skips cleanly when the fixture is absent) re-runs the full
evaluation and compares against `evaluation/onc_baseline.json`:
precision/recall may not drop more than 0.02 below baseline, the fixture
size must match, and crash count must not exceed baseline (0). Absolute
recall is deliberately NOT asserted — real-world recall is information, not
a bug. Re-record the baseline after intentional engine changes:

```bash
python3 -m fhir4ds.matching.evaluation.onc_gate --write-baseline
```

## Recommended follow-ups (NOT implemented — this task measures)

1. **Nickname/abbreviation-aware first-name comparison** (largest single
   lever: up to ~77% of current misses). Options: a nickname equivalence
   table (KENNETH↔KEN, KATHERINE↔KATHY...) or a fuzzy first-name mode with
   prefix-abbreviation allowance; must be guarded so the 70
   `name_collision_negative` and 300 `placeholder_collision_negative` cases
   stay rejected — precision is currently perfect and should not be traded
   away cheaply.
2. **Compound-tolerance**: a guarded rule variant tolerating two
   simultaneous fuzzy deviations (e.g. family typo + dob year) when SSN4 or
   phone agrees exactly.
3. **Placeholder handling**: treat upstream placeholder phone/given values
   as missing rather than as evidence (30 misses).
4. Re-run this gate after any such change; the regression gate plus this
   report's per-family table will show exactly which families moved.
