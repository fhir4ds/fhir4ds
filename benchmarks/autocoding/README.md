# AutoCoding & Annotations Benchmarks

Scaling benchmarks for the fhir4ds AutoCoder (text-only CodeableConcepts →
coded Codings) and the medterm4ds annotations engine (NER `$extract`),
both **in-process** — the production path for bulk work.

Results and narrative: `benchmarks/baselines/autocoding_scaling_2026.md`.

## Prerequisites

- `pip install 'fhir4ds-v2[terminology]'` (medterm4ds pinned per
  `pyproject.toml`; these baselines were recorded on **medterm4ds 0.0.10**)
- The terminology release cached locally
  (`~/.cache/medterm4ds/terminology/<release>/`, repo `fhir4ds/terminology`)
- Synthea s100k FHIR corpus (see `benchmarks/scaling/omop_common.py` for the
  expected path, or pass your own)
- **Annotations only:** a `numpy<2` virtualenv — thinc 8.2.x is binary
  incompatible with numpy 2.x. Create once:
  ```bash
  python3 -m venv --system-site-packages <dir>
  <dir>/bin/pip install "numpy<2"
  ```

## Usage

```bash
# 1. Stage the workload (one pass over Synthea -> workload.ndjson)
python3 stage_corpus.py

# 2. AutoCoding ladder (main interpreter)
python3 bench_autocoding.py

# 3. Annotations ladder (numpy<2 venv)
<venv>/bin/python bench_annotations.py
```

Each script writes a `results_*.json` next to itself. Wall times on the
reference machine (i9-13900KF, 62 GiB): ladder ≈ 15 min, annotations ≈ 45 min.
Run the two ladders **serially** — concurrent runs contend for CPU and distort
the timings.

## Notes

- `bench_autocoding.py` drives the scored semantic engine
  (`medterm4ds.services.search.search(mode="semantic")`) through a
  benchmark-only endpoint. This is the engine the HTTP surface serves; the
  shipped in-process adapter currently routes to the unscored discovery
  service (see the baseline's findings section).
- Rung sizes in `bench_annotations.py` are tuned to measured per-word cost
  (~10–19 ms/word); adjust before pointing at longer notes.
