# QA Handoff — SOF-SQ-03 SKEPTIC (integration seams)

## Verdict: CLEAN — 15/15 fresh checks (flagged=0 after 1 harness fix)

Verified: one-level chain (SQLQuery->VD) materializes + executes; two-level
chain (Q->SV->VD); mutual cycle SQLView A<->B -> SQLQueryCycleError BEFORE
execution; resolver failure -> SQLQueryMaterializationError w/ label+
canonical context; error model — SQLError <- SQLOnFHIRError; Cycle/
Materialization/Type errors <- SQLError; except SQLOnFHIRError catches all
transitively; all errors also <- ValueError (backward-compat); parsed-object
resolver contract (ViewDefinition objects + SQLView objects via isinstance);
parameter.name sql-name validated+quoted (9bad rejected); one-way dependency
(viewdef does NOT import sqlquery — verified via import-statement grep; a
types.py DOCSTRING mention is not an import); public API surface exports
all 7 names.

Harness fix: s10 grep initially matched a docstring reference; narrowed to
actual import statements.

Evidence: .temp/qa/speccomp2/sofsq03_skeptic_probe1.py
