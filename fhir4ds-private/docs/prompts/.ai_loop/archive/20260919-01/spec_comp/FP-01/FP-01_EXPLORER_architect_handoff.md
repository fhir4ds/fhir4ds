# Architect Handoff — FP-01 EXPLORER Iteration 1 (2026-08-16)

## Structural health of this iteration's changes
Scope: the working-tree delta introduced by this launch (native decimal
arithmetic module + `math.div` fix + parity tests), audited against the
established golden-standard invariants (AGENTS.md FHIRPath sections,
GLOBAL_RULES.md).

### Golden-standard invariants checked
1. **Native Decimal-producing paths must populate source_text and re-anchor
   the numeric field** (FP-11 pattern). PASS — `FromDecimal(strtod(text))`
   at the single exit of `tryDecimalArithmeticText`; `fhirpath_number`
   verified equal to `float(Decimal)` on division results.
2. **Native/fallback byte-identical output.** PASS — 8463-case
   differential corpus vs Python-decimal ground truth, 0 FAIL; all 5 QA
   probes 0 divergences on the final state.
3. **No silent fallbacks masking errors.** PASS — the binary64 defer path
   is a documented boundary (JSON reals / text-less Decimals have no exact
   digits), not an error mask; zero-divisor still returns empty per §6.6.2.
4. **Reuse over duplication.** PASS with one observation — the new module
   reuses `addIntegerMagnitudes` / `subtractIntegerMagnitudes` /
   `multiplyIntegerMagnitudes` / `stripLeadingIntegerZeros`; however the
   single-digit division step (rem×10 then repeated subtract) appears
   three times in `fpDecDiv` (integer loop, fractional loop, tie-break
   continuation). A local lambda would deduplicate (~20 lines). LOW,
   cosmetic; no behavior risk. Logged as an observation, not an issue.
5. **Tests encode spec semantics, not implementation quirks.** PASS — the
   corrected FP-18 expectations carry the §6.6.2 rationale inline; new
   tests cite §4.1.4/§6.6.2/§5.5.8.
6. **General, not test-case-specific.** PASS — no input-specific branches;
   all rules (guard digit, tie continuation, zero signs, integral quantize)
   are general decimal-arithmetic semantics verified across the corpus.
7. **Extension deployment hygiene.** PASS — rebuilt and redeployed after
   every source change (3 builds), including a comment-only final change
   re-verified by the corpus.
8. **CQL extension isolation.** PASS — CQL extension untouched; CQL
   conformance 1706/1706 and CQL pytest 5631/9-skip held.

### QA Enforcer Gate
QA (EXPLORER) was NOT lazy: 221 fresh cases in 5 batteries mapped directly
onto the orchestrator brief (leap seconds, offset bounds, truncations,
scientific-ish forms, unicode escapes, plural/singular/abbreviated units,
§4.2-§4.5 operator/function interactions), every case executed on BOTH
engines with output comparison, and the two findings carried full
reproducers + spec citations. FIX-phase validation exceeded the role
minimum (8463-case differential oracle). **No RETRY_QA.**

## Issue summary
| ID | Sev | Status |
|---|---|---|
| QA-001 | HIGH | RESOLVED (native exact Decimal string arithmetic for + - * /) |
| QA-002 | HIGH | RESOLVED (§6.6.2 division-always-Decimal in both engines + quantize crash guard) |

0 non-terminal CRITICAL/HIGH/MEDIUM issues remain. Details archived to
ARCHIVE_LOG.md (FP-01 EXPLORER iter 1 section); `evolution.json` issues
tombstoned.

## Handoff compression
QA probed 221 pathological cases on both engines and found the literal
grammar surfaces (temporal, escapes, quantity spellings) clean while
discovering that native binary64 arithmetic corrupts >16-significant-digit
decimals under identity operations and that division was not Decimal in
either engine (fallback int/int→float; native double quotient with
opposite boolean outcomes, scientific JSON, 10^19 digit loss). The engineer
implemented an exact Decimal string arithmetic module in the native
evaluator mirroring Python `decimal` (28-sig half-even, ideal exponents,
IBM zero signs, long division with guard-digit + tie-break streaming,
integral one-decimal quantize) and converted fallback Integer operands to
Decimal with a quantize InvalidOperation guard (a pre-existing whole-UDF
crash). Validation: differential corpus 8463/8463, parity files 187/187,
fhirpath package 1608/1608, CQL 5631+9skip/0fail, full conformance
2832/2832 — baseline held; bundled extension rebuilt + redeployed.

## Recommended fix order (future)
1. LOW/cosmetic: dedupe the single-digit division step inside `fpDecDiv`
   (local lambda) next time `evaluator.cpp` is touched.
2. Observation: JSON-sourced reals still take the binary64 path in native
   (no exact digits); if a future chunk surfaces parity needs there,
   consider shortest-round-trip canonicalization at parse time — separate
   concern, do NOT bundle with FP-01.

## Exit
iteration 1 ≥ min_iterations (1); zero non-terminal CRITICAL/HIGH/MEDIUM.
Clean exit: workflow=null, exit_reason=CLEAN. Handoffs copied to
`spec_comp/FP-01/FP-01_EXPLORER_{qa,engineer,architect}_handoff.md` and
`FP-01_EXPLORER_evolution.json` for the outer spec-compliance orchestrator.
