# Architect Handoff - FP-20 EXPLORER - 2026-05-17

Golden standard written to `.temp/architect/golden_standard.md`. The implementation now satisfies the relevant invariants: public native/fallback parity for exposed environment-variable helpers, no silent valid result for invalid variable mutation, and scoped restoration of transient variables around expression-parameter callbacks.

Architectural assessment: CLEAN. The fix is scoped to the Python core fallback path and shared expression-parameter scope restoration. It does not add FHIR-model hardcoding, does not touch C++, and keeps native behavior as the parity reference. The new tests compare the full public DuckDB tuple for `defineVariable()` success, same-chain redefinition, system-variable overwrite, `where()` leakage, and `aggregate()` leakage.

Issue summary:

- HIGH: 1 found, resolved, verified (`QA-FP20-EXP-001`).
- CRITICAL/MEDIUM active: 0.

QA quality audit: sufficient. EXPLORER covered the requested odd public shapes across native and forced fallback paths, including nested/shadowed environment variables, `%context`/`%resource`/`%rootResource`, malformed grammar, type/reflection shapes, and row-resilient wrappers. No `RETRY_QA` requested.

Recommended follow-up order: none for this FP-20 EXPLORER loop. Keep `defineVariable()` in future parity matrices because it is native-exposed and easy for fallback paths to miss.
