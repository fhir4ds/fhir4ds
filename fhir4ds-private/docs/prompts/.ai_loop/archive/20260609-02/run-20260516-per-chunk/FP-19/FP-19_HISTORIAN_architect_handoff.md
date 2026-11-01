# Architect Handoff - FP-19 HISTORIAN

Structural review passed. The fixes preserve layer boundaries: core evaluator scope restoration stays in the Python engine, DuckDB wrapper lexical prechecks remain in the DuckDB adapter, and native JSON materialization stays in the C++ UDF boundary. No new public native/fallback parity drift remains for FP-19 probes.

The key architectural invariant reinforced is that lexical heuristics must never override parser-level trivia semantics, and owned native JSON values need explicit provenance rather than content-based guessing. The `__json__` marker is internal to the C++ materialization boundary and avoids treating arbitrary String values as JSON.

Issue count: 3 resolved, 0 open. Recommended fix order is complete. QA was sufficient for the HISTORIAN role: it covered aggregate scoping, lexical trivia, literals, identifiers, malformed lexemes, wrapper validity, and both native and forced fallback public surfaces. No `RETRY_QA` required.
