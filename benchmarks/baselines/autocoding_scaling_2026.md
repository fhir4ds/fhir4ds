# AutoCoding & Annotations Scaling Baseline (2026)

- Date: 2026-11-06 (overnight run)
- Machine: 13th Gen Intel i9-13900KF (32 threads), 62 GiB RAM, WSL2
- Engine: medterm4ds 0.0.10, terminology release `fhir4ds/terminology` `2026.11.05.1`, in-process (no HTTP)
- fhir4ds: dev tree (AutoCoder, DuckDB cache)
- Config: `search_mode=semantic`, `min_match_grade=probable`, `top_k=1`
- Corpus: Synthea s100k (132,569 text-only CodeableConcepts staged; 1,087 distinct texts — see Duplicate profile)
- NER env: numpy<2 venv (scispaCy/thinc binary compat; the main env's numpy 2.2 breaks thinc)

## Headline findings

1. **Dedup + cache make bulk autocoding cheap on real-world duplicate profiles.**
   100k text-only concepts: 154 s cold / 60 s warm-cache, 99% of rows never
   reach the engine; worst case (all-distinct) is ~17.6 concepts/s — 1M
   concepts ≈ 10 min on the natural profile.
2. **Annotations (NER) cost scales with note length** — ~230 ms for a
   sentence, ~2.2 s for a 200-word note, ~11.8 s for a 2,000-word note — but
   **the batched API is ~9× faster (39 notes/s on short notes, sustained to
   1k)**. Bulk annotation should batch and shard; 1M short notes ≈ 7 h
   batched-serial. It is an ingestion-time tool, not a corpus-wide sweep.
3. **The shipped in-process adapter is not the scored engine (finding, pre-v0.0.22).**
   `InProcessTerminologyEndpoint.search_text` calls
   `medterm4ds.services.discovery.search_names`, whose `NameSearchResult`
   carries no `score`/`match_grade` — the adapter's `getattr(..., 0.0/"ambiguous")`
   defaults fire, so every in-process result grades `ambiguous` at score 0.0 and
   the AutoCoder threshold (default `certain`) silently drops everything: 0/40
   coded in the smoke test. The scored engine the HTTP surface serves is
   `medterm4ds.services.search.search(mode=...)`. This benchmark drives the
   scored engine through a benchmark-only endpoint; the adapter fix (route to
   `services.search` and honor `mode`) belongs on the v0.0.22 fix branch.
4. **Two input-dependent crash classes exist in the NER dependency stack**
   (PyRuSH sentence splitter `UnboundLocalError` + one observed heap
   corruption; medspaCy ConText `TypeError`) — see Annotations ladder below.
   Both are medterm4ds dependencies; reported upstream.

## AutoCoding ladder (in-process semantic)

| rung | rows | wall | rows/s | engine calls | dedup hit | engine p50 | engine p95 | coded |
|---|---|---|---|---|---|---|---|---|
| natural 1k cold | 1,000 | 25.4 s | 39 | 194 | 80.6% | 102 ms | 126 ms | 980 |
| natural 1k warm-cache | 1,000 | 0.43 s | 2,302 | 0 | 100% | — | — | 980 |
| natural 10k cold | 10,000 | 51.8 s | 193 | 482 | 95.2% | 88 ms | 147 ms | 9,764 |
| natural 10k warm-cache | 10,000 | 5.5 s | 1,832 | 0 | 100% | — | — | 9,764 |
| natural 100k cold | 100,000 | 154 s | 648 | 946 | 99.1% | 109 ms | 129 ms | 97,723 |
| natural 100k warm-cache | 100,000 | 60 s | 1,673 | 0 | 100% | — | — | 97,723 |
| mixed 10k (50% pre-coded) | 10,000 | 41.7 s | 240 | 371 | 92.6% | 112 ms | 124 ms | 4,886 |
| **distinct 1k (worst case)** | 1,000 | 56.7 s | 17.6 | 999 | 0% | 51 ms | 64 ms | 956 |
| **distinct 10k (worst case)** | 10,000 | 569 s (9.5 min) | 17.6 | 9,987 | 0% | 51 ms | 62 ms | 9,539 |

Reading the ladder:

- **Real-world shape (natural rungs):** cost is bounded by *distinct* texts, not rows. 100k concepts took 154 s cold — 99% of rows never reach the engine (in-run dedup + the AutoCoder's DuckDB cache). Scaling is sub-linear: 10× rows added 3× wall.
- **Warm cache:** re-running a seen corpus runs at **~1,700–2,300 rows/s** with zero engine calls; even within one 100k pass, the cache cut 154 s → would-be ~250 s+ of row overhead.
- **Already-coded resources are free** (INV-4 skip): the 50%-pre-coded rung costs the same as its 5k uncoded half; skip overhead is unmeasurable.
- **Worst case (every concept distinct):** engine-bound at **~17.6 concepts/s (~57 ms/query)** — 10k in 9.5 min, linear. This is the honest per-contract price; real corpora sit far below it. The adversarial rung is *faster per query* (51 ms vs ~100 ms) because exact SNOMED names short-circuit ranking; Synthea's FSN-with-suffix texts exercise the fuller path.
- **Extrapolation (natural profile):** 1M concepts ≈ ~1,100 distinct × ~0.1 s engine work (~2 min) + row processing ~2k rows/s (~8 min) → **~10 min for a million concepts**. Memory flat ~4.2 GB throughout (model weights dominate).
- **Yield:** 95.6–98% of resources gained a coding at `min_match_grade=probable, top_k=1`.

### Duplicate profile

Synthea s100k yields 132,569 CodeableConcepts but only **1,087 distinct texts**
(Condition 266, Observation 225, Procedure 437, MedicationRequest 119,
Immunization 21, AllergyIntolerance 19). Real EHR exports show the same shape:
a few hundred phrases dominate. The adversarial all-distinct rungs below use
244,532 real SNOMED condition names from the lexical index as the worst case.

## Annotations ladder (in-process NER)

| rung | notes | words/note | ms/note | notes/s | concepts/note |
|---|---|---|---|---|---|
| sentence 100 | 100 | 18 | 321 | 3.1 | 6.5 |
| sentence 1,000 | 1,000 | 21 | 237 | 4.2 | 6.8 |
| sentence 10,000 | 10,000 | 16 | 227 | 4.4 | 6.6 |
| medium 100 | 100 | 203 | 2,218 | 0.45 | 37.6 |
| medium 300 | 300 | 204 | 2,192 | 0.46 | 37.2 |
| long 20 | 20 | 2,007 | 11,822 | 0.085 | 126.2 |
| long 50 | 50 | 2,007 | 12,002 | 0.083 | 120.0 |
| batched sentence 100 | 100 | 18 | 25.4 | 39.4 | — |
| batched sentence 1,000 | 1,000 | 18 | 25.5 | 39.3 | — |

Notes are synthesized from distinct rotations of Synthea condition/discovery
texts (no per-note cache flattery), full assertion flags
(`include_family/historical/uncertain=true`).

- **Per-note cost tracks note length**: ~230 ms for a one-liner, ~2.2 s for
  200 words, ~11.8 s for 2,000 words (~6 ms/word at the long end; fixed
  per-note overhead dominates short notes).
- **Batching is the scaling lever**: the batched API
  (`extract(list_of_texts)` → `_nlp.process_batch` + `canonical_batch` over
  deduped entity texts) ran 100 short notes at **25 ms/note vs ~230 ms
  single-note — ~9× throughput**. Bulk annotation should always batch.
- Serial throughput on short notes: 3.1 → 4.4 notes/s as volume grows (warm-up
  amortizes); **batched: 39 notes/s sustained to 1,000 notes**. 1M short notes
  ≈ 7 hours batched-serial — shard across cores or run at ingestion.
- **Crash finding 1 (PyRuSH/PyFastNER):** the sentence splitter aborted the
  benchmark on specific note content — `UnboundLocalError: this_char` in
  `WildCardFunctions.processWildCard_a` (rule engine walks past text end),
  once followed by native heap corruption ("corrupted double-linked list",
  SIGABRT). Input-dependent, process-killing when the heap goes.
- **Crash finding 2 (medspaCy ConText):** a second input-dependent crash class
  on long notes — `TypeError: 'ConTextModifier' object is not iterable` in
  `context_graph.apply_modifiers`. Also process-killing when uncaught.
  Both are medterm4ds dependencies, reported upstream; the benchmark harness
  runs annotation ladders with per-note exception guards from part 3 on.
- **The crashes are non-deterministic across identical replays** — the same
  seeded note list crashed one pass and ran clean the next — consistent with
  native memory corruption rather than purely deterministic input triggers.
  Bulk-annotation deployments need per-batch isolation (subprocess workers)
  until the upstream fixes land.

## Findings / caveats

- In-process adapter gap (above) — package fix queued for v0.0.22 branch.
- No batch API on the scored semantic search (`SearchService.semantic` is
  single-query; `canonical_batch` exists but is a different surface). Per-query
  embedding is the cost floor (~85–100 ms); batched embedding would amortize it.
- RSS: ~4.2 GB resident (SapBERT + FAISS + lexical indexes) regardless of
  corpus size — the memory story is flat, dominated by model weights.
- NER main-env breakage: thinc 8.2.5 binary-incompatible with numpy 2.2.6;
  benchmark ran under a numpy<2 venv. Worth pinning in docs or requirements.
- Synthea texts are SNOMED FSNs — near-canonical search inputs. Real messy EHR
  text (abbreviations, typos) will shift match grades down (fewer `certain`) but
  not the cost per query.
