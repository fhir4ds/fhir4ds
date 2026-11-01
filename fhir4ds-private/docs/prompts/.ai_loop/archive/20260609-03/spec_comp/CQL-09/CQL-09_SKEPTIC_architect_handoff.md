# Architect Handoff: CQL-09 SKEPTIC

Golden standard written to `.temp/architect/golden_standard.md`. The comparison fixes are structurally sound: they keep CQL-specific comparison behavior in the translator/operator layer and helper UDF layer, avoid raw SQL string assembly, add no FHIR profile or measure-specific knowledge, and preserve native-loaded versus forced Python fallback parity.

QA quality: sufficient. The SKEPTIC pass tested beyond happy paths and hit the chunk's key semantic risks: null propagation where SQL truth tables differ from CQL `between`, interval-valued `between`, Ratio equality/equivalence, temporal imprecision, list/tuple null equality, and both registration paths. No `RETRY_QA` needed.

Issues by category: 3 `SPEC_VIOLATION`, all resolved. Recommended fix order: none remaining for this pass. Details were archived in `ARCHIVE_LOG.md`, and durable lessons were added to `GLOBAL_KNOWLEDGE.md` and `extensions/cql/AGENTS.md`.

Validation confirmed: `.temp/qa/cql09_skeptic_probe.py` passed, focused comparison parity passed 6/6, and full conformance passed 2822/2822.
