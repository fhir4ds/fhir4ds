# BENCHMARKS — v0.0.18 release prep (REVISED after rerun + attribution)

## Rerun + attribution (2026-10-24, Joel-requested)

Three-way comparison on identical /tmp worktrees (same disk, host idle):

| Phase | Baseline (May) | S24 pre-campaign | HEAD (0.0.18) | S24/base | HEAD/S24 |
|---|---|---|---|---|---|
| library_translation | 20.3s | 24.1s | 23.3s | 1.19x | **0.97x** |
| sql_generation | 25.4s | 35.4s | 35.1s | 1.39x | **0.99x** |
| sql_execution | 13.8s | 16.6s | 16.2s | 1.20x | **0.98x** |
| total | 60.9s | 77.1s | **75.5s** | 1.27x | **0.98x** |

- The 60.9s → 86.7s (1.42x) first measurement mixed TWO factors: the stale
  May baseline (1.27x pre-existing correctness-surface growth, already present
  at S24 — e.g. CMS2 sql_gen 6.7s→13.2s unchanged by the campaign) and a
  ~12% /mnt/d drvfs disk penalty in the original measurement location.
- On matched disks the campaign is **performance-neutral (0.98x)** — the
  translation LRU cache offsets the added audit/type surfaces.
- Accuracy: 100% on all 47 measures at S24 and HEAD. Run-to-run stability:
  median 1.014 across reruns.

## Original single-run numbers (kept for the record)

- Measures compared: **47** (skipped without timing data: _summary)
- Accuracy: **100% on all compared measures**
- Total time: baseline 60.9s -> current 86.7s (1.42x)
- Median per-measure ratio: **1.12x**; regressions >1.25x: **16**

| Measure | Baseline (s) | Current (s) | Ratio | SQL size ratio |
|---|---|---|---|---|
| CMS0334 | 8.38 | 13.41 | 1.60x | 1.17x |
| CMS1017 | 1.53 | 2.01 | 1.31x | 1.03x |
| CMS1056 | 0.68 | 0.72 | 1.06x | 0.98x |
| CMS117 | 1.80 | 2.08 | 1.16x | 1.00x |
| CMS1218 | 3.12 | 3.90 | 1.25x | 1.26x |
| CMS122 | 2.38 | 3.74 | 1.57x | 0.95x |
| CMS124 | 0.51 | 0.48 | 0.94x | 1.01x |
| CMS1244 | 0.78 | 1.12 | 1.44x | 1.01x |
| CMS125 | 1.60 | 2.64 | 1.65x | 0.96x |
| CMS1264 | 0.47 | 0.69 | 1.46x | 1.01x |
| CMS128 | 1.22 | 1.89 | 1.56x | 1.25x |
| CMS130 | 1.45 | 2.73 | 1.89x | 0.95x |
| CMS133 | 0.48 | 0.43 | 0.89x | 1.00x |
| CMS135 | 0.69 | 0.82 | 1.18x | 1.04x |
| CMS142 | 0.37 | 0.30 | 0.79x | 1.01x |
| CMS143 | 0.26 | 0.28 | 1.10x | 1.01x |
| CMS144 | 0.75 | 1.01 | 1.35x | 1.03x |
| CMS145 | 1.37 | 1.70 | 1.24x | 1.00x |
| CMS146 | 1.58 | 2.56 | 1.62x | 0.94x |
| CMS149 | 0.24 | 0.26 | 1.08x | 1.01x |
| CMS155 | 0.36 | 0.41 | 1.12x | 1.02x |
| CMS157 | 0.74 | 0.63 | 0.85x | 1.01x |
| CMS159 | 0.95 | 1.36 | 1.42x | 1.00x |
| CMS165 | 3.14 | 4.20 | 1.34x | 0.96x |
| CMS190 | 1.39 | 1.37 | 0.98x | 1.00x |
| CMS2 | 11.58 | 22.24 | 1.92x | 0.86x |
| CMS22 | 0.56 | 0.58 | 1.03x | 1.00x |
| CMS349 | 0.28 | 0.30 | 1.08x | 1.06x |
| CMS50 | 0.28 | 0.35 | 1.23x | 1.00x |
| CMS506 | 0.52 | 0.65 | 1.26x | 1.00x |
| CMS56 | 0.67 | 0.69 | 1.02x | 1.00x |
| CMS645 | 0.50 | 0.56 | 1.13x | 1.02x |
| CMS646 | 0.44 | 0.50 | 1.12x | 1.00x |
| CMS68 | 0.21 | 0.20 | 0.96x | 1.02x |
| CMS69 | 0.72 | 0.72 | 0.99x | 1.00x |
| CMS71 | 0.76 | 0.78 | 1.02x | 1.01x |
| CMS72 | 0.79 | 0.77 | 0.98x | 1.00x |
| CMS74 | 0.36 | 0.34 | 0.95x | 1.03x |
| CMS75 | 0.65 | 0.60 | 0.92x | 1.01x |
| CMS771 | 0.43 | 0.49 | 1.12x | 1.00x |
| CMS816 | 0.53 | 0.40 | 0.76x | 1.01x |
| CMS819 | 0.31 | 0.34 | 1.10x | 1.01x |
| CMS826 | 0.39 | 0.41 | 1.04x | 1.01x |
| CMS832 | 2.81 | 3.21 | 1.14x | 1.04x |
| CMS871 | 0.76 | 0.67 | 0.89x | 0.98x |
| CMS986 | 0.38 | 0.60 | 1.58x | 1.00x |
| CMS996 | 0.67 | 0.57 | 0.84x | 1.00x |

Source: `conformance/reports/dqm_report.json` vs `benchmarks/baselines/dqm_2025.json` (single run, same host). SQL-size growth reflects added correctness surfaces (AGENTS.md CQL doctrine).
