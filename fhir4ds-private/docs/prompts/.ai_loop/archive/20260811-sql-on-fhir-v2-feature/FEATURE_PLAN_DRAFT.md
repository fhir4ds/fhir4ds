# FEATURE_PLAN_DRAFT v1 — SQL-on-FHIR v2 Spec Compliance + Analytics Layer

**Status:** DRAFT (pre self-audit)
**Author:** Feature Designer (autonomous, `.ai_loop`)
**Source:** `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md` (gap analysis, 2026-08-11)
**Spec target:** SQL-on-FHIR v2 **2.1.0-pre** (`https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/`)
**Package baseline:** fhir4ds 0.0.11 (`dev` branch)

---

## 0. SCOPE DECISION GATES (REQUIRE HUMAN APPROVAL BEFORE IMPLEMENTATION)

This design identifies **one decision that the Feature Designer cannot make autonomously**. It must be surfaced to the human at the APPROVAL gate. The default below is the Feature Designer's recommendation; the human may overturn it.

### Gate A — §M-2 FHIR operations: is fhir4ds a library or a server?

**Decision needed:** Should fhir4ds implement the four spec operations (`$viewdefinition-run`, `$viewdefinition-export`, `$sqlquery-run`, `$sqlquery-export`)?

**Default recommendation: LIBRARY-ONLY.**
- fhir4ds has no FHIR server today. The existing FastAPI surface at `fhir4ds/cql/fhir_server/app.py` serves the CQL pipeline, not ViewDefinition.
- The spec does not require every implementation to expose HTTP.
- Adding HTTP operations is a multi-quarter effort and would require its own feature scoping (async pattern, Content-Location polling, OutputFormatCodes negotiation, CapabilityStatement advertisement).
- The Analytics Layer value (§M-1 SQLQuery) is fully deliverable as a Python library without operations.

**If the human chooses server scope:** §M-2 is removed from this feature, filed as a separate future feature, and §M-1 design is unchanged (a server would simply wrap the library). This feature's pipeline stays the same.

**The rest of this design assumes LIBRARY-ONLY.** It does not depend on the human's answer for any other component.

---

## 1. OBJECTIVE

Bring the fhir4ds SQL-on-FHIR v2 ViewDefinition implementation to full conformance with the current 2.1.0-pre spec, measured against the **canonical** conformance suite at `FHIR/sql-on-fhir.js` (144 tests / 22 files, May 2026). Add the spec's Analytics Layer (SQLQuery and SQLView Library profiles) as a DuckDB-only MVP. Tighten four documented gaps in the ViewDefinition layer (§G-1 through §G-4). Harden the fhir4ds-specific `joins` extension (§E-1) as a clearly-documented extension, never removed.

**Definition of Done (this feature):**
1. `pytest fhir4ds/viewdef/tests/test_spec_compliance.py` reports a clean or triaged baseline against the 144-test canonical suite.
2. `pytest fhir4ds/viewdef/` (1,061 internal tests) remains green on every commit.
3. §G-1, §G-2, §G-3, §G-4 fixes land in `fhir4ds/viewdef/types.py` and `fhir4ds/viewdef/parser.py`.
4. New `fhir4ds/sqlquery/` package implements SQLQuery + SQLView Library profiles against DuckDB.
5. `joins` extension has documentation in three places (viewdef package docstring, `Join` dataclass docstring, `fhir4ds-private/docs/`).
6. `conformance/reports/final_compliance_report.md` reflects the new 144-test denominator and SQLQuery row.
7. Public docs (README, website ViewDefinition page) disclose the `joins` extension and the new SQLQuery module.
8. Release Engineer artifact gate passes on the final candidate.

---

## 2. SPEC ALIGNMENT

| Component | Spec basis (2.1.0-pre) | Source path |
|---|---|---|
| ViewDefinition invariants `cnl-0`, `cnl-1` | `https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html` (invariants tab) | IG |
| CanonicalResource / DomainResource inheritance | R5/R6 Foundation | IG + FHIR core |
| `column.tag.name` namespace recommendation | ViewDefinition `column.tag` short element definition | IG |
| SQLQuery profile | `https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery` | `input/fsh/profiles/library-profiles.fsh` |
| SQLView profile | `https://sql-on-fhir.org/StructureDefinition/SQLView` | same |
| `sql-must-be-sql-expressions` invariant | Library profile invariant | same |
| `content.contentType` dialect suffixes | `AllSQLContentTypeCodes` ValueSet | same |
| `relatedArtifact.label` semantics (table alias) | SQLQuery profile `relatedArtifact` slice | same |
| Conformance suite | `https://github.com/FHIR/sql-on-fhir.js/tree/main/tests` | upstream repo |

`joins` field on ViewDefinition is **NOT** in any spec version. Verified by spec-history audit: 1,104 commits searched across all branches of `HL7/sql-on-fhir`, no occurrence of `"joins"` in any spec source file.

---

## 3. ARCHITECTURE

### 3.1 Layering (unchanged for ViewDefinition layer)

```
                    ┌─────────────────────────────────────────┐
                    │   public API:  fhir4ds.viewdef           │
                    │   parse / validate / generate            │
                    └─────────────────────────────────────────┘
                          │              │              │
                  ┌───────▼───┐   ┌──────▼─────┐   ┌───▼──────────┐
                  │ types.py  │   │ parser.py  │   │ generator.py │
                  │ (model)   │   │ (JSON→AST) │   │ (AST→SQL)    │
                  └───────────┘   └────────────┘   └──────────────┘
                          │                              │
                  ┌───────▼───────────────────────────▼────────┐
                  │  fhir4ds.fhirpath (UDF surface, DuckDB)     │
                  └─────────────────────────────────────────────┘
```

The §G-1..§G-4 fixes touch only `types.py` (regex + new `_extensions` bag + warning hooks) and `parser.py` (`validate_view_definition()` warnings list). The generator is untouched. This is the minimum-blast-radius path.

### 3.2 New: `fhir4ds/sqlquery/` package (mirrors `viewdef/`)

```
fhir4ds/sqlquery/
├── __init__.py            # public API: parse_sqlquery, SQLQueryRunner, etc.
├── types.py               # SQLQuery, SQLView, SQLParameter, SQLContent dataclasses
├── parser.py              # FHIR Library JSON → dataclass (profile-conformant)
├── validator.py           # profile + invariant checks
├── runner.py              # materialize relatedArtifact as DuckDB views; bind params; execute
├── errors.py              # SQLError hierarchy
└── tests/
    ├── unit/
    ├── integration/
    └── spec_tests/        # spec examples from input/fsh/examples/sql-query-examples.fsh
```

**Critical boundary:** `fhir4ds/sqlquery/runner.py` **depends on** `fhir4ds/viewdef/generator.py` (to materialize a ViewDefinition into a `CREATE VIEW` statement). The dependency is one-way. `viewdef/` never imports `sqlquery/`.

### 3.3 Extension hardening (§E-1)

`Join`, `JoinType`, `JoinGenerator`, `joins` field, and the public `Join` / `JoinType` exports in `viewdef/__init__.py` **stay**. Changes are documentation-only at this layer, plus an optional gating hook in `ViewDefinition.to_dict()` (off by default).

### 3.4 Conformance measurement (§G-5)

The local snapshot at `fhir4ds/viewdef/tests/spec_tests/` is the measurement, not the implementation. Replacement is a `git`/`curl` pull from `FHIR/sql-on-fhir.js/tests/*.json` plus a re-run. The 22 filenames are stable; only file contents change. A periodic re-sync hook (CI or release checklist) prevents future silent drift.

The stale comment in `test_spec_compliance.py` line 5 (`https://github.com/FHIR/sql-on-fhir-v2/tree/master/tests`) must also be updated.

---

## 4. IMPLEMENTATION PLAN (sequenced)

Each step is independently committable. Steps are gated: a later step does not begin until the prior step's tests are green.

### Step 1 — §G-5 Spec suite refresh (BLOCKER; lands first)

**Why first:** Every other conformance claim in this feature is suspect until the measurement baseline is current. The 12 new `repeat.json` tests are the highest-risk surface.

**Tasks:**
1. Pull the 22 test files from `https://github.com/FHIR/sql-on-fhir.js/tree/main/tests` into `fhir4ds/viewdef/tests/spec_tests/`, replacing the existing snapshot.
2. Update the stale header comment in `test_spec_compliance.py` (currently references the old `sql-on-fhir-v2` URL).
3. Run `pytest fhir4ds/viewdef/tests/test_spec_compliance.py -v`. Capture the pass/fail/skip breakdown.
4. For each failure: triage against the per-file delta from the gap doc §G-5. Most likely failures cluster in `repeat.json` (recursive traversal + forEach + unionAll + constants + nested iteration).
5. File each triaged failure as a typed issue in `evolution.json.issues` (severity HIGH for spec regressions, MEDIUM for new unimplemented behavior, LOW for whitespace/formatting).
6. Once triage is complete (not necessarily fixed — fix work happens in §G-1..§G-4 or follow-on issues), update `conformance/reports/final_compliance_report.md` with the new 144-test denominator and current pass rate.
7. Add a release-checklist step (in `fhir4ds-private/docs/` or `.github/workflows/`) to re-pull from `FHIR/sql-on-fhir.js` before each release.

**Exit criteria:** Spec test count = 144 in the report; every test marked pass/fail/skip with a triage note; no fewer than the pre-refresh 134 tests pass.

**Estimated effort:** 0.5–1 day for the pull + run + triage. Fix work is gated on what the triage finds.

### Step 2 — §G-1 `cnl-1` URL invariant (error)

**Spec basis:** `cnl-1` on `ViewDefinition.url`: `exists() implies matches('^[^|# ]+$')`.

**Tasks:**
1. In `fhir4ds/viewdef/types.py`, add `_CANONICAL_RE = re.compile(r"^[^|# ]*$")` near the existing `_URI_RE` (line 249).
2. Add a `validate_canonical_string(value: str, field_name: str) -> None` helper that raises `ValidationError` when `_CANONICAL_RE` does not match.
3. Route the following through `validate_canonical_string`:
   - `ViewDefinition.url` validation (`types.py:1165-1166`)
   - Each entry of `ViewDefinition.profile` (`types.py:99-113`)
   - Each entry of `ViewDefinition.meta.profile` (`types.py:1160-1164`)
4. **Keep `_URI_RE` (`^\S*$`) for `Column.type`** — the spec allows relative URIs and element-ID references there. Do not over-tighten.
5. Add unit tests in `fhir4ds/viewdef/tests/unit/test_types.py`: reject `url` containing `|`, `#`, space; accept valid canonical; preserve `Column.type` permissiveness.

**Exit criteria:** New unit tests pass; existing `test_types.py` and `test_parser.py` suites green; spec suite from Step 1 not regressed.

**Estimated effort:** 0.5 day.

### Step 3 — §G-2 `cnl-0` name invariant (warning)

**Spec basis:** `cnl-0` warning on `ViewDefinition.name`: when present, must match `^[A-Z]([A-Za-z0-9_]){1,254}$`.

**Tasks:**
1. In `fhir4ds/viewdef/parser.py`, function `validate_view_definition()` (lines 587–695): the warnings list already exists. Add a warning when `vd.name` is present AND either:
   - `not vd.name[0].isupper()`, OR
   - `len(vd.name) > 255`.
2. **Do NOT promote to error.** `cnl-0` is warning severity in the spec. The existing `sql-name` error invariant (`^[A-Za-z][A-Za-z0-9_]*$`) stays at its current enforcement points.
3. Add unit tests asserting the warning fires for `name='myView'` (lowercase) and `name='A'*256` (too long); does not fire for `name='PatientDemographics'`.

**Exit criteria:** Unit tests pass; spec suite not regressed.

**Estimated effort:** 0.25 day.

### Step 4 — §G-3 CanonicalResource roundtrip via extension bag (option B)

**Spec basis:** ViewDefinition inherits from CanonicalResource / DomainResource / Resource. Beyond what the dataclass carries today, spec defines: `identifier`, `versionAlgorithm[x]`, `experimental`, `date`, `publisher`, `contact`, `useContext`, `jurisdiction`, `purpose`, `copyright`, `copyrightLabel`, `approvalDate`, `lastReviewDate`, `effectivePeriod`, `topic`, `author`, `editor`, `reviewer`, `endorser`, and DomainResource fields `language`, `text`, `contained`, `extension`, `modifierExtension`.

**Tasks:**
1. Add `_extensions: dict[str, Any] = field(default_factory=dict)` to the `ViewDefinition` dataclass (`types.py:911-1088`). Use a leading underscore to signal "private catch-all" — this is not an official FHIR field name.
2. Modify `ViewDefinition.from_dict` (parser path): for every unknown top-level key in the input dict, store it in `_extensions` verbatim (do not validate — the spec allows arbitrary DomainResource extension).
3. Modify `ViewDefinition.to_dict`: emit every key from `_extensions` after the known fields. Order does not matter for FHIR JSON.
4. **Do not implement option A** (full typed dataclass fields). Defer unless a downstream consumer needs typed access — gap doc explicitly recommends option B.
5. Unit tests: roundtrip a ViewDefinition JSON with `publisher`, `purpose`, `copyright`, and an arbitrary custom extension key; assert they all survive `from_dict → to_dict` byte-for-byte at the JSON level.

**Exit criteria:** Roundtrip tests pass; existing parser/serializer tests green (no regressions for known-field roundtrip).

**Estimated effort:** 0.5 day.

### Step 5 — §G-4 `column.tag.name` namespace warning

**Spec basis:** `column.tag.name` short element definition: "Namespace recommended (e.g. `ansi/type`)."

**Tasks:**
1. In `fhir4ds/viewdef/parser.py`, `validate_view_definition()`: add a warning when any `column.tag.name` is present and lacks a `/` separator.
2. **Do not promote to error.** Spec language is "recommended", not "shall".
3. Unit tests: warn for `name='type'`, do not warn for `name='ansi/type'`.

**Exit criteria:** Unit tests pass; spec suite not regressed.

**Estimated effort:** 0.25 day.

### Step 6 — §E-1 `joins` extension documentation (and optional gating)

**Tasks:**
1. Update `fhir4ds/viewdef/__init__.py` package docstring to disclose that `joins` / `Join` / `JoinType` are fhir4ds extensions, not part of SQL-on-FHIR v2. Reference the spec-history verification (1,104 commits searched; `"joins"` never appeared).
2. Update `Join` dataclass docstring in `fhir4ds/viewdef/types.py:872-908` with the same disclosure.
3. Add a section to `fhir4ds-private/docs/` (the architecture or extensions doc, location TBD by writer) documenting: (a) the extension exists, (b) it is non-portable, (c) authors who care about portability should use SQLQuery (§M-1) instead, (d) the canonical profile URL `https://fhir4ds.org/StructureDefinition/JoinExtension` is reserved.
4. **Optional, gated on human input at Step 5 approval:** if any downstream consumer roundtrips ViewDefinitions through other tools, also add a serialization gate in `ViewDefinition.to_dict()` — refuse to emit `joins` unless `meta.profile` contains `https://fhir4ds.org/StructureDefinition/JoinExtension`. Default OFF (preserve current behavior). The Feature Engineer asks the human at gate time if there are such consumers; if "no" or "unknown", leave the gate off.

**Exit criteria:** Documentation in three places; docstring unit tests (smoke) pass; no behavior change unless the optional gate is enabled.

**Estimated effort:** 0.5 day base; +0.25 day if the optional gate is added.

### Step 7 — §M-1 SQLQuery Library profile (DuckDB-only MVP)

**Spec basis:** `https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery` and `SQLView` profiles on FHIR `Library`.

This is the largest single component (gap doc estimates 1–2 weeks). Break into sub-steps:

#### 7a. `fhir4ds/sqlquery/types.py` — dataclasses

Define: `SQLQuery`, `SQLView`, `SQLParameter`, `SQLContent`, `SQLRelatedArtifact`. Mirror the profile shape from §M-1 of the gap doc. Both `SQLQuery` and `SQLView` share structure; only difference is `parameter 0..0` on `SQLView`.

#### 7b. `fhir4ds/sqlquery/parser.py` — FHIR Library JSON → dataclass

Profile-conformant parser. Enforce:
- `meta.profile` contains the SQLQuery or SQLView canonical
- `type.coding` = `LibraryTypesCodes#sql-query`
- `content 1..*` with each entry's `contentType` matching `application/sql*` (the `sql-must-be-sql-expressions` invariant)
- `relatedArtifact` with `type=#depends-on`, non-empty `resource` canonical, and `label` satisfying `sql-name`
- `parameter` forbidden on SQLView; on SQLQuery, each has `name`, `type`, `use=#in`

Reject malformed input with typed `SQLError`s.

#### 7c. `fhir4ds/sqlquery/validator.py` — profile invariants

Centralize the `sql-must-be-sql-expressions` check and the SQLView `parameter 0..0` check here.

#### 7d. `fhir4ds/sqlquery/runner.py` — DuckDB execution

The runner:
1. **Materialize dependencies.** For each `relatedArtifact` with a ViewDefinition canonical, resolve to a `ViewDefinition` object (from an in-memory registry or by parsing FHIR JSON), call `SQLGenerator().generate(vd)`, and emit `CREATE VIEW "<label>" AS <generated SQL>` against the DuckDB connection. For SQLView dependencies, recurse (with cycle detection — a `set` of visited canonicals).
2. **Pick content.** Among the `content[]` entries, prefer `application/sql;dialect=duckdb`; fall back to `application/sql`; reject everything else with a typed error.
3. **Bind parameters.** Decode `content[].data` (base64 → SQL string). Use DuckDB prepared statements. Coerce each parameter value from its FHIR type to the corresponding DuckDB type — no string interpolation. Reuse the FHIR-type-to-SQL-type mapping already maintained by `fhir4ds/viewdef/generator.py` if accessible; otherwise add a small typed coercion table in `sqlquery/runner.py`.
4. **Execute and return rows** as Python tuples / Arrow tables (caller's choice).

**Cycle detection:** Maintain a `set[str]` of canonicals currently being materialized. If a recursive descent revisits one, raise `SQLQueryCycleError`.

**SQL injection analysis:** The only user-controlled strings that reach DuckDB are (a) the base64-decoded SQL body, and (b) parameter values. (a) is intentional — the SQLQuery profile is literally "raw SQL the author wrote", so injection-by-author is not a threat model. (b) goes through prepared statements, which is the standard defense. Identifiers (view labels, parameter names) are validated against `sql-name` and double-quoted as DuckDB identifiers via the existing `viewdef` quoting helpers.

#### 7e. `fhir4ds/sqlquery/__init__.py` — public API

Export: `parse_sqlquery`, `parse_sqlview`, `SQLQueryRunner`, `SQLQuery`, `SQLView`, `SQLParameter`, error hierarchy. Do NOT export internal parser/validator hooks.

#### 7f. Tests

- Unit tests for parser/validator (every shape variant).
- Integration tests: a SQLQuery depending on one ViewDefinition, executed against a small in-memory DuckDB fixture; assert rows.
- Integration test: a SQLQuery depending on a SQLView depending on a ViewDefinition (recursive materialization).
- Integration test: cycle detection (A depends on B depends on A).
- Integration test: parameter binding with each supported FHIR type.
- Integration test: dialect rejection (`application/sql;dialect=postgres` raises).

**Exit criteria:** All sub-step tests pass; full `pytest fhir4ds/` green; documented examples from `input/fsh/examples/sql-query-examples.fsh` round-trip and execute.

**Estimated effort:** 1.5 weeks of focused engineer time.

### Step 8 — Documentation + conformance report update

**Tasks:**
1. Update `conformance/reports/final_compliance_report.md`:
   - §1 table: ViewDefinition row denominator → 144; add new row for SQLQuery (suites: spec examples executed).
   - Note in §2 the new fixes (§G-1 through §G-4) and the SQLQuery addition.
2. Update `README.md` and any website page touching ViewDefinition compliance to reflect 144-test count and SQLQuery module.
3. Update `fhir4ds/viewdef/__init__.py` package docstring (already touched in Step 6).
4. Add `fhir4ds/sqlquery/__init__.py` package docstring introducing the Analytics Layer.
5. Confirm `fhir4ds-private/docs/` discloses the `joins` extension (Step 6).

**Exit criteria:** All doc surfaces updated; conformance report totals internally consistent.

**Estimated effort:** 0.5 day.

### Step 9 — Release Engineer artifact gate

After implementation is complete, hand to Release Engineer to validate the final candidate artifact. The Feature Engineer does NOT run this gate during implementation — only on the final candidate.

**Tasks owned by Release Engineer (next pipeline step):**
- Build candidate wheel.
- Verify wheel contents include new `fhir4ds/sqlquery/` package.
- Verify public API surface (`viewdef` exports unchanged except for newly-added items; `sqlquery` exports as designed).
- Verify the bundled native DuckDB extension (if any) still loads.
- Smoke-install in a clean venv; import `fhir4ds`; run a tiny end-to-end ViewDefinition + SQLQuery example.

**Exit criteria:** Release Engineer signs off in `release_readiness_report.md` (note: this pipeline does NOT include a `pre_release` step — the gate is informal, run by the human or as a code-review-time check).

---

## 5. TEST STRATEGY

### 5.1 Spec compliance (§G-5)

- Canonical suite: 144 tests, 22 files, auto-discovered by `test_spec_compliance.py`.
- Pre-refresh pass rate: 134/134 (stale denominator). Post-refresh target: every test marked pass/fail/skip with a triage note. No silent skips.
- Highest-risk area: `repeat.json` (12 new tests covering recursive traversal + `forEach` + `unionAll` + constants + nested iteration).

### 5.2 Non-regression on internal ViewDefinition suite

- 1,061 tests under `fhir4ds/viewdef/`. Every commit must keep this green. This is a hard constraint, not a target.

### 5.3 Unit tests for §G-1..§G-4 fixes

- Each fix ships with unit tests in `fhir4ds/viewdef/tests/unit/` covering the spec-cited shape and at least one negative case.
- Each fix also asserts that the permissive `validate_view_definition()` API (the one that returns warnings instead of raising) stays permissive for the cases the spec marks as warning severity.

### 5.4 SQLQuery MVP tests

- See Step 7f above. Coverage spans parser, validator, runner, integration scenarios, cycle detection, parameter binding, dialect rejection.

### 5.5 Roundtrip tests for §G-3

- Roundtrip JSON with arbitrary extension keys → assert byte-for-byte survival at the JSON level (key order may differ, content must not).

### 5.6 Native vs. Python-fallback FHIRPath parity

- The new SQLQuery runner indirectly depends on `viewdef/generator.py`, which already pairs native C++ and forced Python FHIRPath fallback paths. Add at least one parity probe for a SQLQuery execution under both registrations.

---

## 6. NON-REGRESSION CONSTRAINTS (HARD)

1. `pytest fhir4ds/viewdef/` stays at 1,061/1,061 green on every commit.
2. `pytest fhir4ds/` overall stays green.
3. Public API surface of `fhir4ds.viewdef` does not lose any existing export (`Join`, `JoinType`, `Column`, `Select`, `Constant`, `ViewDefinition`, `ColumnType`, `parse_view_definition`, `validate_view_definition`, `SQLGenerator`, all 5 error types).
4. The `joins` extension continues to function at runtime; only documentation changes are guaranteed at this layer.
5. No new dependencies added to `pyproject.toml` for the ViewDefinition layer fixes. SQLQuery MVP also adds no new dependency (DuckDB is already required).

---

## 7. OUT OF SCOPE

1. **§M-2 FHIR operations** — gated on Gate A above. Default: library-only.
2. **Full CanonicalResource typed dataclass (option A for §G-3)** — deferred unless a consumer needs typed access. Extension bag (option B) is the implementation.
3. **Multi-dialect SQLQuery content support** beyond `application/sql` and `application/sql;dialect=duckdb`. Authors targeting other dialects get a typed "unsupported dialect" error.
4. **AST-level schema validation** of column references inside SQLQuery SQL bodies. The spec does not require runners to validate this; skipping is not a compliance gap.
5. **Serialization gate for `joins`** (`ViewDefinition.to_dict()` refusing to emit `joins` without an extension profile declaration) — optional, default off, gated on human input at approval.
6. **CQL server or FastAPI changes.** The existing `fhir4ds/cql/fhir_server/` is untouched by this feature.
7. **§M-1 SQLView-only-as-table optimizations** (e.g., inlining a SQLView dependency into its dependent's SQL body). The MVP materializes every dependency as a real DuckDB view.

---

## 8. ESTIMATED SCHEDULE

| Step | Effort | Cumulative |
|---|---|---|
| 1. §G-5 spec suite refresh + triage | 0.5–1 day (longer if triage finds real bugs) | 1 day |
| 2. §G-1 cnl-1 | 0.5 day | 1.5 days |
| 3. §G-2 cnl-0 warning | 0.25 day | 1.75 days |
| 4. §G-3 extension bag | 0.5 day | 2.25 days |
| 5. §G-4 tag namespace warning | 0.25 day | 2.5 days |
| 6. §E-1 joins documentation | 0.5–0.75 day | 3.25 days |
| 7. §M-1 SQLQuery MVP | 1.5 weeks | ~11 days |
| 8. Docs + conformance report | 0.5 day | ~11.5 days |
| 9. Release gate | (handled by next pipeline step / human) | — |

Total: ~12 working days for a single engineer. Steps 1–6 are quick wins (under 4 days combined) and produce immediate conformance value; Step 7 is the long pole.

---

## 9. OPEN QUESTIONS (for the human at APPROVAL gate)

1. **Gate A:** Library-only (default) or server scope for §M-2?
2. **§E-1 optional gate:** Are there downstream consumers that roundtrip ViewDefinitions through other SQL-on-FHIR v2 runners? If "no" or "unknown", leave the serialization gate off.
3. **Version target:** This feature ships meaningful new public API surface (`fhir4ds/sqlquery/`). Is the target version `0.0.12` (patch) or `0.1.0` (minor bump)? The state file currently records `0.0.11` as a placeholder.
4. **Spec-suite sync cadence:** Should the periodic re-sync from `FHIR/sql-on-fhir.js` be a CI job (runs on every PR) or a release-checklist step (runs before each release)? CI is stricter; release checklist is cheaper.
