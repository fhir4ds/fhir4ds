# Code Review Findings — 0.0.13 diff (2026-08-26)

**Scope**: full diff vs 81957b59 (0.0.12 release) — 31 files, +1448/−606:
post-0.0.12 reliability fixes (4f7de65b), the evolution campaign's 22 fixes,
the medterm4ds 0.0.3 bound bump, the native-binary rebuild, and ruff
cleanups. VERDICT: **CLEAN_WITH_NOTES** — no CRITICAL/HIGH findings.

## Security (SQL/regex injection)

- No new injection vectors. New SQL constructions use static identifiers,
  quoted literals (`quote_sql_literal` path handling unchanged), or literal
  constants (`array_extract(...,1)`). C++ named-group translation constrains
  group names to `[A-Za-z0-9_]` before regex emission — no pattern injection.
- `_effective_path_pattern` expansion is `os.path.isdir`-guarded and
  glob-metachar-aware; cloud prefixes pass through untouched.

## Model-knowledge-in-logic

- Campaign typing fixes consume schema metadata (`FHIR_TYPE_TO_CQL_TYPE`,
  `fhir_schema.get_element_type`) — data-driven ✓.
- REV-017 (LOW): one new shape-regex (`extension.where(...).value$`) in
  generic translator code — base-R4 carve-out, noted for centralization.

## Error hygiene

- No new swallowing: every new except is a typed fallback (repr-key, None
  guards) with the error path preserved. Supersession comments cross-cite
  doctrine and tests.

## Post-0.0.12 fix spot-checks (clobber check — all present)

- orjson depth-limit dual-spelling match (udf.py `_parse_json`) ✓
- numpy-safe `_truthy` (dqm/evaluator.py, sequence semantics) ✓
- `_declared_parameters_only` (dqm/batch.py, ParameterDefinition filter) ✓
- recursion-limit scoping to main() (run_dqm.py, cli.py) ✓ — import leak fixed

## REV ledger

- Carried unchanged (11 open hardening items REV-002/003/005/009-016) — none
  touched by this diff; REV-009 retry doctrine exercised live this campaign
  (DQM gate passed on retry).
- New: REV-017 (LOW model-knowledge note), REV-018 (LOW re-parse note,
  pre-existing), REV-019 (LOW C++ style).

## Campaign-diff C++ audit

- Exact div/mod long division: b==0 guarded upstream; digit strings never
  empty (parseFpDecimalDigits floors at "0") — no divide-by-zero/empty loops.
- 2^63 literal + unary chains match pinned contracts; binary rebuilt and
  md5-verified across all deployment surfaces.
