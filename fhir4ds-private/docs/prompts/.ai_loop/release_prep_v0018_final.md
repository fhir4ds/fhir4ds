# RELEASE PREP — v0.0.18 (final loop pass)

## WASM example surface sync (this pass)

- **cql-clinic**: wheel 0.0.15 → 0.0.18; stale `cql.duckdb_extension.wasm`
  (`11b358b3`) → current (`5bc222aa` = cleanroom/wasm-demo binary).
- **viewing-room**: wheel 0.0.17 → 0.0.18.
- Both website snapshots (`web/website/static/{cql-clinic-app,
  viewing-room-app}`) redeployed from fresh builds.
- All five website apps + both standalone dev apps now ship the identical
  wheel `fhir4ds_v2-0.0.18-py3-none-any.whl` (md5 `cdcaacf2`).
- Runtime verification: cql-clinic lesson-1 boot → "engine ready", zero
  page errors (Pyodide + DuckDB-WASM on the new wheel). viewing-room e2e:
  11 passed; the 3 failures (gallery / s5-browse / web-component) were
  bisected against the restored 0.0.17 wheel and fail IDENTICALLY there —
  pre-existing, not regressions.

## Wheel rebuild + artifact parity

- `hatch build -t wheel` on the final tree is **byte-identical** to the
  shipped wheel (md5 `cdcaacf27809cf321552616e62404a9e`) — deterministic.
- Extensions: repo bundle = wheel = site-packages — fhirpath
  `05128412a68ac0b4f99c8af98f2dac93`, cql `bd8ec2890912b623faff4c24d8ceb4b7`.
  (The fhirpath binary updated in `755fdcba` is carried by the wheel.)

## Gates

- **Conformance: 2832/2832 (100%)** — ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47 (`/tmp/opencode/conformance-v18.log`, exit 0).
- **Clean-venv smoke:** fresh venv + wheel install → `pip check` clean,
  `fhir4ds.__version__ == '0.0.18'`, `register()` native both True on
  `allow_unsigned_extensions` connection, documented Python-fallback on
  plain connection, `fhirpath_text` UDF executes.
- **Notebooks:** 4/4 re-executed in-place against the wheel — 0 error
  outputs, diffs are execution-metadata (timestamps) only.
- **Website:** `tsc --noEmit` clean, `npm run build` success (with the
  updated releases.md).
- **Benchmarks:** `run_comparison.py --runs 5 --skip-cr` — **47/47
  measures at 100% accuracy** (235/235 measure-runs), median exec/patient
  4.70 ms vs 818.69 ms (174.3× vs clinical-reasoning); COMPARISON.md
  regenerated.

## Docs

- `releases.md` v0.0.18 section extended: WASM standalone parity bullets
  (patient_id cells, include closure, view spinner/diagnostics, atomic
  reset, cellify-on-arrival) + all-example-surfaces-on-0.0.18 note.
- Notebooks md / wasm-engine.md / homepage PRODUCT_VERSION already 0.0.18
  (verified, no drift).

## Code review

See `code_review_v0018.md`: CLEAN_WITH_NOTES (CR-001 LOW expectedReports
cosmetic asymmetry; CR-002 LOW committed dev-server node_modules;
CR-003 LOW pre-existing viewing-room e2e failures; CR-004/005 verified
clean).

## Verdict

**GO** — v0.0.18 artifacts consistent and gated. Remaining: commit the
surface-sync + docs churn, push, open the PR (squash-merge recommended).
