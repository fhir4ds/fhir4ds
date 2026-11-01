# Architect Handoff — CQL-03 Spec Compliance, iter 1 — 2026-08-20

## Scope audited
The two landed fixes from this launch (QA-001 lexer temporal-literal
strictness, QA-002 native quantity-compare unit guard) plus the QA-003
INTENDED pin. Closeout audit after an interrupted run — fixes were already
landed and validated by the engineer.

## Fix 1 — strict temporal literal lexing (QA-001)
- `fhir4ds/cql/parser/lexer.py:_validate_datetime_literal` enforces CQL 1.5
  grammar shapes (zero-padded DATE/TIME/DATETIME, optional `Z|±hh:mm`),
  full calendar validation via `datetime.date`, and Time component ranges.
- Layering sound: validation lives at the lexer boundary where LexerError
  belongs; no silent fallbacks; error messages carry line/column.
- Offset-range VALUES (`+14:30`, `+99:00`) are deliberately runtime-null,
  not lex errors — consistent with the conformance doctrine pinned in
  test_datetime_part1_parity.py (documented in-code). Shape errors
  (`+02` missing minutes) are lex errors. Acceptable split.
- Regex patterns composed by concatenation with an in-code note about the
  f-string `{2}` hazard — good institutional hygiene.
- Verified: `test_cql_malformed_temporal_literals_rejected_at_lex_time_per_spec`
  (15 valid + 18 malformed) passes; chunk parity file 17/17.

## Fix 2 — same-code quantity comparison unit guard (QA-002)
- `extensions/cql/src/cql/quantity.cpp:same_code_unit_valid_for_compare()`
  guards the same-code fast path in `quantity_compare()`: table units,
  UCUM annotations (`{dose}`, `[pH]`), annotated known units (`mm[Hg]`),
  and compounds of valid components (`mg/m2`) compare by value; unknown
  bare codes (`xyz`) → null per CQL 1.5 §Equal (equivalence wrapper → false
  per §Equivalent). Spec-correct and minimal.
- Recursion guard present (early return for separator-free codes) — the
  segfault from the first corrected build is structurally prevented.
- REGRESSION RISK CHECK: the DQM catch-and-correct during FIX is real and
  permanently relevant — a table-only guard broke CMS69/CMS771/CMS1218
  (annotation/compound units). The landed annotation/compound-aware guard
  restored DQM 47/47; documented in AGENTS.md so future edits are gated.
- Deployed binary verified this session: md5 67c1b10a93db5cc47b26082dfc43de21
  matches across repo bundle and site-packages.
- Verified: `test_cql_invalid_unit_quantity_comparison_returns_null_per_spec`
  (8 cases × both backends) passes.

## QA audit (Enforcer Gate)
SKEPTIC QA was adequate: ~120 execution-level dual-backend expressions
covering literal forms, accessors, timezone normalization, uncertain
precision, quantity conversion equality, Ratio literals, implicit casts,
ToString of all five types, and null propagation; both cited HIGHs had
concrete reproducers and correct spec citations. No RETRY_QA.

## Empirical validation (this session, 2026-08-20)
- Both cited regression tests: pass (2/2).
- Focused sweep: test_temporal_complex_parity.py (17) + test_ratio_udfs.py
  (40) → 57/57 pass.
- Master conformance gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47). See `.temp/qa/cql03_spec_2026_08_19/closeout_gate.log`.

## State hygiene
All three issues terminal (2 RESOLVED, 1 INTENDED); full details retained
in evolution.json for the outer spec-compliance orchestrator (chunk runs
multiple personality launches against the same state file). Archived in
AGENTS.md discoveries section (CQL-03 launch entry).

## Verdict
No architecture regressions. Both fixes are spec-grounded, minimally
scoped, layered correctly, and regression-gated. Chunk-level guidance:
CLEAN exit at iteration 1 (≥ min_iterations 1, zero non-terminal
CRITICAL/HIGH/MEDIUM).
