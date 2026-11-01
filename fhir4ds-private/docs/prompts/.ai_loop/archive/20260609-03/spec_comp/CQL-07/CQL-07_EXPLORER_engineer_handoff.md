# Engineer Handoff: CQL-07 EXPLORER

Resolved `QA-001`.

Root cause: conversion function definitions lost semantic CQL type metadata.
`ToQuantity(...)`, `ToRatio(...)`, `ToConcept(...)`, and `ToLong(...)` were not
classified by `_infer_cql_type`, and user-defined function calls did not inherit
the inlined body type. Quantity aliases could therefore become resource-shaped
CTEs with `resource` columns, and later `ToString(Q)` lacked Quantity evidence.

Fix: added conversion return-type inference, classified scalar conversion
functions as patient-scalar rows, kept conversion definition columns on
`value`, and routed statically known Quantity `ToString(...)` through
`QuantityToString`. Added population-SQL parity coverage for direct
`ToQuantity` aliases and function-inlined Quantity aliases.

Validation:
- `python3 .temp/qa/cql07_explorer_probe.py`
- `pytest` conversion/check/clinical/primitive/structural parity: 46 passed
- Full conformance: 2822/2822
