# QA Handoff — SOF-SQ-02 SKEPTIC (runner)

## Verdict: CLEAN — 12/12 fresh cases (flagged=0 after 4 adjudications)

Verified: SQLQuery->VD materialization (CREATE OR REPLACE VIEW from
generated SQL); SQLQuery->SQLView->VD two-level recursion; SQLView A->B->A
cycle -> SQLQueryCycleError BEFORE execution; dialect preference
(application/sql;dialect=duckdb over generic; postgres-only ->
UnsupportedDialectError); :name placeholder binding via prepared statements
(spec-example convention; positional ? unbound by named dict — documented);
missing param -> SQLQueryTypeError w/ name+declared-type; wrong-type
(string-for-boolean) -> SQLQueryTypeError w/ declared-vs-got; integer/date
coercion; Quantity param rejected at PARSE (parameter.type FHIR-primitive-
only, typed SQLQueryParseError); idempotent re-execution; label sql-name
invariant (special chars -> validation rejection before quoting).

Adjudications: r6/r9 bodies rewritten to :name placeholders (positional ?
is not the binding convention); r10 Quantity is parse-time primitive-only
rejection; r12 special-char labels are validation-rejected (sql-name
invariant) — quoting applies to valid names.

Evidence: .temp/qa/speccomp2/sofsq02_skeptic_probe1.py
