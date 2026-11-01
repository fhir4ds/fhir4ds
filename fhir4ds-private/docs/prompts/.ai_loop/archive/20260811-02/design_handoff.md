# Design Handoff — SQL-on-FHIR v2 Spec Compliance + Analytics Layer

**Date:** 2026-08-11
**Designer:** Feature Designer (autonomous, `.ai_loop`)
**Plan:** `fhir4ds-private/docs/architecture/plans/FEATURE_SQL_ON_FHIR_V2_SPEC_COMPLIANCE.md`
**Draft (v1):** `fhir4ds-private/docs/prompts/.ai_loop/FEATURE_PLAN_DRAFT.md`
**Self-audit:** `fhir4ds-private/docs/prompts/.ai_loop/ARCHITECT_REVIEW.md`
**State:** `workflow: WAIT_FOR_USER_APPROVAL` — **the loop is paused for human approval.**

---

## 1. What was designed

A feature that brings fhir4ds's SQL-on-FHIR v2 ViewDefinition layer to full conformance with the current 2.1.0-pre spec, measured against the canonical 144-test conformance suite, and adds the spec's Analytics Layer (SQLQuery and SQLView Library profiles) as a DuckDB-only MVP.

The plan covers 7 work items in a strict sequence:
1. **§G-5** — Refresh the stale local snapshot of the spec test suite (134 → 144 tests; 12 new `repeat.json` tests are the highest-risk surface). **BLOCKER; lands first.**
2. **§G-1** — `cnl-1` URL invariant (error).
3. **§G-2** — `cnl-0` name invariant (warning).
4. **§G-3** — CanonicalResource roundtrip via extension bag (option B).
5. **§G-4** — `column.tag.name` namespace recommendation (warning).
6. **§E-1** — `joins` extension documentation (extension preserved, never removed).
7. **§M-1** — New `fhir4ds/sqlquery/` package implementing SQLQuery + SQLView Library profiles against DuckDB (the long pole, ~1.5 weeks).

Total: ~12 engineer-days. Steps 1–6 are quick wins (under 4 days combined).

---

## 2. How the plan was refined

The v1 draft was structurally sound — no invariant violations. The v2 refinement applies 10 skeptical notes from the self-audit:

| Note | Severity | What changed in v2 |
|---|---|---|
| S-7 | HIGH | Added a 4-branch triage decision tree to Step 1 so large-scope new spec failures pause the feature at `WAIT_FOR_USER_APPROVAL` instead of being silently absorbed. |
| S-1 | MED | Committed to extracting `viewdef.types.fhir_type_to_duckdb` as a public helper instead of hedging with "if accessible". |
| S-3 | MED | Named the existing `_quote_identifier` at `viewdef/generator.py:38` and committed to promoting it to public `viewdef/utils.py:quote_identifier`. |
| S-4 | MED | Expanded the §G-3 roundtrip test corpus from flat-string-only to four shape categories (flat string, complex extension array, deeply-nested extension, non-extension DomainResource field). |
| S-8 | MED | Committed to a dict-driven `_FHIR_TYPE_TO_DUCKDB` registry in `sqlquery/types.py`, not `if param.type == 'X'` branches. |
| S-10 | MED | Documented explicitly that `pyproject.toml` is **not** modified (sqlquery is a subpackage of the existing fhir4ds wheel target). |
| S-2 | LOW | Reframed "fall back to" → "select the most specific supported content type" to avoid the silent-fallback connotation. |
| S-5 | LOW | Replaced line-number citations in Step 2 with grep-based instructions (`grep -n "validate_optional_uri_string"`). |
| S-6 | LOW | Made the `joins` serialization gate default OFF explicit in both Step 6 and §7. |
| S-9 | LOW | Added `CREATE OR REPLACE VIEW` semantics + a docstring note about view accumulation. |

---

## 3. Architectural invariants the implementation must preserve

Eight falsifiable invariants from the self-audit (see `ARCHITECT_REVIEW.md` and §10 of the plan):

1. **I-1** — One-way dependency: `sqlquery` imports `viewdef`; `viewdef` never imports `sqlquery`.
2. **I-2** — No silent fallbacks in SQLQuery validation; typed `SQLError` subclasses only.
3. **I-3** — SQLQuery parameters bind via DuckDB prepared statements; no string interpolation.
4. **I-4** — `_extensions` bag preserves unknown keys verbatim, no validation.
5. **I-5** — `cnl-1` strictness applies to canonical URL fields only; `Column.type` stays permissive.
6. **I-6** — `cnl-0` and §G-4 surface only as warnings, never as errors.
7. **I-7** — `joins` extension runtime preserved; serialization gate (if implemented) defaults OFF.
8. **I-8** — §G-5 refresh changes only `tests/spec_tests/*.json`, the report markdown, and the test header comment — no `generator.py` / `parser.py` / `types.py` edits.

---

## 4. DECISIONS REQUIRED FROM THE HUMAN

The feature cannot proceed to implementation without answers to these four questions. They are listed in §9 of the plan and reproduced here for the approval gate:

### Q1 (Gate A) — §M-2 FHIR operations: library-only or server scope?

**Default if no answer: LIBRARY-ONLY.** The four spec operations (`$viewdefinition-run`, `$viewdefinition-export`, `$sqlquery-run`, `$sqlquery-export`) are out of scope. The Analytics Layer (§M-1 SQLQuery) is fully deliverable as a Python library.

If you choose server scope, §M-2 becomes a separate future feature; §M-1's design is unchanged.

### Q2 — `joins` serialization gate: any known downstream roundtrip consumers?

**Default if no answer: leave gate OFF.** Current behavior (`ViewDefinition.to_dict()` always emits `joins` when populated) is preserved. Documentation is added regardless.

If you know of consumers that roundtrip ViewDefinitions through other SQL-on-FHIR v2 runners (the JS reference implementation, the Verily Java runner, etc.) and need spec-compliant output by default, answer "enable gate" and the implementation adds the `meta.profile` check.

### Q3 — Version target?

The feature ships new public API surface (`fhir4ds/sqlquery/`). Is the target:
- `0.0.12` (patch), or
- `0.1.0` (minor bump)?

The state file currently records `0.0.11` as a placeholder. This does not block implementation; it blocks only the Release Engineer gate.

### Q4 — Spec-suite sync cadence?

After the initial refresh, should the periodic re-sync from `FHIR/sql-on-fhir.js` be:
- a CI job (runs on every PR; stricter), or
- a release-checklist step (runs before each release; cheaper)?

**Default if no answer: release-checklist step** (cheaper, matches current release cadence).

---

## 5. APPROVAL

To approve the plan and proceed to `feature_implementation`:

Write `APPROVED` (or `EXECUTE`) in `USER_DIRECTIVES.md` under a new `## Approval` heading. Optionally include answers to Q1–Q4 in the same section. The Master Orchestrator will pick up the approval, set `workflow: feature_implementation`, `phase: IMPLEMENTATION`, and dispatch the Feature Engineer.

To request changes, write `CHANGES REQUESTED` plus the specific concerns; the Master Orchestrator will return the loop to `feature_design` with `phase: DESIGN` and the requested refinements noted in `config.notes`.

To reject the plan entirely, write `REJECTED`; the loop exits with `exit_reason: NEEDS_USER_APPROVAL`.
