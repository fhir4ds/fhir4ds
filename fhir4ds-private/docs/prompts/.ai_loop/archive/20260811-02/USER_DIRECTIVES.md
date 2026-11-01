# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal

Bring the fhir4ds SQL-on-FHIR v2 ViewDefinition implementation to full conformance with the current 2.1.0-pre spec, and add the spec's Analytics Layer components (SQLQuery Library profile). Treat every gap identified in `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md` as in-scope for a single feature, sequenced so that conformance-measurement infrastructure (§G-5) lands before any implementation that depends on its claims.

The fhir4ds-specific `joins` extension (§E-1) is intentionally preserved. It is documented as an extension, not removed.

## Pipeline

1. feature_design
2. feature_implementation
3. code_review

## Feature Plan

**Source document:** `fhir4ds-private/docs/plans/SQL_ON_FHIR_V2_GAP_ANALYSIS.md`

This is a gap analysis, **not** a feature design. The `feature_design` step must consume it and produce `FEATURE_SQL_ON_FHIR_V2_SPEC_COMPLIANCE.md` at `fhir4ds-private/docs/architecture/plans/`. Do **not** skip `feature_design` — the gap analysis identifies what to do, not how to architect it. Several gaps (§M-2 in particular) are scope-decision items that the Feature Designer must surface to the human via the standard APPROVAL gate before implementation begins.

## Specific Bug Fix

None. This is a feature, not a targeted remediation. The `bug_fix` workflow is not in the pipeline.

## Focus Areas

### Sequencing (must-follow)

- **§G-5 lands first, before any other implementation.** Pull the current spec test suite from `FHIR/sql-on-fhir.js/tests/` into `fhir4ds/viewdef/tests/spec_tests/`. Run the suite. Triage failures. Update the conformance report totals. The 12 new `repeat.json` tests are the highest-risk surface — recursive-traversal coverage combined with `forEach`, `unionAll`, constants, and nested iteration. Without re-running the canonical suite, every other conformance claim in this feature is suspect.
- Only after §G-5 produces a clean (or triaged) baseline may §G-1 through §G-4 land.
- §M-1 (SQLQuery) is gated on the §M-2 scope decision.

### ViewDefinition layer compliance gaps (§G-1 through §G-4)

- **§G-1 `cnl-1` URL invariant** — tighten the canonical/URL validators in `fhir4ds/viewdef/types.py`. Add a dedicated `_CANONICAL_RE = re.compile(r"^[^|# ]*$")`; route `ViewDefinition.url`, `ViewDefinition.profile`, and `ViewDefinition.meta.profile` through it. Keep the more permissive `_URI_RE` for `Column.type` (which spec-accepts relative URIs and element-ID references).
- **§G-2 `cnl-0` name invariant** — surface as a non-fatal warning from `validate_view_definition()` when `ViewDefinition.name` is present and either starts with a non-capital letter or exceeds 255 characters. Do not promote to error (cnl-0 is warning severity).
- **§G-3 CanonicalResource / DomainResource field roundtrip** — use the extension-bag approach: add an `_extensions: dict[str, Any]` catch-all to the `ViewDefinition` dataclass that preserves unknown keys verbatim through `from_dict` / `to_dict`. This is the minimum-cost path to roundtrip safety. Defer the full-dataclass approach (option A in the gap doc) unless a downstream consumer needs typed access.
- **§G-4 Tag namespace recommendation** — non-fatal warning from `validate_view_definition()` when any `column.tag.name` lacks a `/` namespace prefix. Spec language is "recommended," not "shall."

### Conformance measurement (§G-5)

- Source: `https://github.com/FHIR/sql-on-fhir.js` at `tests/` (22 JSON files, 144 tests).
- Replace the contents of `fhir4ds/viewdef/tests/spec_tests/` (currently 134 tests, 9 of 22 files stale).
- Run `pytest fhir4ds/viewdef/tests/test_spec_compliance.py` and triage.
- Add a CI job or release checklist step to re-sync from `FHIR/sql-on-fhir.js` periodically. The snapshot must not silently drift again.
- Update `conformance/reports/final_compliance_report.md` with the new totals once stable.

### Major components

- **§M-1 SQLQuery Library profile** — DuckDB-only MVP scope. New `fhir4ds/sqlquery/` package mirroring `viewdef/` (types, parser, validator, runner). Materialize each `relatedArtifact` dependency as a DuckDB view (`CREATE VIEW "<label>" AS <generated SQL>`) so the raw SQL in `content[].data` resolves table aliases correctly. Bind parameters via DuckDB prepared statements with FHIR-type-to-SQL-type coercion — no string interpolation. Pick `application/sql` or `application/sql;dialect=duckdb` content; reject other dialects. Skip AST-level schema validation of column references (spec does not require it). Implement `SQLView` profile alongside `SQLQuery` since they share structure (only difference: `parameter 0..0` on SQLView). Estimated 1–2 weeks.
- **§M-2 FHIR operations** — `$viewdefinition-run`, `$viewdefinition-export`, `$sqlquery-run`, `$sqlquery-export`. **This is a scope-decision item.** The Feature Designer must surface this as a question for human approval during the design phase. Default recommendation: library-only (fhir4ds does not expose HTTP). If the human chooses server scope, this becomes a multi-quarter effort and should be split into its own feature; do not bundle into this feature's implementation.

### Extension hardening (§E-1)

- The `joins` field on `ViewDefinition`, the `Join` dataclass, `JoinType` enum, the `JoinGenerator` module, and the public API exports remain in place.
- Add clear documentation in the `viewdef` package docstring, the `Join` dataclass docstring, and `fhir4ds-private/docs/` that `joins` is a fhir4ds extension and not part of any past or current version of SQL-on-FHIR v2. Reference the spec-history verification in §E-1 of the gap analysis (1,104 commits searched; `"joins"` never appeared in any spec source file).
- Optional second step (gated on whether any downstream consumer roundtrips ViewDefinitions through other tools): refuse to emit `joins` in `ViewDefinition.to_dict()` unless `meta.profile` declares a fhir4ds-specific extension profile canonical (e.g., `https://fhir4ds.org/StructureDefinition/JoinExtension`).

### Cross-cutting

- **Release Engineer artifact gate required.** This feature touches public API surface (`Join` exports may move; new `fhir4ds/sqlquery/` package added; `Column`, `ColumnTag`, `Constant`, `Select`, `ViewDefinition` dataclasses may gain fields). The final candidate artifact must be tested after implementation.
- **No regressions in the 1,061 fhir4ds-internal ViewDefinition tests.** Every change must preserve green on `pytest fhir4ds/viewdef/`.
- **Documentation updates required.** Public-facing docs (README, package docstrings, any website content touching ViewDefinition compliance) must reflect the new spec-test count, the SQLQuery module, and the `joins` extension disclosure.

## Approval

**APPROVED 2026-08-11.** Decisions on the four open questions from §9 of the feature plan (`fhir4ds-private/docs/architecture/plans/FEATURE_SQL_ON_FHIR_V2_SPEC_COMPLIANCE.md`):

1. **§M-2 server scope: LIBRARY-ONLY.** The four FHIR operations (`$viewdefinition-run`, `$viewdefinition-export`, `$sqlquery-run`, `$sqlquery-export`) are out of scope. The existing stdlib `http.server` CQL facade (`fhir4ds/cql/fhir_server/app.py`) is not extended. Server scope, if ever needed, is a separate future feature.
2. **§E-1 `joins` serialization gate: DEFERRED.** Default OFF. `ViewDefinition.to_dict()` continues to emit `joins` whenever the field is populated. The gate ships behind `viewdef.types._EMIT_JOINS_REQUIRES_PROFILE: bool = False` for a future feature to flip if downstream roundtrip consumers surface.
3. **Version target: `0.0.13`.** Skips `0.0.12`; human preference. `evolution.json.config.target_version` updated.
4. **Spec-suite sync cadence: RELEASE-CHECKLIST STEP.** A `fhir4ds-private/docs/` release-checklist entry (not a CI job) prompts the release engineer to re-pull from `FHIR/sql-on-fhir.js` before each release.

The Master Orchestrator is authorized to proceed to `feature_implementation` and execute Steps 1–8 of the plan in order.
