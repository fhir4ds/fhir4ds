## Architect Handoff - FP-09 HISTORIAN

Golden standard: FHIRPath §5.6 semantics must be shared across core Python evaluation, native DuckDB UDFs, forced Python fallback UDFs, and any direct helper API that claims FHIRPath behavior. Public SQL wrappers may translate typed FHIRPath errors to empty/NULL for row resilience, but helper and strict boundaries must still enforce singleton String input, Integer substring arguments, empty collection propagation, Unicode character indexing, and the exact `substring(start == len)` boundary.

Audit result: Structurally clean. The remediation is narrowly scoped to the direct helper abstraction, removes host-language string coercion from `_get_singleton_string()`, and changes only the FHIRPath boundary check for helper `substring()`. Regression coverage now spans direct helper semantics plus native-vs-forced-fallback public UDF parity. No architecture drift, silent fallback, hardcoded fixture behavior, or cross-layer coupling was introduced.

QA audit: Adequate. QA covered all five requested §5.6.1-§5.6.5 functions, native C++ and forced Python fallback paths, empty-vs-empty-string distinctions, multi-item errors, invalid types, Unicode positions, and the direct helper API. No `RETRY_QA` needed.

Issue status:
- `QA-001`: VERIFIED. Details archived in `ARCHIVE_LOG.md`.

Recommended fix order: none. The workflow is clean-exit eligible.
