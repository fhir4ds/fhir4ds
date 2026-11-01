# Architect Handoff — FP-14 iteration 1

## Golden Standard invariants applied (scoped to this launch)
1. Dual-engine lockstep: FHIRPath semantic changes land in Python fallback AND
   native evaluator.cpp. — N/A this launch: engines already §6.2-compliant;
   all three defects were in the Python-only exported helper module. No
   extension rebuild required (verified: no evaluator.cpp diff).
2. Exported helper APIs are public surface and must follow engine semantics
   (FP-09/FP-11 doctrine). — VIOLATED pre-fix (9th instance of the family);
   fixed by DELEGATION to engine `FP_*` compare(), the pattern recommended by
   REV-002/FP-11 (no third hand-maintained comparison table).
3. No silent fallbacks masking errors. — The helper's None-on-(TypeError,
   ValueError) mirrors the FHIRPath empty/uncertain convention at the helper
   boundary, not a masked failure. Acceptable.
4. Fix generality: the delegation fixes the class (any precision pair, any
   timezone pair, any trailing-zero form), not the probed cases.

## Audit of the fix diff (2 files, +118/−96)
- `datetime.py`: `_engine_compare` renders helper values back to lexical form
  and compares engine nodes — round-trip is lossless for the precision forms
  the helpers model; FHIRTime T-prefix ensured. Fractional-second pattern
  widened to 1–9 digits with scale-aware microsecond math.
- Residual (LOW, documented, no action): the `FHIRDate/FHIRDateTime/FHIRTime`
  dataclass dunders (`__lt__` etc.) still encode compare-at-min-precision
  semantics. They are no longer used by the public comparison surface
  (DateTimeComparisons delegates); remaining users are internal sorting and
  two explicit dunder unit tests. Flagged for the eventual helper-to-engine
  delegation cleanup (same family as REV-002).

## QA Enforcer Gate
QA was NOT lazy: 64 adversarial dual-path cases + full official R4 fixture
batch (81/81 both engines) + helper probe; all four orchestrator-briefed
focus areas (string collation, temporal precision/timezones, Boolean,
mixed Integer/Decimal at 28 digits, quantity strictness, criteria chaining,
empty propagation, batch parity, dual-path) covered. Three real defects
found, all in the correct layer. No RETRY_QA.

## State
Issues QA-001 (MEDIUM), QA-002 (MEDIUM), QA-003 (LOW) — all RESOLVED and
verified: test_datetime 82/82, fhirpath tree 1876 passed, conformance
2832/2832 (baseline held). Zero non-terminal CRITICAL/HIGH/MEDIUM issues.
Clean exit at iteration 1 (>= min_iterations 1).
