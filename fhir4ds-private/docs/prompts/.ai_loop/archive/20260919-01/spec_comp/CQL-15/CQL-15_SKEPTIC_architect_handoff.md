# Architect Handoff — CQL-15 iteration 1

## Golden-standard invariants applied
1. CQL interval semantics must be spec/reference-engine grounded and covered by focused
   dual-engine tests (GLOBAL_RULES CQL Translator Invariants).
2. Dual-engine lockstep: every semantic change lands in Python UDF and native C++, with the
   bundled extension rebuilt + md5-verified before the chunk closes.
3. Translator layering: no operator may be lowered through a different operator's semantics
   when the spec defines distinct behavior (the expand-wrap collapse-per violated this).
4. No silent fallbacks masking errors; fixtures/spec outrank implementation convenience.

## Audit of this iteration's fixes
- QA-001 fix is confined to `_translate_ends_op`, uses existing precision-truncation helpers,
  no fixture-specific branching. The point-operand degenerate-interval semantics now match
  the no-precision path and EndsEvaluator.kt. PASS.
- QA-002/003: replacing `collapse(expand())` composition with a dedicated per-aware UDF
  removes a genuine abstraction violation (reusing Expand's grid semantics for Collapse's
  merge-window semantics). Python and native implementations are algorithmically parallel;
  `collapse_intervals_per` added to `_PYTHON_PREFERRED_CPP_CONFLICTS` consistent with the
  documented "Python UDFs remain the conformance authority" doctrine. Extension rebuilt and
  deployed md5-verified (025c79edaea4af69621e5ae59060d1e3). Stale test pins were corrected
  rather than preserved — correct precedence (spec > pins). PASS.
- QA-004: coercion keyed on Interval AST nodes, not SQL shape — keeps list-typed identifiers
  untouched (the initial broader wrap broke `LNumeric except { null }` and was caught by the
  focused suite before landing). PASS.
- Documented boundary (not a defect): `_extend_bound_by_per`/`extend_high` no-op (no
  extension) on dynamically-incompatible per units; statically-incompatible per is rejected
  as NULL by the translator guard. Mirrors native behavior; noted in AGENTS.md doctrine.

## QA Enforcer Gate
QA was NOT lazy: ~100 dual-engine cases, verbatim spec examples, reference-engine source
verification (CollapseEvaluator.kt, EndsEvaluator.kt), and correct separation of
implementation artifacts (stale pins) from genuine violations. No RETRY_QA.

## Verdict
Zero open CRITICAL/HIGH/MEDIUM issues. audit_status PASS; recommend clean exit at
min_iterations=1.
