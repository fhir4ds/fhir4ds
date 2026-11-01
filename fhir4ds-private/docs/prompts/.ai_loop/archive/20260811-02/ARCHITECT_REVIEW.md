# ARCHITECTURE SELF-AUDIT — SQL-on-FHIR v2 Spec Compliance + Analytics Layer FDD v1

> Designer-owned architecture self-audit per `ROLE_FEATURE_DESIGNER.md`
> Step 3, applying the standards of `ROLE_ARCHITECT.md`. Phase 1
> (Golden Standard) and Phase 2 (audit against the FDD v1 draft) only.
> Phases 3 (empirical validation) and 4 (issue logging/state pruning)
> belong to the post-implementation evolution loop.
>
> Prior cycle's architect review archived at
> `archive/ARCHITECT_REVIEW_batch_aug_2026-07-04.md` (unrelated feature).

Audited artifact: `FEATURE_PLAN_DRAFT.md` (this loop directory).
Audit date: 2026-08-11.
Source gap analysis: `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md`.

---

## Phase 1 — Golden Standard (Architectural Invariants)

The feature must preserve these 8 falsifiable invariants. Each is testable; each is grounded in either spec text, GLOBAL_RULES, or the project's documented design intent.

| # | Invariant | Falsifier | Source |
|---|---|---|---|
| **I-1** | The new `fhir4ds/sqlquery/` package may import from `fhir4ds/viewdef/`, but `fhir4ds/viewdef/` MUST NOT import from `fhir4ds/sqlquery/`. | `grep -rE "import\s+(fhir4ds\.)?sqlquery" fhir4ds/viewdef/` returns nothing. | Layering principle; one-way dependency. |
| **I-2** | No silent fallbacks in SQLQuery profile validation. Unsupported dialect, malformed `contentType`, missing `relatedArtifact.resource`, or `parameter` on SQLView MUST raise a typed `SQLError` subclass, never coerce. | Each error path has a unit test asserting the typed exception. | GLOBAL_RULES "No Silent Fallbacks". |
| **I-3** | SQLQuery parameter binding uses DuckDB prepared statements. User parameter values MUST NOT be substituted into SQL via string interpolation, f-string, or `format()`. | Grep `sqlquery/runner.py` for `.format(`, `f"`, `%s` SQL-string patterns; only present inside identifier quoting helpers (which validate against `sql-name` first). | SQL injection defense; spec says raw SQL body is author-controlled but parameters are caller-controlled. |
| **I-4** | The `_extensions` bag on `ViewDefinition` preserves unknown top-level keys verbatim. No validation, type coercion, key normalization, or canonicalization. | Roundtrip test feeds a ViewDefinition with arbitrary nested-complex `extension` array; JSON-level output contains identical bytes for the unknown keys. | §G-3 spec basis: DomainResource extension is intentionally open. |
| **I-5** | `cnl-1` strictness applies only to canonical URL fields (`ViewDefinition.url`, `profile[]`, `meta.profile[]`). `Column.type` MUST keep the permissive `_URI_RE = ^\S*$` because the spec allows relative URIs and element-ID references there. | Unit test asserts `Column(type='Observation.referenceRange')` and `Column(type='relative/path')` are accepted after the cnl-1 change. | Spec: ViewDefinition `column.type` short element definition. |
| **I-6** | `cnl-0` (`ViewDefinition.name` leading-capital + 255-char) and §G-4 (`column.tag.name` namespace) surface ONLY as warnings from `validate_view_definition()`. They MUST NOT raise from strict parser/generator paths. | Each rule has a paired test: `validate_view_definition(...)` returns a warning in the list; `parse_view_definition(...)` does not raise for the same input. | Spec severity: cnl-0 is warning; tag namespace is "recommended". |
| **I-7** | The `joins` extension (`Join`, `JoinType`, `JoinGenerator`, the `joins` field, the public exports) continues to function at runtime. Documentation changes are allowed. The serialization gate, if implemented, MUST default OFF. | Existing `Join` runtime tests stay green without modification. New tests assert `ViewDefinition.to_dict()` still emits `joins` by default. | §E-1: extension intentionally preserved. |
| **I-8** | The spec test suite refresh (§G-5) is a measurement change, not an implementation change. It MUST NOT modify `generator.py`, `parser.py`, or `types.py` as part of the refresh itself. Triage findings become separate typed issues with their own fix steps. | Diff between commit before and after §G-5 refresh shows only changes to `tests/spec_tests/*.json`, the report markdown, and the test header comment. | GLOBAL_RULES "spec tests are how fhir4ds detects drift" — drift detection must precede drift correction, not be tangled with it. |

---

## Phase 2 — Audit Against the FDD v1 Draft

### A. Layering (Invariant I-1)

**Draft §3.2** explicitly states the one-way dependency and names the single import point (`viewdef/generator.py`). ✓

**Skeptical Note S-1 (medium):** Draft Step 7d says *"Reuse the FHIR-type-to-SQL-type mapping already maintained by `fhir4ds/viewdef/generator.py` if accessible; otherwise add a small typed coercion table in `sqlquery/runner.py`."* The phrase "if accessible" is fuzzy. Either the mapping is importable (a clean public helper in `viewdef`) or it is not. If it is not, the design should commit to a small coercion table in `sqlquery/types.py` rather than hedge. Hedging creates an undocumented decision point that the engineer will resolve ad hoc.

**Suggested fix:** Reframe as — "The FHIR-type-to-SQL-type mapping is currently an internal detail of `viewdef/generator.py`. Step 7a will extract it to a public `viewdef` helper (e.g., `viewdef.types.fhir_type_to_duckdb(fhir_type: str) -> str`) that `sqlquery/runner.py` imports. This makes I-1 explicit and avoids duplicating the mapping."

### B. Silent Fallbacks (Invariant I-2)

Draft Steps 7b, 7d, 7f all commit to typed errors. ✓

**Skeptical Note S-2 (low):** Draft Step 7d content selection says *"prefer `application/sql;dialect=duckdb`; fall back to `application/sql`"*. The verb "fall back" sounds like a silent fallback. It is not — both content types are spec-accepted and the runner supports both — but the language reads as a recovery path. Reframe to "select the most specific supported content type" or "prefer X, then accept Y".

### C. Parameter Binding (Invariant I-3)

Draft Step 7d commits to prepared statements, no interpolation. ✓

**Skeptical Note S-3 (medium):** Identifier quoting is described as "via the existing viewdef quoting helpers" without naming them. The draft should cite the specific helper(s) — likely in `viewdef/utils.py` or `viewdef/generator.py`. Without the citation, the engineer may invent a new quoting path. Also, the design must explicitly say how `relatedArtifact.label` (which becomes a DuckDB view name) is quoted: identifier quoting via `"`-delimited DuckDB identifier, after `sql-name` regex validation.

**Suggested fix:** Name the helper. Add an explicit statement that `relatedArtifact.label` becomes a DuckDB identifier quoted as `"label"` after `sql-name` validation.

### D. Extension Bag (Invariant I-4)

Draft Step 4 commits to verbatim preservation, no validation. ✓

**Skeptical Note S-4 (medium):** The roundtrip test description says "byte-for-byte at the JSON level" but only samples flat string keys. DomainResource `extension` arrays in real FHIR resources carry complex nested objects (e.g., complex extensions with nested `extension[]` children). The test corpus must include at least one such nested-complex extension to truly falsify I-4.

**Suggested fix:** Add to Step 4 task 5: "Roundtrip corpus includes (a) flat string `publisher`, (b) `extension: [{"url": "...", "valueString": "..."}]`, (c) deeply-nested `extension: [{"url": "...", "extension": [{"url": "...", "valueBoolean": true}]}]`, (d) `meta.tag` array with system+code+display. Assert JSON-level key survival for all four."

### E. cnl-1 Scope (Invariant I-5)

Draft Step 2 explicitly preserves `_URI_RE` for `Column.type`. ✓

**Skeptical Note S-5 (low):** The list of canonical call sites (Step 2 task 3) cites line numbers (`types.py:1165-1166` etc.) from the gap analysis, which is correct as of 2026-08-11. By the time implementation lands, these line numbers will drift. The fix instructions should say "grep for `validate_optional_uri_string` callers" rather than rely on line numbers.

### F. Warning vs Error (Invariant I-6)

Draft Steps 3 and 5 explicitly say "Do NOT promote to error". ✓

No skeptical note. This is the cleanest part of the draft.

### G. joins Extension Preservation (Invariant I-7)

Draft §3.3, §6 constraint #4, and §7 out-of-scope all align. ✓

**Skeptical Note S-6 (low):** The optional serialization gate (Step 6 task 4) is described as gated on "are there downstream consumers that roundtrip through other tools". The draft surfaces this to the human at approval, which is correct. But the design should commit to a default behavior in the absence of an answer: default OFF (preserve current serialization). The draft says this in §7 out-of-scope, but Step 6 task 4 itself reads as a pending decision. Make the default explicit in both places.

### H. Spec Test as Measurement (Invariant I-8)

Draft Step 1 cleanly separates measurement from implementation. ✓

**Skeptical Note S-7 (HIGH):** Draft Step 1 exit criteria says *"no fewer than the pre-refresh 134 tests pass"* but does not specify what happens if MORE than 134 pass but new tests fail. The 12 new `repeat.json` tests are explicitly called out as "highest-risk". If, say, 6 of them fail and the failures are not fixed by §G-1..§G-4, the feature reaches its Definition of Done with known spec regressions. The draft currently has no decision rule for this case.

**Suggested fix:** Add a triage decision tree to Step 1:
- **PASS on first run**: Update report, done.
- **FAIL, root cause matches an existing §G-1..§G-4 scope**: Fold the fix into that step; bump its scope.
- **FAIL, root cause is new but small** (e.g., format/whitespace, off-by-one): File as a typed issue, fix in this feature.
- **FAIL, root cause is new and large** (e.g., a previously-unknown Process(S,N) algorithm edge case requiring generator rewrite): Pause. Surface to human via `WAIT_FOR_USER_APPROVAL`. Do NOT silently defer; do NOT bundle a multi-day fix into a "spec suite refresh" step.

This prevents the "stale measurement" failure mode from being replaced by a "stealth scope expansion" failure mode.

### I. Generalizability / Hardcoding

**Skeptical Note S-8 (medium):** Step 7d parameter binding uses "FHIR-type-to-SQL-type coercion". The draft is silent on whether this is a dict-driven registry (good) or a chain of `if param.type == 'string'` branches (anti-pattern per GLOBAL_RULES "Model Knowledge Must Be Data-Driven").

**Suggested fix:** Commit to a dict-driven `_FHIR_TYPE_TO_DUCKDB: dict[str, str]` registry in `sqlquery/types.py`. New types added by editing the dict, not by adding branches.

### J. Coupling

The SQLQuery runner takes a DuckDB connection as a parameter (caller-supplied), not a global. ✓ Good — keeps the runner testable and avoids singleton state.

### K. Performance Critical Paths

No performance concerns at this layer for §G-1..§G-4 (constant-time dict ops, regex matches).

For §M-1: each `relatedArtifact` becomes a `CREATE VIEW` on the caller's connection. View names persist for the connection's lifetime. If the caller runs many SQLQuery resources against the same connection, view names accumulate. Not a critical-path issue for MVP, but the design should note it: SQLQuery runner should `CREATE OR REPLACE VIEW` (idempotent) and document that callers may `DROP VIEW` if needed.

**Skeptical Note S-9 (low):** Add `CREATE OR REPLACE VIEW` semantics and a docstring note about view accumulation.

### L. Test-Driven Hacks

None identified. The draft does not special-case any test fixture.

### M. Spec Alignment

- §G-1: `^[^|# ]+$` matches the cnl-1 invariant regex. ✓
- §G-2: `^[A-Z]([A-Za-z0-9_]){1,254}$` matches cnl-0. ✓
- §G-3: Extension bag (option B) matches gap doc recommendation. ✓
- §G-4: Warning level matches spec "recommended" language. ✓
- §G-5: Suite migration matches the May 2026 upstream move. ✓
- §M-1: Profile shape matches `input/fsh/profiles/library-profiles.fsh` snippet in gap doc. ✓
- §M-2: Surfaced as scope decision, not silently decided. ✓
- §E-1: Extension preservation matches the gap doc's explicit "intentionally retained" stance. ✓

### N. Validation Strategy

- Spec suite (§G-5) gates the rest. ✓
- 1,061-test internal ViewDefinition suite is the non-regression gate. ✓
- Native vs. forced Python FHIRPath parity is in §5.6. ✓

**Skeptical Note S-10 (medium):** The draft does not specify a non-regression check for the existing fhir4ds-internal CQL pipeline (`pytest fhir4ds/cql/`). Although this feature does not directly touch CQL code, the SQLQuery runner introduces a new public package, and `pyproject.toml` may need updating to register it. The `[tool.hatch.build.targets.wheel] packages = ["fhir4ds"]` line already covers it (since `fhir4ds/sqlquery/` is a subpackage of `fhir4ds`). But the design should explicitly say "no pyproject.toml change is required because `sqlquery/` is a subpackage of the existing `fhir4ds` package, which is already in the wheel target list." Otherwise the engineer might assume a config change is needed.

### O. Likely Regression Points

The draft names five likely regression points and assigns mitigations. All five are sound:
1. New `repeat.json` failures → triage.
2. `_extensions` field breaking positional constructors → keyword-only default.
3. `validate_canonical_string` over-rejection → spec suite re-run.
4. Serialization gate accidentally on → default OFF.
5. DuckDB view name collisions → see Skeptical Note S-9 (`CREATE OR REPLACE`, document caller responsibility).

---

## Phase 2 Summary — Skeptical Notes by Severity

| ID | Severity | Subject | Required action |
|---|---|---|---|
| S-7 | HIGH | §G-5 triage decision tree missing | Add explicit decision rule for "new tests fail and root cause is large" case |
| S-1 | MEDIUM | "if accessible" hedge for FHIR-type mapping | Commit to extracting a clean public helper in `viewdef` |
| S-3 | MEDIUM | Unnamed identifier-quoting helper | Cite specific helper; specify `relatedArtifact.label` quoting |
| S-4 | MEDIUM | Roundtrip test corpus too thin | Add nested-complex extension fixtures |
| S-8 | MEDIUM | Coercion-table shape unstated | Commit to dict-driven registry |
| S-10 | MEDIUM | pyproject.toml impact unstated | Explicitly document that no config change is needed |
| S-2 | LOW | "fall back" wording | Reframe as "most specific supported" |
| S-5 | LOW | Line-number citations in Step 2 | Use grep-based instructions |
| S-6 | LOW | Default for serialization gate ambiguous between sections | State default OFF in both Step 6 and §7 |
| S-9 | LOW | View accumulation unstated | Use `CREATE OR REPLACE VIEW`, document caller cleanup |

No invariant violations found. The draft is structurally sound. The 10 skeptical notes are all refinements, not defects.

---

## Phase 3 — QA Enforcer Gate (Pre-Implementation)

This is a feature design, not a QA cycle. There is no prior QA phase to veto. The design itself specifies QA discipline for Step 1 (§G-5): "no silent skips, every test marked pass/fail/skip with a triage note". The Skeptical Note S-7 above extends this discipline to cover the "what if new tests fail" branch. **`RETRY_QA` is not applicable here.**

---

## Phase 4 — Recommended Fix Order for v2 Refinement

For the FEATURE_DESIGNER's v2 refinement pass (next step):

1. **(HIGH) S-7:** Add the triage decision tree to Step 1.
2. **(MEDIUM, cluster the boundary-precision notes):** S-1 + S-3 + S-8 — make the SQLQuery/viewdef boundary and identifier-quoting helper explicit.
3. **(MEDIUM) S-4:** Expand the §G-3 roundtrip corpus.
4. **(MEDIUM) S-10:** Add the pyproject.toml non-impact statement.
5. **(LOW) S-2, S-5, S-6, S-9:** Wording and minor precision fixes; bundle into a single cleanup pass.

After applying these, the FDD is ready for `WAIT_FOR_USER_APPROVAL`.
