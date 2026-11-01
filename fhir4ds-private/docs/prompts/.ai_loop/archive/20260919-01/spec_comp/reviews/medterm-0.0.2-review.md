# Code Review Findings — medterm4ds 0.0.2 remediation (code_review, 2026-08-24)

Workflow: `code_review` (pipeline step 2 of 2). Scope: MT-001..MT-007 delta only
(4 code files + 2 test files + pyproject.toml). The uncommitted 58-chunk
spec-compliance campaign tree was NOT reviewed. Review-only — nothing fixed,
nothing committed.

## Environment (unchanged)

`pip show medterm4ds` → 0.0.2 (site-packages,
`/home/jmontavon/.local/lib/python3.10/site-packages/medterm4ds`). Not reinstalled.

## Per-issue verdicts — all 7 CONFIRMED RESOLVED (independently re-verified)

- **MT-001 VERIFIED** — `pyproject.toml:63` `medterm4ds>=0.0.2,<0.0.3` + incident
  comment. `ner` extra's `medterm4ds[extraction]` untouched (directive scoped
  line 57 only). Diff clean.
- **MT-002 VERIFIED** — `http_adapter.py:491-498` sends
  `{query, searchMode, count:"25"}` + `system` only when mappable; legacy
  `category`/`mode` keys gone. Cross-checked against the installed 0.0.2 route
  (`apps/fhir_api.py` `search_get`): `system: str|None = Query(None, min_length=1)`
  single URI, `searchMode` pattern `^(lexical|hybrid|semantic|canonical)$`,
  `count: ge=1 le=200` (25 OK). Live spot-check: every URL emitted by
  `category_to_system_param` (condition/medication/lab/icd10/snomed/rxnorm)
  resolves via medterm's `FHIR_URI_TO_SYSTEM` registry; unknown/""/None → param
  omitted (correct all-systems semantic; medterm defaults to its 4 core systems).
- **MT-003 VERIFIED** — `expand()` GET and `expand_intensional()` POST both send
  `count=1000, activeOnly="false"`. FastAPI bool Query parses the string
  `"false"` → False; medterm's own `_parse_active_only_query_param` also accepts
  exactly 'true'/'false'. count=1000 == server `le=1000` max.
- **MT-004 VERIFIED** — `in_process_adapter.py:319-345`: primary
  `expand_url_pattern(engine, url, count=1000, include_retired=True)`; facade
  retained as ImportError fallback. Signature confirmed live against installed
  wheel: `(engine, url, *, count=1000, include_retired=False)`. Mock asserts
  kwargs exactly and `facade.expand_url.assert_not_called()`.
- **MT-005 VERIFIED** — `expand_intensional_value_set(engine, vs, 1000,
  include_retired=True)` positional count. Confirmed live that the installed
  0.0.2 function RETURNS a `(deduped, depth_cap_hit)` tuple despite its stale
  `-> list[dict]` annotation (read the actual `return deduped, depth_cap_hit`) —
  the adapter's tuple unpack is correct, not a bug. Facade fallback intact;
  protocol signature unchanged.
- **MT-006 VERIFIED** — RuntimeError from `connect()` re-raised with
  FHIR4DS_TERMINOLOGY_DB + build-duckdb / omit-path / prepare-derived hints.
  Reproduced LIVE against real 0.0.2: `connect('/nonexistent/mt.db')` → hinted
  RuntimeError preserving medterm's original message. `cache_indexes=True` with
  inner TypeError retry; outer TypeError → LocalDuckDBEngine fallback still
  reachable and correct (search_index_dir honored only there, DEBUG-logged
  otherwise).
- **MT-007 VERIFIED** — tests exist and assert the new behavior (param dicts,
  mock call signatures, hint contents). Fake audit re-run: plumbing/resolver/
  auto_coder fakes are protocol-level, no stale HTTP param dicts.

## New findings

### REV-001 (LOW, OPEN, latent — not triggerable today)
`fhir4ds/cql/terminology/system_mappings.py:67-79` — `category_to_system_param`
comma-joins multiple canonical URLs, but medterm4ds 0.0.2 `$search` `system`
is a SINGLE URI (`str | None = Query(None, min_length=1)`; an unresolvable
value 400s). Every current `CATEGORY_TO_SOURCES` value is a single-element
tuple, so the comma path is dead code today; a future multi-mnemonic category
(e.g. `"problem": ("SNOMEDCT_US","ICD10CM")`) would produce
`"http://snomed.info/sct,http://hl7.org/fhir/sid/icd-10-cm"` → 400 from the
sidecar. Fix (when needed): send `system` per-request or extend medterm to
accept a list. Logged only — review-only pass.

### Observations (no action)
- Installed medterm 0.0.2 `expand_intensional_value_set` has a stale return
  annotation (`-> list[dict]`, actually returns a tuple) — medterm4ds-side
  cosmetic; our adapter matches runtime behavior and the directive facts.
- `$search` `count` sent as `"25"` (string) vs `$expand` `count` 1000 (int) —
  httpx/FastAPI encoding-identical; non-issue.
- Breaker semantics, thread-safety model (HTTP locked, in-process
  single-threaded by contract), and error contracts (HTTP raises on failure,
  in-process degrades to `[]`) are unchanged by the diff.
- Diff scope clean: `git status` on the mandate paths shows exactly the 6
  files; no out-of-mandate edits.

## Gates (rerun this review)

- Master gate `conformance/scripts/run_all.py`: ViewDefinition 144/144,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47, **OVERALL 2832/2832 (100%)** — HELD.
- Terminology unit suite: **99 passed**.
- `test_medterm4ds_in_process.py`: **4/4 passed** against installed 0.0.2
  (live evidence the include_retired primary path works end-to-end).
- Fake-audit suites (plumbing 24 / resolver_fallback+auto_coder 40 via
  combined run): **all passed**.
- Live HTTP suite: skipped (`MEDTERM4DS_TEST_URL` unset — no sidecar), as in
  the engineer's run.
- MT-008 (pre-existing `test_audit_mode` arg_min/arg_max failures): confirmed
  out of scope per mandate; not chased.

## Verdict

exit_reason: **CLEAN_WITH_NOTES** — MT-001..MT-007 all genuinely resolved;
one latent LOW (REV-001) logged OPEN for a future launch; no regressions;
gate 2832/2832 held.
