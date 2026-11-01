# Feature Handoff — SQL-on-FHIR v2 Spec Compliance + Analytics Layer

**Date:** 2026-08-11
**Engineer:** Feature Engineer (autonomous, `.ai_loop`)
**Plan:** `fhir4ds-private/docs/architecture/plans/FEATURE_SQL_ON_FHIR_V2_SPEC_COMPLIANCE.md`
**Commits:** `050e5e78` (Steps 1-6), `e83631a5` (Steps 7-8)
**State:** `feature_implementation` complete; ready for `code_review`.

---

## 1. What was built

All 8 steps of the approved plan executed. Two commits, both on `dev`:

### `050e5e78 feat(viewdef): SQL-on-FHIR v2 spec compliance (§G-1..§G-5, §E-1)`

- **§G-5 spec suite refresh** — Pulled canonical suite from `FHIR/sql-on-fhir.js` (134 → 144 tests; 12 new `repeat.json` tests). All green after 4 triage fixes:
  - Test infrastructure: depth-aware `_split_top_level_union_all` and `_has_top_level_where` in `test_spec_compliance.py` so UNION ALL inside LATERAL subqueries (SOF-VD-05 ARCH-003 pattern) isn't fragmented.
  - Generator: `NULLIF(fhirpath_text(...), '')` for uncast text columns to surface empty FHIRPath collection as NULL.
  - Type-guard compat: extended `dateTime`/`date` compat sets to accept cross-type boundary outputs.
  - Time boundary precision: `_time_boundary` preserves input-precision second/ms.
- **§G-1 cnl-1** — `_CANONICAL_RE = ^[^|# ]+$` on `ViewDefinition.url`. `profile[]`/`meta.profile[]` keep permissive URI validation since FHIR canonical type allows `|version`. `Column.type` unchanged.
- **§G-2 cnl-0** — Warning in `validate_view_definition()` for non-capital or >255 name.
- **§G-3 extension bag** — `_extensions: dict` on ViewDefinition preserves unknown top-level keys through `from_dict`/`to_dict`.
- **§G-4 tag namespace** — Warning for `column.tag.name` without `/` prefix.
- **§E-1 joins docs** — Disclosure in `viewdef/__init__.py`, `Join` dataclass, and new `fhir4ds-private/docs/joins-extension.md`. `_EMIT_JOINS_REQUIRES_PROFILE = False` module constant for future gate (deferred per human decision).

### `e83631a5 feat(sqlquery): SQL-on-FHIR v2 Analytics Layer MVP (§M-1)`

New `fhir4ds/sqlquery/` package:
- `types.py` — SQLQuery, SQLView, SQLContent, SQLParameter, SQLRelatedArtifact + `_FHIR_TYPE_TO_DUCKDB` dict-driven coercion registry.
- `parser.py` — Profile-conformant FHIR Library JSON parser with dispatch on `meta.profile`.
- `validator.py` — Profile invariants + `select_best_content` helper.
- `runner.py` — `SQLQueryRunner` with `CREATE OR REPLACE VIEW` materialization, recursive SQLView resolution with cycle detection, prepared-statement parameter binding.
- `errors.py` — Typed hierarchy (`SQLError` base + 6 subclasses).
- `AGENTS.md` — Package architecture notes.
- Public helpers extracted from `viewdef` per design: `viewdef.utils.quote_identifier` and `viewdef.types.fhir_type_to_duckdb`.
- 28 unit + integration tests covering parser dispatch, profile rejection, validator invariants, materialization (one-level and recursive), cycle detection, parameter binding across FHIR types, idempotent re-execution, dialect rejection.

---

## 2. Verification

| Suite | Pre-feature | Post-feature |
|---|---|---|
| ViewDefinition internal (fhir4ds/viewdef/) | 1061 | **1117** (+56) |
| FHIRPath (fhir4ds/fhirpath/) | 935 | **935** (no change) |
| SQLQuery (fhir4ds/sqlquery/) | 0 | **28** (new) |
| Spec compliance (spec_tests/) | 134 / 134 (stale) | **144 / 144** (current) |
| **Combined viewdef+fhirpath+sqlquery** | 2656 | **2710** |

No regressions. All architectural invariants I-1..I-8 preserved (verified during implementation, not just at end).

---

## 3. Out-of-scope items (intentionally deferred)

- **§M-2 FHIR operations** — Per human approval, library-only. The existing stdlib `http.server` CQL facade at `fhir4ds/cql/fhir_server/app.py` is not extended.
- **§E-1 serialization gate** — Deferred per human decision. `_EMIT_JOINS_REQUIRES_PROFILE = False` constant added; a future feature may flip it.
- **AST-level schema validation** of SQLQuery SQL bodies — Spec does not require; skipped per design.
- **Multi-dialect support** beyond DuckDB — Other dialects raise `UnsupportedDialectError`.

---

## 4. Handoff to code_review

Implementation is complete. Recommended focus areas for the code reviewer:

1. **`fhir4ds/sqlquery/runner.py:_materialize_one`** — Structural detection of ViewDefinition dicts (no `resourceType` field the way Library has) uses `select` + `resource` keys. Confirm this heuristic is robust; consider whether the resolver contract should be tightened to require typed returns.
2. **`fhir4ds/sqlquery/runner.py:_coerce`** — Light-touch type validation only. DuckDB handles actual coercion. Confirm this is the right balance (vs. comprehensive pre-validation).
3. **`fhir4ds/viewdef/generator.py:_quote_identifier`** — Now delegates to `viewdef.utils.quote_identifier`. Existing callers raise `ValidationError`; new helper raises `ValueError`. Confirm backward-compat path is sufficient.
4. **`fhir4ds/viewdef/types.py:_FHIR_TYPE_TO_DUCKDB`** — Registry is the single source of truth. Spec additions go here. Confirm coverage matches the FHIR primitive type set.
5. **`fhir4ds/viewdef/types.py:_extensions` bag on ViewDefinition** — Preserves unknown top-level keys verbatim, no validation. Confirm this matches §G-3 spec basis (DomainResource extension is intentionally open).
6. **`fhir4ds/viewdef/parser.py` cnl-0 warning** — Conservative check: flags non-capital or >255 length, not minimum length 2. Document this gap; spec regex requires 2+ chars but we don't over-enforce.

---

## 5. State transition

Per MASTER_ORCHESTRATOR §3, advancing `pipeline_step` from `feature_implementation` to `code_review`:
- `workflow: null` (signal feature_implementation is complete)
- `exit_reason: "CLEAN"`
- `pipeline_step: 2` (next: code_review)

The Master Orchestrator will dispatch the Code Reviewer next.
