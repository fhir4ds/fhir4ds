# QA Handoff: CQL-07 EXPLORER

Scope: CQL Appendix B conversion functions (`ToBoolean`, `ToConcept`,
`ToDate`, `ToDateTime`, `ToDecimal`, `ToLong`, `ToInteger`, `ToQuantity`,
`ToRatio`, `ToString`, `ToTime`) with EXPLORER emphasis on alias chains,
function inlining, invalid forms, and native-loaded versus forced Python
fallback parity.

Found one HIGH spec violation. Translated Patient-context CQL where `Q` was
defined as `ToQuantity(...)` returned internal Quantity JSON for `ToString(Q)`
and `convert Q to String` instead of the CQL Quantity text `5.0 'mg'`. The
same bug reproduced through an inlined user-defined function
`MakeQuantity(S): ToQuantity(S)`.

Fresh probe: `.temp/qa/cql07_explorer_probe.py`.
