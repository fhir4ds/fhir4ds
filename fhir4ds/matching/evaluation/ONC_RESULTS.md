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

### Before/after the AMUX-134 nickname/abbreviation expansion (same day, same corpus)

| metric | before | after | Δ |
|---|---|---|---|
| precision | 1.0000 | **1.0000** | 0 (still 0 FP across all 574 negatives) |
| recall | 0.9049 | **0.9380** | +3.31 pp |
| F1 | 0.9501 | **0.9680** | +1.79 pp |
| TP / FP / FN / TN | 12,416 / 0 / 1,305 / 574 | **12,870 / 0 / 851 / 574** | +454 TP |
| `fuzzy_variant/given_abbreviate` misses | 142 / 213 (66.7%) | **4 / 213 (1.9%)** | −138 |
| `fuzzy_variant/given_nickname` misses | 52 / 96 (54.2%) | **32 / 96 (33.3%)** | −20 |
| all given_abbreviate/nickname-containing misses | 1,006 | **564** | −442 |
| compound_variant misses | 884 / 1,801 (49.1%) | **598 / 1,801 (33.2%)** | −286 |
| fuzzy_variant misses | 285 / 1,804 (15.8%) | **125 / 1,804 (6.9%)** | −160 |
| ambiguous outcomes | 0 | 0 | — |
| engine crashes | 0 | 0 | — |

The AMUX-134 change (nickname table 50→220 sets + guarded prefix/initial
abbreviation in `name_fuzzy_match`) removed 454 misses with zero precision
cost. Remaining given-name miss mass is almost entirely given-name ×
DOB-mutation compounds (`dob_year/month/typo/swap + given_abbreviate`, ~470
of the 564), which need compound-tolerance (follow-up 2 below), not more
nickname coverage. The residual `given_nickname` misses (32) are
non-English names abbreviated to initials not covered by any safe English
family (e.g. `zeinab`→`z`, `samiya`→`s` are initial-only and ARE covered —
the rest are cross-lingual diminutives deliberately excluded).

### Original baseline (pre-expansion)

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

## False negatives by rationale family (after AMUX-134; original in parentheses)

| family | misses / total | miss rate | was |
|---|---|---|---|
| compound_variant (two mutations) | 598 / 1,801 | 33.2% | 884 (49.1%) |
| fuzzy_variant (single mutation) | 125 / 1,804 | 6.9% | 285 (15.8%) |
| phone_churn | 48 / 961 | 5.0% | 48 (5.0%) |
| placeholder | 30 / 285 | 10.5% | 30 (10.5%) |
| marriage_variant | 21 / 2,000 | 1.1% | 21 (1.1%) |
| surname_address_change | 5 / 166 | 3.0% | 11 (6.6%) |
| surname_change | 7 / 303 | 2.3% | 9 (3.0%) |
| ssn_dropped | 9 / 1,504 | 0.6% | 9 (0.6%) |
| normalization_edge_case | 5 / 3,929 | 0.1% | 5 (0.1%) |
| email_churn | 2 / 499 | 0.4% | 2 (0.4%) |
| address_move | 1 / 365 | 0.3% | 1 (0.3%) |

## Top miss families — what the engine can't catch (post-AMUX-134)

1. **Given-name × DOB compounds** now dominate: ~470 remaining misses pair
   an abbreviated/nickname given name with a DOB mutation
   (`dob_year + given_abbreviate` 51, `dob_month + given_abbreviate` 47,
   `dob_typo + given_abbreviate` 31, ...). The given-name side is now
   matched (table + prefix rule); these miss because no rule tolerates the
   simultaneous DOB deviation. See follow-up 2.
2. **Given-name nickname residual** (`fuzzy_variant/given_nickname`:
   32/96): cross-lingual diminutives (Arabic/Spanish/Russian names
   abbreviated non-phonetically) deliberately excluded from the English
   table — unsafe without a curated multilingual list.
3. **Phone churn** (dropped/replaced numbers, 48 misses) — when both phone
   and another field changed, no rule's field set survives.
4. Smaller tails: `placeholder` values (30 — placeholder given/phone strings
   are not treated as missing/wildcard), `marriage_variant` surname changes
   without name history (21), `surname_address_change` (5).

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

## Recommended follow-ups (updated 2026-11-17 after AMUX-134)

1. ~~Nickname/abbreviation-aware first-name comparison~~ — **DONE
   (AMUX-134)**: nickname table expanded 50→220 standard English families
   (`normalizers._NICKNAME_GROUPS`, union-of-groups indexing so shared
   diminutives like chris/ted/jo are symmetric without equating their
   formal names), plus guarded prefix abbreviation in
   `fuzzy.name_fuzzy_match` (>=4-char truncation OR single leading
   initial; 2-3-char ambiguous fragments excluded). Precision held at
   1.0000 (the 11 negative pairs whose given names are initial-vs-fullname
   all remain rejected — other rule fields discriminate them); recall
   0.9049 → 0.9380.
2. **Compound-tolerance** (now the largest lever: ~470 remaining misses
   are given-name × DOB-mutation compounds): a guarded rule variant
   tolerating two simultaneous fuzzy deviations (e.g. abbreviated given
   + dob year) when SSN4 or phone agrees exactly.
3. **Placeholder handling**: treat upstream placeholder phone/given values
   as missing rather than as evidence (30 misses, unchanged).
4. Re-run this gate after any such change; the regression gate plus this
   report's per-family table will show exactly which families moved.
