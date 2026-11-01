# Architect Handoff — CQL-22 EXPLORER launch (iteration 1)

## Structural audit of the QA-001 fix (fhir4ds/cql/translator/expressions/_query.py)
Golden-standard invariants applied:
1. No silent fallbacks — the fix REMOVES a silent drop (where clause discarded,
   Error-severity Message swallowed). It does not introduce a new fallback path.
2. General, not specific — the defer predicate keys on the source SQL SHAPE class
   (fhirpath_text/fhirpath scalar navigation) + clause presence, not on any
   resource type, path string, or fixture value. Verified: same lowering fires
   for `Encounter.reasonReference`-style sources already covered by the
   pre-existing list_transform branch (the fix extends it, does not fork it).
3. Layering — change stays inside query-expression translation; no SQLRaw/to_sql,
   no cross-boundary reaches; SQL assembled purely as AST (SQLLambda, SQLFunctionCall,
   SQLSelect with WHERE for the subquery-safe UNNEST variant).
4. Dual-engine lockstep honored — the defect and fix are translator-level, so both
   the Python fallback and C++ extension paths are covered by the same dual-engine
   regression test.
Residual debt (pre-existing, not introduced): per-element RETURN projection still
uses scalar fhirpath_text (first-element-only) — ARCH-001 scalar-collapse class,
out of chunk scope, unchanged by this fix.

## QA Enforcer Gate
QA (EXPLORER) was NOT lazy: probed all mandated boundary axes (alias chains,
retrieves, multi-valued navigation, population criteria, uncertain-age conditions,
embedded quotes/unicode/long codes, Message-into-Message, e2e dual-engine) and
found the one remaining real defect. No veto; RETRY_QA stays false.

## Issue counts
1 MEDIUM SPEC_VIOLATION fixed (QA-001); 1 LOW INTENDED; 1 LOW UNCONFIRMED;
1 out-of-chunk observation (pre-existing audit_mode arg_min/arg_max unit failures
on the cumulative tree — flagged for human review, conformance gate unaffected).

## Recommended Fix Order (next engineer, if any)
1. Pre-existing test_audit_mode TestMinMaxAttribution failures (bisected to an
   earlier uncommitted launch's change, not this one).
2. ARCH-001 scalar-collapse debt for per-element return projections.

## Handoff compression
QA EXPLORER found that `Patient.name N where <cond> return N.given` silently
dropped its where clause — unfiltered results for every patient and swallowed
Error-severity Message raises (CQL 1.5 §9 + Appendix B), on both engines. Engineer
fixed it in _query.py by deferring the where into the per-element list_transform
path (list_filter before list_transform; WHERE in the UNNEST variant when
subqueries present), with a dual-engine regression test. Focused suites green
(message 13/13, nullological 15/15, aggregate+list 82/82); master gate fresh
2832/2832 on the final tree (DQM 47/47 first pass); binaries unchanged and
md5-matched (cql c5b22d58310c1eb7bafa17ce7877f989, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a).
Clean exit at iteration 1: zero non-terminal CRITICAL/HIGH/MEDIUM issues.
