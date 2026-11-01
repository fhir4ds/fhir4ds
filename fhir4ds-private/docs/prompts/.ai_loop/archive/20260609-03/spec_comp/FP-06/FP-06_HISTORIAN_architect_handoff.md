# Architect Handoff - FP-06 HISTORIAN

Golden standard: `.temp/architect/golden_standard.md` defines the FP-06 invariants for exact §5.5 signatures, singleton conversion error boundaries, `iif` laziness, native/fallback public-surface parity, and bundled extension freshness.

Audit result: structurally clean. The remediation encoded general signature/cardinality rules rather than probe-specific strings. Native checks live at the evaluator dispatch boundary before semantic execution, while Python fallback checks live in the conversion helper boundary used by public UDFs. The selected `iif` branch remains lazy; malformed arity and multi-item criteria now fail before branch evaluation. The bundled extension was rebuilt and copied into the Python package path.

QA quality: sufficient. The HISTORIAN probe covered valid lexemes, invalid strings/ranges, empty propagation, multi-item input, wrong arity, `iif` fluent context, and lazy branch sentinels across native C++ and forced Python fallback. No `RETRY_QA` veto.

Issue status: `2` MEDIUM issues, both `RESOLVED`. No new architect findings.

Validation: probe `63/63`, focused pytest `12 passed`, native sqllogictest `388 assertions passed`, full conformance `2822/2822`.

Note: Per user directive, no archive files were updated and `spec_schedule.json` was not modified.
