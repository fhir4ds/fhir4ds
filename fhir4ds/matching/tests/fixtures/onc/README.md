# ONC-derived labeled pair fixtures (NOT COMMITTED)

This directory holds fetched upstream test data for a future ONC matching
gate. The data files are gitignored — run the fetch script to populate:

```bash
python3 -m fhir4ds.matching.scripts.fetch_onc_test_data             # sample set (~17 MB)
python3 -m fhir4ds.matching.scripts.fetch_onc_test_data --list      # all choices
```

Source: `icanbwell/cms-hte-patient-matching-test-set`, pinned tag `0.0.6`
(commit `e4cf29e77e5c4e73cba661bffea00fd4fc1543c9`).

What is fetched: the exported **labeled pair JSONL** files under
`evaluation/cases/` — one `{case_id, source, target, expected_match,
rationale}` record per line, where `source`/`target` are complete FHIR R4
Patient resources. The raw ONC challenge CSV shards vendored upstream
(`evaluation/fixtures/onc/`, ~120 MB, nine files) are NOT fetched: upstream's
own `onc_loader.py` documents that this copy has 1,000,000 rows with all
distinct EnterpriseIDs — no duplicate-pair answer key — so the CSVs are pair
*generation* input, while the JSONL exports are the ready-made labeled pairs.

After fetching, `onc_fetch_meta.json` records tag/commit/URL/sha256
provenance, and the loader test
(`fhir4ds/matching/tests/test_matching_onc_loader.py`) stops skipping and
exercises `load_onc_pairs` end-to-end.
