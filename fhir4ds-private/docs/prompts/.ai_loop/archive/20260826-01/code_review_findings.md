# Code Review Findings — 0.0.12 Full Diff (2026-08-24)

**Reviewer scope per USER_DIRECTIVES**: full 0.0.12 diff (spec-compliance campaign + medterm4ds integration + evolution-campaign fixes); carry the REV ledger forward without re-litigating settled doctrine; clobber spot-check key fix symbols.

## REV ledger status (carried forward, re-verified)
**Open hardening/debt (unchanged, none regressed):** REV-002 (hand-maintained native/python semantic tables), REV-003, REV-005, REV-009 (DQM ERROR retry doctrine, terminal-unconfirmed), REV-010, REV-011, REV-012 (cqlUncertain dual-parser doctrine gap), REV-013, REV-014 (fhirpath fallback temporal±UCUM validity divergence), REV-015 (native regex named-group/anchor gaps), REV-016 (recursion-budget global stack_size mutation).
**Resolved (verified by symbol presence):** REV-001/004 (fhirpath native rework — `fhirpathSplitUnitTerm` absent as expected), REV-006/007, REV-008 (binary freshness).
Symbol spot-checks: `_parse_int_or_interval` (REV-012) present ×10; `_run_with_recursion_budget` (REV-016) present ×3.

## Evolution-campaign diff review (this session's changes)
Files: `cql/loader/fhir_loader.py`, `sources/filesystem.py`, `cql/__init__.py`, `cql/translator/expressions/_functions.py`, `cql/translator/cte_manager.py`, +4 test files.
- **SQL injection: CLEAN.** All user data flows through parameterized `execute(?, ...)`. Identifiers via `quote_identifier` (table names, Arrow temp tables keyed by validated `isidentifier()` table_name). The QA-018 `SQLRaw` block is fully static (no interpolation). The resolve() macro is static SQL.
- **Error hygiene: CLEAN.** Typed ValueError/TypeError with location attribution throughout; the one risky pre-flight guard (QA-014) was reverted under the Recovery Gate when it contradicted adjudicated doctrine.
- **Model knowledge: ACCEPTABLE.** The subject/patient/beneficiary element list is base-R4 structure documented in-doc; flagged under the existing REV-002-family metadata-debt (evolution QA-007 DEFERRED).
- **Performance: IMPROVED.** Arrow bulk path mirrors the load_valuesets doctrine with register/unregister in `finally` and executemany fallback (verified by import-blocking).
- **Maintenance notes (no issue logged, test-pinned):** (1) the MT-008 `result_type` propagation uses a defensive try/except AttributeError — if the AST classes ever grew `__slots__` the e2e evidence test would fail loudly, so the fallback cannot silently disable the fix; (2) the audit twin re-invokes `_wrap_list_aggregate` on shared `source_sql` (idempotent aliasing/correlation, verified by TestMinMaxAttribution + e2e).

## Clobber spot-check (key fix symbols)
`Patient-typed` doctrine (loader ×2, filesystem ×4 regexes), `_history` version strip ×4, `utf-8-sig` ×4, `Bundle.entry[` attribution ×4, `_bulk_rows` Arrow path, MT-008 twin + `result_type="Quantity"`, `ANY_VALUE(struct_extract` per-patient aggregation, QA-015/016/019 boundary messages — **all present**.

## Verdict
**CLEAN_WITH_NOTES** — zero new CRITICAL/HIGH/MEDIUM findings in the campaign diff; 11 open REV items carried as documented hardening debt (none regressed); master gate 2832/2832 on the reviewed tree; CQL suites fully green (1867/0, first time including MT-008 tests).

**Release note for the Release Engineer:** wheel must be built AFTER these fixes; the campaign changed `fhir4ds/cql/`, `fhir4ds/sources/` (pure Python — no native rebuild required); binary freshness (fhirpath/cql extensions) unchanged by this campaign.
