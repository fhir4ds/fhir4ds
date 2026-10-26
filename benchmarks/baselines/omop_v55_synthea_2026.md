# OMOP v5.5 on real data — Synthea 25-patient cohort (v0.0.19 / session 2026-10-26)

Environment: WSL2, DuckDB 1.5.x desktop, Python 3.10, fhir4ds 0.0.19.
Data: `fhir4ds/omop-demo` Hugging Face dataset — 25-patient Synthea R4
cohort (seed 20261026) + 71,444-concept RxNorm ConceptMap shipped as
3,573 chunked ConceptMap resources (20 elements each).

| Bundle | Resources staged | Staging | Composition (15 views) | Table rows |
|---|---|---|---|---|
| patients | 26 | 12 ms | 458 ms | person 25 |
| encounters | 1,310 | 582 ms | 445 ms | person 25, visit_occurrence 1,284 |
| medications | 5,087 | 2,375 ms | 444 ms | person 25, drug_exposure 1,488 |

Browser (DuckDB-WASM + Pyodide, production build, local network):
medication bundle renders 1,170 rows (ViewDefinition arm) in ~29 s from
sample selection; the remote smoke e2e completes person → medications
(1,170 rows, >1,000 concepts resolved) in ~42 s with HF-hosted data.

Notes:
- Composition cost is plan-time and flat (~450 ms) regardless of bundle.
- Staging dominates the medication bundle (chunked ConceptMap rows).
- A monolithic 157k-element ConceptMap is NOT loadable: DuckDB (desktop
  and WASM) exhausts memory unnesting JSON arrays that size. Hence the
  chunked transport and the 3-class subset (Ingredient / Clinical Drug /
  Branded Drug ⇒ ~90% cohort coverage; unmapped codes surface concept 0
  by design).
