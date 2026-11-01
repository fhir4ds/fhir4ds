# FP-16 Architect Handoff (iteration 1, 2026-08-18)

Audit: single-issue iteration. Fix is minimal, root-cause-level, spec-cited, and follows
the established dual-surface doctrine (helpers mirror engine semantics and error
messages verbatim so the _is_valid_empty_result_error/native acceptance contract stays
coupled without edits). No lockstep C++ change required because the divergence was
Python-helper-only; public UDF parity was already correct.

Recurring-family note: "exported helper API forgotten" now at 12 instances. Structural
mitigation suggestion (deferred, LOW): an audit sweep that greps
fhir4ds/fhirpath/duckdb/{operators.py,functions/} for `return FHIRPathCollection([])`
early-exits on non-singleton guards, since silent-empty returns are the family's
signature. RETRY_QA not warranted: SKEPTIC probe battery was dual-path, spec-verified,
and fixture-anchored; issue fixed and validated same iteration.

Recommendation: clean exit (iteration 1 >= min_iterations 1; zero non-terminal
CRITICAL/HIGH/MEDIUM issues).
