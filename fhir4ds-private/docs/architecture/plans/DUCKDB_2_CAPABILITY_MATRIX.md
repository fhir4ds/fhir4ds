# DuckDB 1.5.5 / 2.0.0 Capability Matrix & Roadmap Tiers

*Status: DISCUSSION (Joel-approved; no engine changes). Date: 2026-10-31.
Author: playground session per cbus-20261031083216. Branch:
`docs/duckdb2-capability-matrix` off `origin/dev` (80fef086).*

*Purpose: map DuckDB 1.5.5 vs 2.0.0 features onto the fhir4ds roadmap and
decide where dual-support ends and 2.0-only enhancement begins. Evidence
sources are cited per claim; all fhir4ds-specific numbers come from our own
probes (file paths given).*

Tier definitions used throughout:
- **core-both** — must work identically on both lines; gated by the dual
  conformance gate.
- **enhanced-2.0** — works on both, materially better on 2.0; we optimize
  opportunistically when feature-detected.
- **2.0-only** — not available on 1.5.5; hidden behind feature detection,
  never on the default path.

---

## 1. Feature matrix

| # | Feature | 1.5.5 | 2.0.0 | fhir4ds relevance | Proposed tier |
|---|---------|-------|-------|--------------------|---------------|
| 1 | Async I/O (Parquet/CSV/native reads; s3:// throughput) | — | yes ([announce], async-io post) | `FileSystemSource` reads over s3/https; measure datasets shipped as Parquet are on the roadmap | **enhanced-2.0** (probe once our s3 legs exist) |
| 2 | VARIANT storage (shredded, columnar; Parquet round-trip; `variant_*` functions) | type exists, minimal integration ([1.5 announce]) | full: shredding, shredded Parquet read/write, `variant_extract[_string]`, `variant_keys/type/exists/...` ([announce]; verified live 2026-10-31, §2) | potential future storage layer for the `resources` table — the biggest open design question, §2 | **2.0-only** (as a storage MODE; JSON mode unchanged) |
| 3 | Python appender (`con.appender`) | — | yes ([gems]) | `FHIRDataLoader.load_resources` currently Arrow-batches into a temp table + `INSERT SELECT` (fhir_loader.py:596-655); appender is an alternative row-wise path — but see §3: our bottleneck is NOT insert throughput | **enhanced-2.0** (marginal; low priority) |
| 4 | Quack protocol + `CONNECT` (client-server) | partial (1.5.3+) | polished ([announce]) | Joel ruling: NO query-service work today | **2.0-only, future** (documented only) |
| 5 | NEAREST joins | — | yes ([announce]) | vector/embedding workloads (terminology fuzzy match? doc embeddings?) — nothing current | **2.0-only, future** |
| 6 | Self-hosted extension repositories | — | yes ([announce]; syntax WIP) | we already self-host via wheel-bundled binaries + `_staged_load_path`; a repo would replace the hatch distribution only for CLI users | **2.0-only, optional later** |
| 7 | PEG parser + extension grammar hooks | opt-in in 1.5, default in 2.0 ([announce]) | default | our generated SQL is parser-compatible (dual-run proven, FINDINGS-2 §a); grammar hooks could let CQL syntax be parsed IN DuckDB someday — speculative | **core-both** today; hooks **2.0-only, speculative** |
| 8 | Window-function extensions (C++ API) | — | yes ([gems]) | none of our UDFs are windowed | not planned |
| 9 | Secure views (`CREATE SECURE VIEW`) | — | yes ([gems]) | DQM measure views hide `resource` blobs? niche hardening | **2.0-only, optional** |
| 10 | Data-modifying CTEs | — | yes ([announce]) | loader could dedup-delete+insert in one statement — already solved via Arrow semi-join | not planned |
| 11 | Triggers | — | yes ([announce]) | incremental materialized measure caches (future) | **2.0-only, future** |
| 12 | `$variable` shorthand / session-var prepared defaults | getvariable() | yes ([gems]) | nicer generated SQL for parameters | **enhanced-2.0** (cosmetic) |
| 13 | Storage-format BREAK: files created by 2.0 are unreadable by <2.0 | — | yes ([announce] migration section) | we are in-memory/Arrow-first; `.duckdb` files are NOT a product surface (FINDINGS §2.4) — but persisted-catalog users of fhir4ds connectors would hit this | **core-both** (document the constraint; no action) |
| 14 | Lambda `->` removal (removal in 2.1) | ok | deprecated; `SET lambda_syntax` shim until 2.1 ([announce]; FINDINGS-2 diff 1) | 38 SQL-literal lambda-arrow sites in emitted SQL — dual-run today via the SET shim | **core-both**; migrate the 38 sites to `lambda x:` before 2.1 |
| 15 | ICU removal (tz/collation in core) | ICU-backed | native, faster ([announce]) | our tz/case handling is in OUR UDFs (FINDINGS §2.4) — unaffected | **core-both** |
| 16 | Aggregate Reuse Optimizer / delim-CTE default / planner changes | — | yes ([announce] PR list; FINDINGS §2.2) | already absorbed: dual-support shipped and gated; CMS68/CMS130 exec is dramatically FASTER on 2.0 (retest; rerun matrix) | **core-both** |
| 17 | Planner/optimizer scaling on wide SQL (duckdb#28181) | flat | super-linear on CMS2-class twin subqueries (~30-40 s plan tax; issue filed 2026-10-30) | CMS2-class measures on 2.0; the reason 2.0 stays opt-in ([RCA]) | **core-both** (gate: upstream fix or translator dedup) |

Sources: [announce] https://duckdb.org/2026/10/21/announcing-duckdb-200.html ·
[gems] https://duckdb.org/2026/10/26/gems-of-duckdb-200.html ·
[1.5 announce] https://duckdb.org/2026/03/09/announcing-duckdb-150.html ·
[RCA] `fhir4ds-private/docs/architecture/plans/PERF_RCA_DUCKDB2_CMS2_PLANTIME.md`
(perf/phase2-opt @6b70358) · FINDINGS/FINDINGS-2
(`/mnt/d/fhir4ds/.temp/duckdb2-upgrade/`, 2026-10-28/29) · retest
(`/mnt/d/scaling-data/wt-retest/benchmarks/scaling/RETEST.md` + erratum) ·
corrected 4-leg matrix (`/mnt/d/scaling-data/rerun-results/`, recorded in the
RCA doc) · live probes 2026-10-31 (below).

---

## 2. THE VARIANT QUESTION — what VARIANT storage means for the translator

**Current pipeline (verified in code):** `FHIRDataLoader` creates
`resources(id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref
VARCHAR)` (fhir_loader.py:275-281). The translator's retrieve CTEs read
`FROM resources r WHERE r.resourceType = '<T>'` (cte_builder.py:283), and
ALL FHIRPath access lowers to our UDFs with signature
`(VARCHAR, VARCHAR) -> VARCHAR` — e.g. `fhirpath_text(r.resource,
'name.given')` — with a DuckDB implicit JSON→VARCHAR cast on the first
argument (verified: fhirpath_extension.cpp:2165-2203 registers all five
UDFs VARCHAR-typed; the Python fallback likewise). `_rt_<Type>` shared base
CTEs (Phase 1/2) project `resource` through unchanged, so the UDF boundary
is the single seam where storage representation meets the evaluator.

**What a VARIANT layer changes:** ingestion shreds each resource into a
VARIANT value (struct-of-columns internally); Parquet layouts become
shredded-VARIANT columns; readers get `variant_extract_string(v, path)` and
friends instead of `json_extract_string(text, '$.path')`.

**Live probe results (duckdb 2.0.0, 2026-10-31, this session):**

| Probe | Result |
|---|---|
| `'{"a":1}'::JSON::VARIANT` stores as OBJECT variant; `variant_type/keys` correct | works |
| `variant_extract_string(v, 'valueQuantity.value')` — native dotted path | works |
| `variant_exists`, `variant_array_length`, `to_json(v)`, `v::JSON` round-trip | works |
| Parquet round-trip keeps VARIANT type (shredded read/write) | works |
| **`v->>'$.x'` / `json_extract(v, '$.x')` directly on a stored OBJECT variant** | **FAILS — "Malformed JSON" — the shredded re-serialization emits non-JSON text (`{'k': v}`) into the JSON path evaluator. Upstream-quality bug; workaround `to_json(v)` first, or use `variant_extract*` only** |
| Micro-bench 50k rows, status filter: JSON-text `json_extract_string` vs VARIANT `variant_extract_string` | ~2x faster on VARIANT (0.010s → 0.005s); an earlier 200k-row run showed ~4x (0.04s → 0.01s) |

**Blast-radius analysis, seam by seam:**

1. **Retrieve CTE emission + `_rt_` bases** — LOW. The SQL shape
   (`FROM resources`, `WHERE resourceType=`, MATERIALIZED bases) is
   representation-agnostic; only the `resource` column's declared type and
   the projection list change. One emission flag suffices.
2. **Expression lowering / FHIRPath accessors** — MEDIUM-HIGH, but
   mitigated. Every `fhirpath_*(resource, expr)` call site (thousands in
   generated SQL, but ONE lowering helper family in the translator) would
   become either (a) `fhirpath_*(to_json(v), expr)` — zero evaluator
   change, pays one re-serialization per call (probe suggests this is
   still fast, but it partially defeats shredding), or (b) a new
   VARIANT-native UDF overload `fhirpath_*(VARIANT, VARCHAR)` registered
   only on 2.0 whose C++ reads the shredded value directly — the better
   end-state, touching ~15 registration sites + the bind/eval entrypoints,
   NOT the evaluator core.
3. **UDF signatures** — see (2): additive overloads; the
   `(VARCHAR, VARCHAR)` signatures remain for JSON mode and 1.5.
4. **Type handling** (`json_typeof` → `variant_type`, etc.) — MEDIUM. Our
   generated SQL uses `json_*` functions in CQL list macros
   (`from_json`, `json_each` in macros/list.py) over values that ORIGINATE
   from `fhirpath_json(...)` output (VARCHAR/JSON), not from the storage
   column — so those are untouched. Only code that inspects the raw
   `resource` column changes.
5. **Loader/ingestion** — MEDIUM: new table DDL, `resource::VARIANT` cast
   at insert, dedup semi-join unchanged, `resolve()` macro's
   json-extraction predicates need VARIANT-aware variants.
6. **wasm/browser** — BLOCKED entirely: duckdb-wasm has no 2.0 line
   (FINDINGS C3), so VARIANT mode cannot reach the browser until wasm 2.0
   exists.

**Verdict: it is a storage-layer swap behind the SAME SQL shape, provided
we take path (2a) first (`to_json(v)` at the UDM boundary) and treat
(2b) VARIANT-native UDF overloads as a follow-up optimization. NOT a
translator fork.** The one structural risk is the shredded-object JSON-path
bug above: until fixed upstream, `json_*` functions must never see a raw
OBJECT variant, which we can enforce centrally in the lowering helper.

**Dual-support proposal:** a `storage_mode` option
(`"json"` default | `"variant"`). VARIANT mode requires duckdb>=2.0 and
feature-detects at connect; the translator receives
`resource_projection = "to_json(resource)"` (phase 1) so every emission
site stays single-shaped; JSON mode is byte-identical to today and remains
the 1.5/browser path. Parquet export layouts become mode-dependent —
documented, not silent.

**Why bother?** Probe-level 2-4x on scalar extraction filters, shredded
compression on disk, and shredded Parquet round-trips. But honest
counterpoint: our Phase-1/2 work already removed scan amplification
(42x→9x; 40.1→15.9 GB peak RSS @5k) and execution is no longer
extract-bound for CMS68/CMS130. VARIANT's real payoff would be for
AD-HOC path queries over `resources` (analyst-facing SQL, SQLView layer)
rather than the measure pipeline. Recommendation: prototype after the
#28181 planner fix lands, driven by the SQLView/analytics surface, not
the CQL translator.

---

## 3. THE APPENDER QUESTION — ingestion on 2.0

**Current ingestion paths (verified in code):**
- `FHIRDataLoader.load_resources` (fhir_loader.py:456-655): row-build +
  dedup in Python, then **Arrow register + `INSERT SELECT`** bulk path
  (temp Arrow tables; `executemany` only as ImportError fallback). This is
  already the fast path the DuckDB docs recommend over the appender for
  prepared data ([gems]: "For data that already lives in a DataFrame or
  Arrow table, `INSERT INTO ... SELECT` is still faster").
- `load_valuesets` (same file): same Arrow pattern.
- Benchmark harness loads (`run_measures.py`) call `load_resources` in
  50-bundle chunks; rung5000 data_load_s measured **924s (1.5.5) / 680s
  (2.0.0)** (retest results JSONs) and 1245s in our rerun (drvfs noise).

**Where does that time actually go?** The Arrow insert is NOT the
bottleneck: 6.27M rows insert in seconds. The wall time is (a) Python
`json.load` of 5,002 bundle files, (b) `_serialize_resource` per resource
(orjson dumps), (c) patient-ref extraction per resource, (d) Arrow table
construction per 50-bundle chunk. The appender replaces none of these —
it targets row-wise insert throughput, which we already beat with Arrow
([gems] explicitly).

**Specification (if we still want it):** feature-detect
`tuple(duckdb.__version__.split(".")) >= (2,0,0)` and `hasattr(con,
"appender")` → append rows via `with con.appender(table) as a:
a.append_rows(batch)` in the `executemany` fallback branch ONLY (where it
is a strict win — the fallback currently pays one prepared execute per
row). The Arrow path stays unconditional. Estimated load-time win:
**near-zero for the benchmark corpus** (Arrow path already active);
meaningful only for pyarrow-less environments (a niche we do not ship).

**Recommendation: implement the appender as the executemany-fallback
replacement only (a ~10-line change, low risk), and spend the real
ingestion win elsewhere** — e.g. parallel bundle-file parsing across
threads (the parse is GIL-released inside orjson/json C loops for most of
the time) or a larger chunk size. Flag the 5k load minutes as the actual
target if load time matters for the product.

---

## 4. Quack / CONNECT — out of scope (Joel ruling)

Documented here only as a **2.0-only, future** tier item: a fhir4ds
"measure server" (Quack serve + CONNECT from any DuckDB client) is
architectically attractive (no Python service layer) and blocked on
nothing technical — it is simply not today's work. Security posture would
need the reverse-proxy pattern ([announce] Quack section) before any
public deployment. No design work done here.

---

## 5. Recommendations & sequencing

**Tier assignments (summary of §1):**
- core-both: everything we ship today + lambda migration (14) + storage
  break documentation (13) + planner watch (17).
- enhanced-2.0: async I/O for s3 sources (1) once FileSystemSource s3 legs
  are benchmarked; `$variable` sugar (12); appender-fallback (3, tiny).
- 2.0-only: VARIANT storage mode (2) — prototype-gated; Quack (4),
  NEAREST (5), triggers (11), secure views (9), extension repos (6),
  parser hooks (7-hooks) — future/optional.

**Gates:**
- **duckdb-wasm 2.0** gates ANY browser-facing item (VARIANT mode included
  — the browser apps must keep working on JSON mode regardless, which the
  feature-flag design preserves).
- **duckdb#28181** gates planner-sensitive adoption (VARIANT prototypes
  change SQL shapes and would re-trigger plan-time measurement; also the
  CMS2-on-2.0 UX in general).
- **November 2.0.x patch release** ([announce] migration section) is the
  sensible moment to revisit 2.0-default and #28181 status.
- **2.1 lambda removal** is a hard deadline for the 38-site migration
  (already dual-compatible; pure mechanical work, FINDINGS-2 §a).

**Suggested sequencing:**
1. NOW (mechanical, zero-risk): migrate 38 lambda-arrow sites to
   `lambda x:` (works on both lines) — kills the SET shim dependency.
2. NOW (tiny): appender in the executemany fallback path.
3. NEXT RELEASE CYCLE: async-I/O benchmark on real s3 corpus once
   FileSystemSource s3 parity tests exist; adopt `enhanced-2.0` label in
   docs if the win is real.
4. AFTER #28181 RESOLVES (or Nov patch shows it fixed): VARIANT storage
   prototype for the SQLView/analytics surface (2a shape first), then
   evaluate VARIANT-native UDF overloads (2b).
5. STANDING: 2.0 stays opt-in (`[duckdb2]` extra; pyproject rationale
   corrected at perf/phase2-opt fb886306); revisit default-2.0 at the
   Nov patch + wasm-2.0 milestones with the 4-leg matrix re-run as the
   acceptance gate.

---

## Appendix: probe repro (2026-10-31, duckdb 2.0.0 venv)

Session transcript probes; minimal repro of the shredded-object JSON-path
bug (candidate upstream issue #2):

```sql
CREATE TABLE o (v VARIANT);
INSERT INTO o VALUES ('{"resourceType":"Observation","valueQuantity":{"value":120}}'::JSON::VARIANT);
SELECT variant_type(v), variant_keys(v) FROM o;          -- OBJECT, works
SELECT variant_extract_string(v, 'valueQuantity.value') FROM o;  -- works
SELECT v->>'$.resourceType' FROM o;                       -- Invalid Input: Malformed JSON
SELECT json_extract_string(to_json(v), '$.resourceType') FROM o;  -- works (workaround)
```
