# web/cql-clinic — AGENTS.md

Browser CQL teaching sandbox: each lesson ships a template/solution CQL pair,
FHIR fixtures and expected results. Every lesson page mounts its own Pyodide
(translation) + DuckDB-WASM (execution) pair, loads the lesson fixtures into a
`resources` table, and auto-runs the edited CQL 1.2 s after typing stops.

## Commands

```bash
npm install
npm run build                       # tsc -b && vite build
npx playwright test                 # e2e on :5177 (builds + previews its own tree)
PYTHONPATH=~/src/fhir4ds python3 scripts/verify_lessons.py   # regenerate expected.json
```

## Testing doctrine

- `playwright.config.ts` uses port **5177**, `reuseExistingServer: false`, and
  `npm run build && npm run preview`. The cleanroom learned this the hard way:
  a stale preview squatting on a shared port (5176) silently serves weeks-old
  code, so a green run can judge a build that is not the tree under test.
- `scripts/verify_lessons.py` is the non-browser gate: it translates each
  lesson solution with the native extension and rewrites `expected.json`, so
  translator changes that alter lesson output show up as a fixture diff.
  Keep it in step with any worker post-processing change
  (`removeListExtractFhirpathWrappers` is ported there verbatim).

## ValueSet cache (FHIR4-49)

Lesson queries are live-editable, so a learner can add `valueset "X": '<url>'`
and `[Condition: "X"]` at any time. The engine answers ValueSet membership from
the in-process C++ `g_valueset_cache` — **not** from the `resources` table — and
an unseeded url makes `in_valueset` return SQL NULL, so the lesson silently
reads as "no rows" and every check fails for the wrong reason.

- `src/hooks/useDuckDB.ts::loadFixtures` re-seeds the cache on every lesson load
  from that bundle's `ValueSet` resources (via `web/shared/valuesetBridge.ts`,
  the single implementation shared with the cleanroom and wasm-demo) and returns
  the seeded urls. Re-seeding per lesson is deliberate: it also clears whatever
  a previous lesson left behind.
- `LessonPage` diffs the ValueSet urls in the translated SQL against the seeded
  urls and renders `[data-testid="valueset-cache-warning"]` plus a console
  warning. Silence is the bug — never let an unseeded valueset present as "no
  data".
- No lesson currently ships a `ValueSet` resource, so the seeding path is a
  no-op today; the warning is what protects learners.
- `tests/e2e/valueset-cache.spec.ts` pins both directions (a plain lesson stays
  quiet; an edited lesson with an unloaded ValueSet banners).

## Asset invariants (same as wasm-demo)

- Exactly one `fhir4ds_v2-*.whl` in `public/`, refreshed from
  `python3 -m hatch build -t wheel` on release.
- `public/extensions/{fhirpath,cql}.duckdb_extension.wasm` must track the
  current WASM extension builds; the wheel + extensions are what Pyodide and
  DuckDB-WASM actually load.
