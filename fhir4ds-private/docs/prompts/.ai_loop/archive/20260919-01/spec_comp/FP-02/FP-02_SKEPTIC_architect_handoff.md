# Architect Handoff — FP-02 SKEPTIC iteration 1 (2026-08-16)

## Golden Standard (invariants audited against this iteration)
1. Native C++ extension and Python fallback MUST produce semantically identical
   FHIRPath results (units, booleans, collections); display-precision
   differences follow the documented binary64-vs-Decimal convention.
2. Unit spelling between engines MUST be byte-identical (tests compare
   `fhirpath_text`/`fhirpath_json` outputs directly).
3. The shared `extensions/fhirpath/src/include/shared/ucum_units.hpp` table
   stays byte-identical unless the CQL extension is rebuilt too (FP-01
   constraint) — FHIRPath-specific semantics live at consumer sites.
4. `fhirpath_is_valid` classifies execution type errors as valid and
   singleton/syntax violations as invalid (GLOBAL_RULES doctrine).
5. Fixes must be class-general (exponent algebra, precedence-aware splitting),
   never expression-specific hint wrappers.
6. CQL translation must remain decoupled from FP_Quantity internals (no
   non-test CQL imports of fhir4ds.fhirpath.engine.nodes).

## Audit verdict
- **Invariant 1/2 — HELD (empirically):** 1280-case randomized differential
  corpus over quantity `* / + - = < > ~` with single- and multi-term units:
  0 semantic divergences; all 59 raw diffs were the documented
  native-16-digit vs Decimal-28-digit rendering of the same value with
  identical reduced units ('m3/L', 'm/s', 'Pa/g', 's2/g', '1/g2' ...).
- **Invariant 3 — HELD:** `ucum_units.hpp` untouched; only evaluator.cpp
  consumer-site helpers were added. CQL extension not rebuilt; CQL
  conformance 1706/1706 held on the final run.
- **Invariant 4 — CONSISTENT now:** the QA-002 fix removed the unary/binary
  classification asymmetry in BOTH backends; the one contradictory FP-06-era
  pin was updated with fixture-grounded justification
  (testPrecedence1/testMinus4 are both `invalid="execution"`; the strict
  core still errors, so official conformance is unaffected).
- **Invariant 5 — HELD:** no test-specific branches; the exponent algebra and
  pipe-precedence split are general. The legacy-concatenation fallback in
  `fhirpathComposeQuantityUnits`/`__mul__` only fires for unparseable units
  and preserves prior behavior (conversion still fails downstream → empty),
  documented at each site.
- **Invariant 6 — HELD:** no non-test CQL references to FP_Quantity.

## Structural notes (no action required)
- The `*` and `/` native branches collapsed their same-unit/different-unit
  result paths into the single exponent-merge call — behavior-preserving at
  the exact fix site (same-unit squares still render `m2`/`1`).
- Render order is sorted base symbols in BOTH engines; this changes
  cross-symbol product spellings only for reversed operand order
  (`2 'm' * 6 'kg'` now 'g.m', previously 'm.g'), which no pinned test
  relied on.

## QA Enforcer Gate
QA (SKEPTIC) was sufficient: 163 pre-hypothesized dual-path probe cases,
spec N1 + official R4 fixture truth tables fetched and cited, 8 hypotheses
pre-registered (5 rejected empirically, 3 confirmed as issues), plus a
4th issue the FIX phase caught through differential verification. No
RETRY_QA.

## Validation summary (final, post all fixes)
- Full conformance: **2832/2832** (ViewDefinition 144, FHIRPath 935,
  CQL 1706, DQM 47) — baseline held.
- fhirpath package pytest: **1670 passed / 0 failed** (one earlier
  aggregate-lexical failure was load-flakiness; passed in isolation and in
  the full re-run).
- Focused parity suites: operator/arithmetic/boolean/comparison/equality/
  collection 307 passed; comparison+conversion 65 passed.
- Native extension rebuilt and redeployed (repo + user site-packages).

## Issue ledger (all terminal)
- QA-003 HIGH RESOLVED — quantity unit exponent algebra (§6.6.1/§6.6.2).
- QA-001 MEDIUM RESOLVED — §6.8 union/arithmetic precedence in fallback
  is_valid.
- QA-004 MEDIUM RESOLVED — §6.2 quantity ordering base-table parity.
- QA-002 LOW RESOLVED — unary type-error is_valid classification.

## Recommended next steps (for the outer spec-comp orchestrator)
- Continue FP-02 with the HISTORIAN and EXPLORER personality launches per
  the campaign rotation; the §4.5 branch-1-vs-branch-2 ambiguity
  (convertible String/Integer nodes in Boolean context) is flagged in
  qa_handoff.md as an unresolved spec-reading question worth reference-
  implementation evidence.
