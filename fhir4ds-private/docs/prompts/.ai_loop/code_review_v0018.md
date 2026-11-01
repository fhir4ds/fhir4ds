# CODE REVIEW — v0.0.18 release delta (post-S32)

Scope: commits `4339c9f0..HEAD` (the S32 release → now): the WASM parity +
e2e reconciliation commit (`83774cb7`), the static deploy (`0b37a75a`), the
benchmark refresh pair, the origin/main merge (viewing-room S1–S6, notebooks
E2E fix), plus the current uncommitted WASM-example updates (cql-clinic
0.0.15→0.0.18, viewing-room 0.0.17→0.0.18, both website snapshots).

## Verification performed

- **Extension/wheel binary parity (release doctrine):** repo bundle =
  0.0.18 wheel = site-packages for BOTH extensions — fhirpath
  `05128412a68ac0b4f99c8af98f2dac93`, cql `bd8ec2890912b623faff4c24d8ceb4b7`.
  The fhirpath binary that moved in `755fdcba` (FP-10-F01 follow-up +
  Time-boundary parity rebuild) is already carried by the wheel — verified by
  extracting from `dist/fhir4ds_v2-0.0.18-py3-none-any.whl`.
- **WASM surface updates:** cql-clinic wheel 0.0.15→0.0.18 + stale
  `cql.duckdb_extension.wasm` (`11b358b` → current `5bc222aa`); viewing-room
  wheel 0.0.17→0.0.18. Both website snapshots redeployed from fresh builds.
  All five website apps now ship the same wheel (`cdcaacf2`).
- **Typecheck + unit:** cql-cleanroom `tsc --noEmit` clean; vitest 197/197.
- **WASM runtime smoke:** cql-clinic lesson 1 boots the 0.0.18 wheel through
  Pyodide + DuckDB-WASM → "engine ready", zero page errors. viewing-room
  e2e: 11 passed; 3 failures bisected to PRE-EXISTING (fail identically on
  the restored 0.0.17 wheel: journey-gallery sample render, journey-s5
  Browse grouping text, web-component boot) — NOT regressions of the update.
- **App-level review of `83774cb7`:** evalLibs closure (hover/run/evidence
  explain all ship the full include closure), standalone cell run
  `patient_id` prefixing (parity with connected run-all), atomic reset
  (explicit-value persist + postReset marker + View-1 reseed), cellify
  arrival-only guard (`userEditedTabsRef`/`applyingProgrammaticRef`),
  ViewOutput spinner/diagnostics split, `viewReportsPending={evaluating}`.

## Findings

- **CR-001 (LOW, note):** in the atomic reset, the in-memory state sets
  `expectedReports: { msr_0: [] }` while the persisted snapshot writes
  `expectedReports: {}`. Benign: `isPristineWorkspace` treats both as
  pristine, and the reload path is guarded by `postReset` — but aligning
  them would remove a future trap.
- **CR-002 (LOW, inherited):** `web/dev-server/node_modules` is committed
  (~5k files in the branch delta). Bloats the PR diff enormously; a
  `.gitignore` + lockfile-only convention would spare future reviews.
  Out of scope for this release.
- **CR-003 (LOW, note):** viewing-room's 3 pre-existing e2e failures
  (gallery/s5-browse/web-component) predate the wheel update and remain
  open; flagged for the viewing-room owner, not a release blocker for
  fhir4ds core.
- **CR-004 (verified clean):** `hoverEvalKey` now includes per-include
  `name:length` fingerprints — cache correctly invalidates when an INCLUDE
  changes (previously only main-lib text length keyed it). No stale-hover
  risk found.
- **CR-005 (verified clean):** `PW_WORKERS` default stays 1; the
  fixed-port devserver specs remain serialized via unique ports per spec.

## Verdict

CLEAN_WITH_NOTES — no release blockers. The delta is consistent with the
S32 review's invariants (Python conformance authority, allowlist discipline,
artifact parity doctrine), and the new WASM-example surfaces now match the
release wheel everywhere.
