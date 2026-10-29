# FEATURE: DuckDB 2.0 Dual-Support (D1 + D2)

Date: 2026-10-29 · Branch: `feat/duckdb2-dual-support` (off `origin/main` @ `d24e9fc4`)
Per: Joel's NEXT SLOT GO via cbus (cbus-20261029001700) · Evidence:
`/mnt/d/fhir4ds/.temp/duckdb2-upgrade/FINDINGS-2.md` (+ FINDINGS.md, probe JSONs).

## 0. Locked rulings (requirements — from the dispatch)

1. **D1** = mechanical rewrite of every emitted-SQL lambda-arrow site to
   `lambda x:` syntax. NO translator flag, NO `SET lambda_syntax` shim in
   shipped code (the SET stays documented in FINDINGS-2 as emergency
   fallback only). Single translator, one syntax, valid on both versions.
2. **D2** = BOTH packaging pieces:
   (a) an opt-in extra that moves duckdb+extension together atomically
       (default = duckdb 1.x + ext-1; `pip install fhir4ds-v2[duckdb2]`
       marker-guarded `python_version >= "3.11"` → duckdb 2.x + ext-2);
   (b) BOTH extensions bundled in the wheel + RUNTIME SELECTION via
       `duckdb.__version__` at the existing `register()` version-detection
       seam (mismatch backstop: clean loud error, never a mysterious
       load failure).

## 1. Ground truth from the investigation (what we build on)

- **Only ONE real SQL break**: 2.0 removed arrow-lambda syntax
  (`Binder Error: Deprecated lambda arrow (->) detected`); `lambda x:`
  is accepted by BOTH 1.5.5 and 2.0 (proven live, incl. multi-param
  `lambda x, y:` for `list_reduce` and nested lambdas).
- Every other probed surface (unnest chains incl. row order, json_each
  joins, DECIMAL matrix, division semantics, legacy lateral forms) is
  byte-identical across versions; `json_each` fullkey quoting,
  non-integral DECIMAL params, `decimal_average` — zero exposure.
- Extension ABI is the ONLY hard fork: 1.5-built extensions will not
  load in 2.0 and vice versa (version-locked binaries) — hence dual
  bundles + runtime selection.
- 2.0 Python client needs **pytz** for TIMESTAMPTZ rendering
  (InvalidInputException without it) — dependency scoping required.
- duckdb 2.0 wheels are **cp311+**; our floor stays >=3.10 → the extra
  is marker-guarded `python_version >= "3.11"`.

## 2. D1 — lambda migration (mechanical)

### 2.1 Site census (verified this session, AST-based)

Two classes of emitters:

**A. SQL-literal sites (static strings)** — 31 occurrences across:
- `fhir4ds/cql/duckdb/macros/list.py` (13: `_v`, `i`, `x` params)
- `fhir4ds/cql/duckdb/macros/aggregate.py` (9: `_v`)
- `fhir4ds/viewdef/generator.py` (7: `_v`, `_t`, `_j`)
- `fhir4ds/cql/duckdb/macros/audit.py` (1: `_ev`)
- `fhir4ds/cql/translator/ast_helpers.py` (1: `_ev` struct_pack)

**B. Dynamic emitters (the keystone)** — `fhir4ds/cql/translator/types.py`:
- `SQLLambda.to_sql()` renders `{param} -> {body}`  (types.py:953)
- `SQLLambda2.to_sql()` renders `({p1}, {p2}) -> {body}` (types.py:973)
Every runtime-built lambda (list ops in `_functions.py`, `_query.py`,
`retrieve_optimizer.py`, `placeholder.py`, `inference.py`,
`fluent_functions.py`, `cte_manager.py`, `ast_utils.py` — ~54
SQLLambda construction sites) funnels through these TWO `to_sql()s`:
rewriting the two renderers to `lambda {param}: {body}` and
`lambda {p1}, {p2}: {body}` migrates the whole dynamic class at once.

**C. Argon-found companions (all in D1 scope)**:
- `CREATE MACRO IF NOT EXISTS` sites (aggregate.py AllTrue/AnyTrue/
  AllFalse/AnyFalse; list.py First/Last/CQLListMode + any sibling) →
  **`CREATE OR REPLACE MACRO`**: IF-NOT-EXISTS never overwrites a
  persisted arrow-macro in an on-disk `.duckdb` catalog (persistence
  verified live), so a pre-2.0 database file would keep raising the
  deprecated-arrow error after upgrade.
- `ast_utils.replace_qualified_alias` handles `SQLLambda` but NOT
  `SQLLambda2` (falls through unchanged) — add the branch (correctness
  predates this feature, but we touch the file family).
- `web/cql-cleanroom/src/lib/cql-macros.ts` mirrors macro BODIES and
  carries ~13 arrow sites — migrate in lockstep (test_macro_sync diffs
  NAMES only, so it will NOT catch body drift — Argon correction of
  our §2.3 assumption; the re-baseline note in §2.3 stands for the
  name-level check only).
- `test_evol_it25_domain9_skeptic.py` + `test_measure_capabilities.py`
  doc examples: mechanical updates.

**D. Test/doc pins**: only 1 test file embeds arrow-lambda SQL (a
comment context). The probe corpus under `.temp/duckdb2-upgrade/` is
investigation material, not shipped code.

### 2.2 Rewrite rule

| Old (1.5-only) | New (both) |
|---|---|
| `_v -> _v IS NOT NULL` | `lambda _v: _v IS NOT NULL` |
| `i -> CQLJsonEqElem(...)` | `lambda i: CQLJsonEqElem(...)` |
| `(x, y) -> x + y` | `lambda x, y: x + y` |

No spacing/paren changes beyond the arrow→`lambda …:` form; bodies
untouched. One syntax everywhere; no flag; no SET.

### 2.3 Migration + gating strategy

1. Rewrite class B (the two `to_sql()`s) — single choke point for all
   dynamic emissions.
2. Rewrite class A sites file-by-file (pure string edits).
3. **Dual-probe harness gates it**: the investigation's probe suite
   (`dual_probe.py`, `lambda_matrix.py`, `order_stress.py`,
   `decimal_matrix.py`, `div_matrix.py`) is promoted into
   `fhir4ds/tests/test_duckdb2_dual_support.py` (skippable on non-1.5/2.0
   versions) asserting, per version present: the migrated macros'
   outputs and the raw lambda acceptance matrix. On 1.5.5 it must show
   ZERO output drift pre/post (before/after diff of the full probe set
   + conformance macro surface). The py3.11/2.0 CI leg exercises the
   2.0 side (Python-fallback trees + probe suite).
4. Full gates on 1.5.5: conformance 2870/2870, viewdef pytest,
   `test_macro_sync.py` pins (macro bodies changed → the
   `duckdb_functions().macro_definition` snapshot comparisons must be
   re-baselined in the same commit).

### 2.4 Blast-radius notes

- The scaling campaign's benchmarks run through
  `viewdef/generator.py` + the CQL macros this touches; output is
  SEMANTICALLY identical SQL (only lambda spelling), so plans are
  unaffected, but any of THEIR text-pinned SQL snapshots would churn —
  coordinate merge timing per the dispatch (their legs are minutes;
  re-runs acceptable, avoid mid-measurement merges).
- `wasm_runtime_helpers`/browser surface: TS macros
  (`cql-macros.ts`) mirror Python macro BODIES — the arrow sites there
  must be migrated in lockstep or `test_macro_sync.py` fails (correctly).

## 3. D2 — packaging + runtime selection

### 3.1 Wheel layout (build-once-per-major, both bundled)

```
fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension        (1.5 build, existing name)
fhir4ds/cql/duckdb/extensions/cql.duckdb_extension                  (1.5 build, existing name)
fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb2_extension       (2.0 build, NEW)
fhir4ds/cql/duckdb/extensions/cql.duckdb2_extension                 (2.0 build, NEW)
```

`hatch_build.py` gains the two extra entries (env overrides
`DUCKDB_FHIRPATH_EXT2` / `DUCKDB_CQL_EXT2`; discovery per
`extensions/*/build/release_v2` or equivalent build dir). **Argon
[HIGH]**: `_discover_versions` sorts `v*` newest-first — once a v2.0.0
build exists in `repository/`, the ext-1 slot would grab it. The ext-2
entries must carry their OWN discovery filter (v2.* only) and the
ext-1 entries theirs (v1.* only), never the shared newest-first scan. **Size cost:
~+22 MB wheel** (current wheel 12.0 MB = both ext-1 (~11.2 MB each
compressed less dedup) — measured exactly at build time and recorded in
the release notes; 0.0.19 wheel is 12,037,134 bytes with two bundled
extensions, so the 2.0 twins roughly double the binary payload →
~34 MB. Accepted per Joel's ruling (b); the number is quantified in the
PR, not silently absorbed.)

Naming uses a distinct `.duckdb2_extension` suffix so a 1.5-only
environment can never LOAD the 2.0 binary by accident and vice versa;
discovery stays deterministic.

### 3.2 Runtime selection at the register() seam

Both `fhir4ds/fhirpath/duckdb/extension.py::_try_load_bundled_extension`
and `fhir4ds/cql/duckdb/extension.py` currently hard-gate on
`startswith("1.5.")`. New logic (same seam):

```
mm = re.match(r"^(\d+)\.(\d+)", duckdb.__version__)  # handles 2.0.0, 2.0.0-dev123, 1.5.5.post1
(mm1, mm2) = (int(mm.group(1)), int(mm.group(2))) if mm else (0, 0)
(1, 5)  → load <name>.duckdb_extension       (1.5 build)
(2, 0)  → load <name>.duckdb2_extension      (2.0 build)
other   → skip with existing INFO fallback-to-Python log  — NEVER LOAD an
          ABI-mismatched binary (Argon: extensions lock to major.MINOR;
          a future 1.6/2.1 must not try either bundle)
```
(Argon review: major-only dispatch would attempt the 1.5 binary under a
future 1.6/2.1 — the table is keyed on the built (major, minor) pair.)
binary MISSING for the running (major, minor) → WARNING with the full
   actionable sentence (the Argon-corrected UX: raising would break
   editable/sdist installs, the transition window, and our own §4.2
   Python-fallback verification on 2.0 — the existing no-binary path
   already falls back to Python UDFs silently). The loud RuntimeError
   happens ONLY when strictness is requested: register(con,
   require_cpp=True) or env FHIR4DS_REQUIRE_CPP=1 (wheel installs that
   NEED the native engine get the clean sentence, never a mid-LOAD
   ABI error; source installs keep working).
LOAD fails (unsigned/signature/ABI) → existing per-error handling
   (warn + Python-UDF fallback) unchanged.
```

`fhir4ds.register(con)` (the public seam) is unchanged in signature;
its return dict already reports `fhirpath_cpp`/`cql_cpp` flags, which
now reflect the selected major's binaries.

### 3.3 Dependency moves — FINAL RULING (Joel, 2026-10-29)

**Option A-refined.** The dispatch's original extra-flips-pin shape is
pip-impossible (empirically probed, Argon-confirmed — see review record),
but a wide base + NARROWING extras works (pip intersects; validated live
with pip 26.x dry-runs):

```toml
dependencies = [
    "duckdb>=1.5.5,<3",                       # widens ONLY with the ext-2 bundle (atomicity)
    "pytz; python_version >= '3.11'",         # duckdb 2.x client needs it; cp311+ only
]
[project.optional-dependencies]
duckdb1 = ["duckdb>=1.5.5,<2"]                # narrowing: intersect → 1.x
duckdb2 = ["duckdb>=2.0.0,<2.1"]              # narrowing: intersect → 2.0.x
```

- Base-only install on py3.11+: resolver picks newest allowed (2.x) —
  and that WORKS because the wheel bundles BOTH binaries and register()
  routes by the running version.
- `[duckdb1]`/`[duckdb2]` give conservative adopters a one-command pin.
- Mismatch UX: warn + Python-UDF fallback by default; strict opt-in via
  `FHIR4DS_REQUIRE_CPP=1`; error wording states SUPPORTED RANGE vs
  DETECTED version.
- Loader stays the authority; the runtime selector routes by the
  built-for (major, minor).

**HARD CONSTRAINT (atomicity)**: the `<2` → `<3` widening and the
dual-extension bundle ship in the SAME release; if ext-2 bundles slip
past the release cut, the pin stays `<2` for that release (one-line
diff, widens next release carrying them). Guarded by
`test_pin_widening_atomicity` in `fhir4ds/tests/test_duckdb2_dual_support.py`
(fails the build on pin-allows-2x-without-bundles).

Implementation sequencing on this branch: everything except the one-line
pin widening lands now; the widening diff is prepared but stays `<2`
until ext-2 builds exist.

### 3.4 What does NOT change

- `requires-python = ">=3.10"` (floor unchanged).
- duckdb-wasm / browser apps (stay 1.33.1-dev64 / 1.5-locked; wasm
  extension twins are separate artifacts untouched by the wheel).
- The C++ SOURCE trees: this feature ships a SECOND BUILD LINE, not a
  source migration — the 2.0 binaries are built from the same sources
  with the submodule pinned to v2.0.0 (port effort already assessed:
  signature-level, ~15 registration sites — FINDINGS-2 §b). Until those
  builds exist, `hatch_build.py` treats the 2.0 binaries as OPTIONAL:
  a wheel without them still builds and works on 1.x; the runtime
  selection raises the loud error only when a 2.x duckdb meets a
  wheel that lacks the 2.0 bundle (correct failure mode during the
  transition window).

## 4. Verification plan

1. **Pre/post drift gate (1.5.5)**: capture the full dual-probe corpus
   + `duckdb_functions().macro_definition` digest + conformance master
   BEFORE the rewrite; re-run after; diff must be lambda-spelling-only
   (macro bodies' `->` → `lambda …:`) with zero row/output drift.
2. **2.0 leg (py3.11 venv)**: the preserved
   `/mnt/d/scaling-data/duckdb2-venv` pattern — install the branch's
   wheel with `[duckdb2]`, run the promoted probe suite + Python-
   fallback pytest trees (fhirpath/cql unit trees that don't need the
   native extension).
3. **Full gates on 1.5.5**: conformance 2870/2870 (ViewDef 144 /
   FHIRPath 935 / CQL 1706 / DQM 47 / OMOP 38), viewdef pytest,
   macro-sync pins re-baselined, `fhir4ds/tests/test_version.py`,
   clean-venv install matrix: default extra-less install (1.x pin
   wins) and `[duckdb2]` on py3.10 (no-op) + py3.11 (2.x).
4. **Runtime-selection UX probe**: wheel with only ext-1 + duckdb 2.x
   → the loud RuntimeError sentence; wheel with both + 1.x → ext-1
   loads, 2.x binary untouched; both + 2.x → ext-2 loads.

## 5. Explicitly out of scope

Making 2.0 the default; duckdb-wasm/browser migration; CPython 3.10
drop; the C++ source port itself (separate build-line work — this
feature packages its OUTPUT); loosening the `duckdb==1.5.5` pin in the
dev environment (dev env stays 1.5.5; the 2.0 leg is venv-isolated).

## 6. Review record

- **Joel ruling (2026-10-29)**: Option A-refined (wide base + narrowing
  extras + marker-scoped pytz in base + atomicity constraint) — supersedes
  the Option-B interim decision; §3.3 rewritten to the ruling.
- **Second opinion (Gemini 4 Argon, repo-grounded, 2026-10-29)** —
  all five answers integrated:
  - A AGREE: pip conclusion correct/complete (PEP 508 intersections,
    no 621/735/723 flip mechanism; only meta-package pattern works and
    breaks bare installs). Also caught a stale §3.3 remnant claiming
    extra-overrides — removed.
  - B DISAGREE-with-A: ship Option B (base `<2`) until ext-2 binaries
    actually ship; A's wide base would make 2.x the de-facto default
    and break fresh installs during the transition. INTEGRATED as the
    Option-B-now decision; widen-to-`<3` gated on real ext-2 bundles.
  - C DISAGREE-with-major-only: dispatch on (major, MINOR) —
    extensions are ABI-locked to major.minor; future 1.6/2.1 must fall
    back, never LOAD. INTEGRATED in §3.2.
  - D AGREE + 3 companions: IF-NOT-EXISTS→OR REPLACE (persisted
    catalogs keep arrow macros), ast_utils SQLLambda2 gap, TS macro
    lockstep (macro-sync diffs names only). INTEGRATED in §2.1C.
  - E DISAGREE-with-raise: warn+Python-fallback default (raise breaks
    editable installs + our own 2.0 verification); strict opt-in via
    require_cpp flag/env. INTEGRATED in §3.2.
  - Risks adopted: [HIGH] hatch `_discover_versions` newest-first
    collision once v2.0.0 builds exist (filter per-major per-target —
    §3.1 note added); [HIGH] persisted-catalog macros; [MEDIUM]
    consolidate the fhirpath/cql unsigned-extension handling into one
    shared loader while touching both seams; [LOW] defensive parens on
    SQLLambda body at nonzero parent_precedence.
