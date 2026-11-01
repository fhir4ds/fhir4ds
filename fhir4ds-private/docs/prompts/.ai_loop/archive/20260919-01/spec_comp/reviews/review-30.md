# Code Review Findings — Spec-Compliance Campaign Milestone #6 (CQL-06..CQL-10)

**Date:** 2026-08-21
**Reviewer:** Code Reviewer role (milestone `code_review` workflow, sixth launch)
**Scope:** Uncommitted working-tree diff vs `db1e4164` (dev), delta since milestone #5 (review-25.md): CQL-06..CQL-10 chunk fixes — `.value` accessor identity (`strip_primitive_value_segments` in `_property.py`), `ConvertsToDecimal` regex, `ToQuantity` calendar keywords, `ToString` calendar rendering (data-driven from `_CQL_CALENDAR_DURATION_UNITS` registry), ToQuantity identity conversion, Coalesce variadic/typed/nested guards, list/interval/tuple equality null-uncertainty macros (`CQLNestedListEq`/`CQLJsonEq`/`CQLTupleValueEqual`), unit-'1' promotion in mixed comparisons, Integer+Long BIGINT promotion, Abs/Ceiling/Floor typed narrowing + extent guards, High/LowBoundary exact-Decimal transport, `_validate_static_arithmetic_operands`, Quantity/Quantity divide unit cancellation; native cql extension (boundary.cpp, math.cpp, quantity.cpp +176 lines, interval.cpp, cql_extension.cpp) + rebuilt binaries; extensive parity/regression test additions (~6,000 insertions across 50 files in `fhir4ds/cql`).

## Status of prior findings

- **REV-001 (LOW, OPEN)** — unguarded `std::stoi` family in evaluator.cpp (lines 1375, 1516, 2235). Unchanged; hardening only.
- **REV-002 (MEDIUM, OPEN)** — hand-maintained metadata drift surface. No new duplications this period; the `_CQL_CALENDAR_DURATION_UNITS` registry in `udf/quantity.py` consumed by `macros/conversion.py` is the correct data-driven direction (registry, not inline lists). Unchanged.
- **REV-003 (LOW, OPEN)** — unrelated untracked files (`conformance/architecture/`, `fhir4ds/dqm/AGENTS.md`) still in tree. Unchanged.
- **REV-004 (LOW, OPEN)** — `exactDecimalRatioText` (evaluator.cpp) input bounds present; still no explicit 128-bit budget guard. Unchanged.
- **REV-005 (LOW, OPEN)** — `_compile_regex` (strings.py:155) still passes patterns verbatim to `re.compile`. Unchanged.
- **REV-006/007 (RESOLVED/verified)** — no regression; symbol audit this review reconfirms.

## Clobber spot-check (CQL-06..CQL-10 symbols)

All key fix symbols present and unique: `strip_primitive_value_segments` (_property.py), `CQLNestedListEq`/`CQLJsonEq`/`CQLTupleValueEqual`/`CQLJsonEqElem`/`CQLJsonEqTemporal`/`CQLNestedListEqElem` (macros/list.py), `_validate_static_arithmetic_operands` (_functions.py), `ConvertsToDecimal` guards (conversion macros + parity tests), calendar-duration keyword rendering data-driven from `_CQL_CALENDAR_DURATION_UNITS` (macros/conversion.py:148-168), Coalesce typed/variadic guards (_functions.py:1366-1385, 2327+). Prior-period symbols still present (QA-103 DQM repair: `resolve_placeholders` order_by traversal in placeholder.py, add_alias row-shaped registration in _query.py). **No lost hunks detected.**

## Binary freshness (special attention)

- `cql.duckdb_extension`: repo bundle md5 `2722c674ccbdd1e542e4949f8f65c6ae`, identical in `~/.local/lib/python3.10/site-packages/fhir4ds/...`; no copies in `~/.duckdb` cache. Binary mtime Aug 21 07:01 > newest source (quantity.cpp 06:58, boundary/math 03:53) — fresh.
- `fhirpath.duckdb_extension`: repo bundle md5 `57d0634b6ee6eddee9fc06a1355bef5a`, identical in site-packages; binary (Aug 19 09:51) newer than evaluator.cpp (Aug 19 09:37). Foreign venvs under `/mnt/d/fhir4px-model/.venv` carry an older md5 (`5b17357b...`) — separate project installs, out of scope for this repo's deployment.

## DQM gate (CQL-05 repair still sound)

`conformance/reports/dqm_report.json` (suite 2025): 47/47 measures, 100.0% accuracy, 2,273 patients, 68 library-cache entries. viewdef_report: 144 passed groups; no failures. Live spot-check this review: `test_comparison_operator_parity.py` 15/15 passed in 41s (exercises the new unit-'1' promotion and Integer+Long BIGINT promotion paths). The QA-103 root-cause fixes (add_alias restoration, order_by placeholder traversal) remain intact and unclobbered.

## New findings

**None.** Audit details:
- No SQL-injection vectors: `con.execute(f"...")` sites in macros/conversion.py interpolate only internal constants and registry-derived unit lists (sorted, quoted from `_CQL_CALENDAR_DURATION_UNITS`), not user input.
- No new error swallowing: `except Exception` sites in udf/quantity.py and udf/math.py log warnings and return typed NULL (CQL null-propagation semantics); the `_functions.py:2150` broad except is a scoped static-inference fallback (pre-existing pattern); the `toConcept` duckdb_functions probe except is a feature-detection idiom.
- No IG/model-specific hardcoding in generic logic: CMS117/CMS72 hits are explanatory comments only; "Observation"/"Condition" occurrences are docstrings/comments; calendar keywords are registry-driven.
- SQLRaw usage remains confined to boundary/fallback APIs (today/now time literals in `__init__.py`), consistent with prior reviews.
- Macros follow null-uncertainty semantics with structural-type guards; no unsafe `to_sql()` in translation pipelines.

## Overall assessment

The CQL-06..CQL-10 delta is clean, spec-grounded, and well-tested (~6k lines of parity coverage added). Both native extension binaries are fresh and md5-matched across deployment locations. The CQL-05 DQM repair has held. The tree carries five open LOW/MEDIUM hardening/debt items (REV-001..005) — no blockers for the next pipeline step.

**Exit recommendation:** CLEAN (milestone review complete; open items are LOW/MEDIUM hardening debt tracked for the pre-release pass).
