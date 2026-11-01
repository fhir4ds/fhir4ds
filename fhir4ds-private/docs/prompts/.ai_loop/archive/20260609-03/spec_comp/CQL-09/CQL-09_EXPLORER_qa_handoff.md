# QA Handoff: CQL-09 EXPLORER

Personality: EXPLORER
Scope: CQL comparison operators (`Between`, equality/equivalence, ordered comparisons) with unusual composition paths.

Spec basis: The CQL comparison section defines `between` as inclusive lower/upper comparison and defines tuple equality by comparing corresponding elements. Quantity/Ratio values therefore must keep their semantic comparison paths when nested inside tuples, singleton extraction, and query aliases.

Probe written: `.temp/qa/cql09_explorer_probe.py`

Findings:
- `QA-001` HIGH: Tuple equality used raw SQL equality for element comparison. Quantity tuple fields compared JSON strings instead of compatible units, incompatible Quantity dimensions returned `false` instead of `NULL`, and Ratio tuple fields did not route through `ratioCompare`.
- `QA-002` HIGH: Static tuple fields from list/query aliases and `singleton from` lost Quantity/Ratio type evidence before comparison lowering. This caused a `singleton from { 1 'g' } = 1000 'mg'` conversion error and caused tuple-list query alias comparisons such as `T.q between 50 'cm' and 150 'cm'` to filter out valid rows.

Additional coverage included interval set-operation outputs, dynamic FHIR choice valueString vs numeric comparisons, and static Code equality/equivalence. No separate defect was found in those paths after local-source execution was forced in the probe.
