# Architect Handoff — FP-14 HISTORIAN iteration 1

## Golden Standard invariants applied (scoped to this launch)
1. Dual-engine lockstep — VIOLATED pre-fix: native `compareDateTimes`
   truncated fractional seconds to 3 digits while the Python fallback
   compared full precision (QA-001, HIGH). Fixed in evaluator.cpp;
   extension rebuilt AND redeployed (repo bundle + user site-packages) per
   the GLOBAL_RULES invariant that source-only edits do not affect package
   behavior.
2. Spec-grounded semantics — §6.2 "second and millisecond precisions are
   considered a single precision using a decimal, with decimal comparison
   semantics". The new fraction-digit compare (right-pad to equal width,
   digit-lexicographic) implements exactly decimal semantics; generality
   holds for any digit count (1–9+), both DateTime and Time, with/without
   timezone (instant compare unaffected — offsets don't touch fractions).
3. Exported helper APIs follow engine semantics — the two helper fixes
   (Time↔Date/DateTime type guard; None-guard on invalid lexical) close the
   class, not the cases: any invalid lexical form and any cross-type pair is
   now None/empty.
4. No test hacks — the native fix is in the shared compare path, not
   special-cased for probes; the parity test is parametrized over the
   semantic space, not the reproducer only.

## Audit of the fix diff (this launch's slice of the cumulative tree)
- `evaluator.cpp`: `frac_digits` populated before millisecond padding in
  BOTH parsers (datetime + time); `compareDateTimes` field loop capped at
  whole seconds with a single new fraction branch. The truncated
  `millisecond` int remains for non-comparison consumers — no behavior
  change outside ordering/equality.
- `datetime.py` `_engine_compare`: guards precede node construction; no
  duplicated comparison logic (delegate-to-engine doctrine respected).
- Residual (documented, no action): `FHIRDate.from_string` still
  over-accepts offset-carrying date strings ('2018-03-01+05:00'); the
  comparison boundary is now safe (None), but strict parse rejection is a
  separate parse-layer change left for a parse chunk. `FHIRDate/FHIRDateTime`
  dataclass dunders keep min-precision semantics (known FP-14 SKEPTIC
  residual; not on the public comparison path).

## QA Enforcer Gate
QA (HISTORIAN) was NOT lazy: re-verified all 3 SKEPTIC fixes regression-free
and hunted NEW ground the SKEPTIC pass missed — sub-millisecond fractional
precision (found the HIGH parity divergence), multi-item/type-mismatch
operands, spec timezone-conversion examples, one-sided offsets, time-valued
quantity comparability, chained ordering, and helper crash paths. The LOW
Date-vs-DateTime ambiguity (QA-004) was correctly filed UNCONFIRMED/DEFERRED
rather than spec-gamed — the right call given no fixture anchor and engine
agreement. No RETRY_QA.

## Validation evidence
- Focused: 178/178 (test_datetime.py + test_comparison_parity.py).
- Full fhirpath pytest tree: 1896 passed.
- Conformance (post-redeploy): ViewDefinition 144/144, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47 — OVERALL 2832/2832. Baseline held.
- Summary: `.temp/qa/fp14_historian_2026_08_18/conformance_summary.log`.

## State
QA-001 HIGH RESOLVED, QA-002 MEDIUM RESOLVED, QA-003 MEDIUM RESOLVED
(all verified this iteration); QA-004 LOW UNCONFIRMED/DEFERRED (terminal,
surfaced for human review). Zero non-terminal CRITICAL/HIGH/MEDIUM issues;
iteration 1 >= min_iterations 1 → CLEAN exit.
