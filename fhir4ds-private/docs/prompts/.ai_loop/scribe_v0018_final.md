# SCRIBE — v0.0.18 final release loop (2026-10-27)

## Pipeline executed (this pass)

1. **WASM examples sync** — cql-clinic 0.0.15→0.0.18 (+stale cql ext wasm
   refreshed), viewing-room 0.0.17→0.0.18, both website snapshots
   redeployed. All 7 wheel locations now identical (md5 `cdcaacf2`).
2. **Testing** — clinic lesson boot: "engine ready", 0 errors; viewing-room
   e2e 11 pass / 3 pre-existing (bisected vs 0.0.17); cleanroom tsc + vitest
   197/197.
3. **Code review** — `code_review_v0018.md`: CLEAN_WITH_NOTES.
4. **Release prep** — wheel rebuild byte-identical; extension md5 parity
   repo = wheel = site-packages; clean-venv smoke; conformance 2832/2832.
5. **Docs audit** — releases.md v0.0.18 section extended; notebooks 4/4
   re-executed (metadata-only diffs); website tsc + build clean; no
   version drift found anywhere.
6. **Benchmarks** — 47/47 at 100% accuracy (5 runs), 174.3× vs
   clinical-reasoning; COMPARISON.md regenerated.
7. **Scribe** — this report.

## Commits (this loop, on `feat/cleanroom-redo-20261014`)

- `83774cb7` fix(cleanroom): WASM parity for evaluation/evidence + e2e
  reconciliation
- `0b37a75a` chore(cleanroom): deploy the WASM parity build to the static
  targets
- `b7093c56` chore(release): sync all WASM examples to 0.0.18 + final
  release pass

Branch is 3 commits ahead of origin (plus previously-pushed release commits).
Tree clean; reports in this directory (`code_review_v0018.md`,
`release_prep_v0018_final.md`).

## Open items (carried, non-blocking)

- viewing-room: 3 pre-existing e2e failures (gallery/s5-browse/
  web-component) — predate this release; owner follow-up.
- CR-001 LOW: expectedReports `{msr_0: []}` vs `{}` cosmetic asymmetry in
  the atomic reset.
- CR-002 LOW: `web/dev-server/node_modules` committed (5k files in PR diff).

## Next

Push branch + open the v0.0.18 PR (squash-merge recommended per
release_prep_s32.md). Awaiting Joel's go.
