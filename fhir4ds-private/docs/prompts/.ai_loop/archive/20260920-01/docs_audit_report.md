# Docs Audit Report — 0.0.15

**Date**: 2026-09-20 | **Auditor**: docs_audit workflow (post pre_release GO)

---

## 1. Notebook Execution Status

| Notebook | Result | Notes |
|----------|--------|-------|
| `docs/notebooks/cql.ipynb` | ✅ PASS | 0 errors, 0 debug artifacts; install pin 0.0.14→0.0.15 (fixed) |
| `docs/notebooks/dqm.ipynb` | ✅ PASS | same |
| `docs/notebooks/fhirpath.ipynb` | ✅ PASS | same |
| `docs/notebooks/viewdef.ipynb` | ✅ PASS | same |

All four executed top-to-bottom in a fresh venv (nbconvert, kernel `nbenv`)
against the 0.0.15 wheel via `--find-links ../../dist`. Output cells clean
(no DEBUG/WARNING/tmp-path artifacts).

## 2. Stale Data Log

| File | Issue | Fixed |
|------|-------|-------|
| `docs/notebooks/{cql,dqm}.ipynb` | `fhir4ds-v2[measures]==0.0.14` | ✅ → 0.0.15 |
| `docs/notebooks/{fhirpath,viewdef}.ipynb` | `fhir4ds-v2==0.0.14` | ✅ → 0.0.15 |
| `web/website/docs/api-reference/fhir4ds.md` | `evaluate_measure` signature stale (missing audit_mode/terminology_endpoint/closure_loaded) + return claim | ✅ documented full kwargs + DataFrame note |
| same | `create_connection` signature missing `valueset_cache` | ✅ added |
| same | `valueset_cache` shape undocumented | ✅ noted tuple/bare-string sets (both accepted) |
| `web/website/docs/api-reference/fhirpath/index.md` | Strict Mode section claimed property-name validation (`Patient.typo` raises) — **false**: strict_mode is grammar-only; unknown properties → `[]` in both modes | ✅ rewritten with real behavior |
| same | `resource_type=` kwarg in Custom Resource Types example — **does not exist** (TypeError) | ✅ rewritten: prefix resolves from `resourceType` in the resource |
| `web/website/docs/api-reference/sqlquery/index.md` | claimed unknown profiles "fall back to SQLQuery" — **false**: typed `SQLQueryParseError` | ✅ corrected |
| same + `releases.md` | `sql-on-fhir.org/ig/StructureDefinition/SQL{Query,View}` links → **404** (site moved) | ✅ → `build.fhir.org/ig/HL7/sql-on-fhir/StructureDefinition-SQL{Query,View}.html` (verified 200) |
| `web/website/docs/api-reference/sources/index.md` | 4 broken intra-docs links (`sources-csv` etc. vs actual `csv.md`...) | ✅ fixed 4/4 |
| `web/website/src/pages/index.tsx` | hero stats 2,822 / 134 stale | ✅ → 2,832 / 144 |
| `web/website/docs/getting-started/benchmarking.md` | 2,822 / 134 stale | ✅ → 2,832 / 144 (historical releases.md sections left as period-accurate) |

**Verified accurate (no change needed)**: `data-sources.md` patient_ref
raw-ID doctrine (live-verified against FHIRDataLoader output), D6
`SQLGenerator(dialect='duckdb')` (only duckdb supported — doc already says so
in signature default), `parse_view_definition` XML-unsupported note.

No `[PLACEHOLDER]` markers found anywhere in `web/website/docs/`.

## 3. Audience Alignment Notes

- **Stakeholder pages** (Landing, Benchmarking, Whitepaper): strategic tone
  intact; stats now consistent with the 2,832 baseline.
- **Developer pages** (User Guide, Integrations, API Reference): all code
  snippets re-verified against live API signatures this pass; the three
  false claims found (strict_mode, resource_type kwarg, parse_library
  fallback) were all in API reference pages and are fixed.
- `terminology.fhir4ds.com` and GitHub links verified live (200).

## 4. Draft Release Notes

v0.0.15 release notes already drafted during pre_release in
`web/website/docs/getting-started/releases.md` (DuckDB 1.5.5 reliability
release; platform + FHIRPath QA-001..008 + CQL QA-009..021 + medterm4ds
sections; 2832/2832 baseline). Reviewed this pass — accurate and consistent
with GLOBAL_KNOWLEDGE; no edits needed.

## Verification

- Website typecheck: EXIT 0
- Website build: EXIT 0
- Website e2e (post-fixes): **19/19 passed**
- Notebooks: 4/4 executed clean
