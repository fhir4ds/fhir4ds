# Architect Handoff - Fresh 0.0.5 Rerun

Structural health: PASS after remediation.

Architecture notes:
- The correct boundary is now explicit: core FHIRPath remains spec-strict, while SQL/DuckDB wrappers provide row-level resilience outside strict mode.
- Native FHIRPath collection equality now follows the same ordered collection semantics as the Python evaluator and R4 conformance.
- `AGENTS.md` and `GLOBAL_KNOWLEDGE.md` were updated with this invariant.

Issue counts:
- New HIGH findings: 2
- Resolved HIGH findings: 2
- Open CRITICAL/HIGH/MEDIUM findings: 0

QA audit:
- QA was sufficient. It found a genuine full-conformance regression and a native parity drift during the fresh rerun.
- No retry veto needed after final full conformance passed 2822/2822.
