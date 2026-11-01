# Architect Handoff - CQL-11 EXPLORER

The CQL-11 EXPLORER pass is clean after remediation. Five findings were fixed and verified across direct helper SQL, translated CQL, Python fallback, native-loaded C++, and C++-only/no-Python runtime paths.

Architectural guardrails to preserve:

- Treat public SQL macros as compatibility surface. Macro behavior must match translated CQL semantics where names overlap, especially for `Div`.
- Date/DateTime boundary constants must match official XML lexical values, including the `Z` suffix for DateTime min/max.
- Predecessor/successor is precision-aware for temporal values. Do not collapse partial Date/DateTime/Time values to milliseconds or full timestamps.
- DateTime marker forms (`YYYYT`, `YYYY-MMT`, `YYYY-MM-DDT`) are DateTime values, not numeric strings or malformed dates.
- Mixed scalar/Quantity arithmetic should construct typed Quantity JSON for the scalar side before UDF dispatch; direct parsing of numeric SQL literals as Quantity is not a valid lowering.

The golden standard for this role is in `.temp/architect/golden_standard.md`.
