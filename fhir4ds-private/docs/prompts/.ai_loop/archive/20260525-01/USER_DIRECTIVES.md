# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal
Pressure test and prepare release version 0.0.7.

## Pipeline
1. evolution (8 iterations)
2. code_review
3. pre_release
4. docs_audit
5. benchmarks
6. scribe

## Feature Plan

## Focus Areas
- Run exactly one QA iteration for each core QA domain 3-10 in `fhir4ds-private\docs\prompts\.ai_loop\SPEC_QA_DOMAINS.md`.
- Do not advance from a domain iteration while it has unresolved non-terminal CRITICAL, HIGH, or MEDIUM issues. Fix and architect-review those issues before moving to the next domain.
- Keep 100% spec compliance. The final gate must include `python3 conformance/scripts/run_all.py`.
- Make sure all relevant pytest suites are passing. The final gate must include the full package pytest suite unless a documented environment limitation blocks it.
- For every DuckDB-backed surface in scope, test both the native C++ extension path and the forced Python fallback path where both exist, and compare outputs.
- Rerun the performance benchmarks and compare against the prior baseline. Treat scaling cliffs, memory spikes, or major unexplained regressions as release blockers.
- Include release/package/import checks for version 0.0.7 during pre-release validation.