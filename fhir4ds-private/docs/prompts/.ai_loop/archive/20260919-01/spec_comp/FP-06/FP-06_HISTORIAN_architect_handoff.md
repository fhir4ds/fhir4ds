# Architect Handoff — FP-06 HISTORIAN (iteration 1, 2026-08-17)

## Structural audit scope
This iteration's working-tree delta: 2+1 surgical edits in
`fhir4ds/fhirpath/engine/invocations/misc.py` (intRegex `\Z` anchor, iif_macro
scope save/restore, numRegex `\Z` anchor) + regression test block in
`fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`.

## Golden-standard invariants applied (pre-established, from GLOBAL_RULES/AGENTS.md)
1. Dual-engine changes land in lockstep — here only the Python fallback was
   wrong; fixes align it to the already-correct native evaluator, so no
   native rebuild was required (verified: extension untouched).
2. Lazy functions must scope transient state — the iif fix mirrors native
   `fn_iif` (evaluator.cpp:7169) exactly for `defined_variables_` and
   `chain_defined_vars_`, closing the last known unsaved-scope site in the
   fallback's conversion section.
3. Lexical grammar checks must be exact — Python `re` `$` end-anchor matches
   before a single trailing newline; all FHIRPath lexical regexes in the
   conversion module now use `\Z` (intRegex, numRegex).
   `longDecimalStringRegex` still ends in `$` but its public surface
   (`toLong`) is not registered in this build; noted for the FP-07 Long
   chunk owner.

## Audit findings
- **QA-004 (MEDIUM, VERIFIED, found during audit)**: same `$`-anchor class in
  `numRegex` — `'1\n'.toDecimal()` → `1.0` in fallback vs empty natively.
  Fixed same-iteration (one-line `\Z`) with regression coverage; chunk-adjacent
  (§5.5.4) but identical root-cause class, deferred-fixing would only
  rediscover it in the Decimal chunk.
- No abstraction violations, silent fallbacks, hardcoded clinical logic, or
  test hacks introduced by the fixes. The iif fix uses the same save/restore
  idiom as `trace_fn`/`where` in the same module.

## QA Enforcer Gate
QA (HISTORIAN) was NOT lazy: 123 fresh dual-path cases on angles orthogonal to
the prior SKEPTIC launch's 209 (Unicode digits, Decimal-arithmetic seams,
scope-in-branches, calendar/derived-unit criteria); both real bugs carry
minimal reproducers and were correctly spec-attributed. RETRY_QA not set.

## Empirical validation
- Probe: 123/123 PASS. `pytest fhir4ds/fhirpath`: 1739 passed.
- Full conformance: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## Compression
QA found 2 MEDIUM parity bugs (trailing-newline integer grammar; defineVariable
leak from iif branch) plus 1 LOW INTENDED doctrine note; Engineering fixed both
in the Python fallback only (native already correct), added a 17-case parity
regression test, and held all baselines; Architecture found and fixed the
sibling numRegex newline bug (QA-004) and confirmed structural soundness.

## Recommended Fix Order (next iteration, if opened)
None — zero non-terminal CRITICAL/HIGH/MEDIUM issues. Clean exit at
min_iterations=1. `longDecimalStringRegex` `$`→`\Z` pre-hardening belongs to
the FP-07/Long surface owner.
