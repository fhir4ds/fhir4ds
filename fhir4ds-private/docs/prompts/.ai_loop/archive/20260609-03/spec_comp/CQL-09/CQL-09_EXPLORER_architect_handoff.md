# Architect Handoff: CQL-09 EXPLORER

Golden standard: `.temp/architect/golden_standard.md` defines the CQL-09
comparison invariants for semantic comparison lowering, tuple element equality,
Quantity/Ratio helper routing, alias metadata separation, native/fallback
parity, and DQM/full conformance protection.

Structural audit result: no additional architectural findings. The two QA
defects were remediated at the correct translator boundaries:
`_translate_tuple_comparison()` delegates tuple-field equality back through
semantic CQL comparison lowering, `_alias_source_asts` keeps parser AST
metadata out of SQL AST state, `singleton from` preserves static source type
evidence, and tuple-list property access reads the tuple JSON value rather
than `alias.resource`. The final design adds no measure-, profile-, resource-,
or fixture-specific branch and continues to emit SQL AST/helper calls instead
of raw SQL shortcuts.

QA sufficiency: accepted. The EXPLORER probe covered the requested unusual
comparison paths, including nested tuple Quantity/Ratio fields, `singleton
from`, tuple-list query aliases, interval set-operation outputs, dynamic FHIR
choice value comparisons, and native-loaded versus forced Python fallback
execution. No `RETRY_QA` is required.

Resolved issue count: 2 HIGH `SPEC_VIOLATION` issues resolved and verified.
`QA-001` fixed tuple equality so Quantity/Ratio tuple fields use semantic
element equality. `QA-002` fixed alias/singleton type preservation for static
tuple fields while preventing parser AST leakage into SQL generation.

Validation: `.temp/qa/cql09_explorer_probe.py` passed; focused comparison
parity passed 9/9; official CQL conformance passed 1706/1706 including
`CqlComparisonOperatorsTest.xml` 198/198; DQM conformance passed 47/47
including CMS190; full conformance passed ViewDefinition 134/134, FHIRPath
935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

Recommended next action: clean exit for this inner evolution run and return
control to the outer spec-compliance orchestrator.
