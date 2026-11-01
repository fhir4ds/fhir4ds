# QA Handoff - CQL-09 EXPLORER

Scope: CQL comparison operators `between`, `=`, `!=`, `~`, `!~`, `<`, `<=`, `>`, and `>=` across dynamic FHIR values, quantities, temporal precision, mixed collections, tuple/list equivalence, direct DuckDB helper calls, and native-loaded vs forced Python fallback execution.

Probe artifact: `.temp/qa/cql09_explorer_probe.py`.

Findings:
- `QA-CQL09-EXPLORER-001` (HIGH): dynamic FHIR numeric comparisons used text/cast behavior, so `Observation.valueString = "5"` could satisfy numeric comparisons, and `Observation.valueQuantity` vs static CQL quantities did not reliably use unit-aware `quantity_compare`.
- `QA-CQL09-EXPLORER-002` (MEDIUM): Quantity equivalence reused exact equality instead of least-precision decimal equivalence for non-duration quantities.
- `QA-CQL09-EXPLORER-003` (MEDIUM): generated population SQL could lose numeric guards through precomputed-column scalar-subquery optimization; CMS159 reproduced as a DuckDB binder error for `(SELECT value) < 5`.
- `QA-CQL09-EXPLORER-004` (HIGH): the first EXPLORER fixes over-applied `fhirpath_number` to internal CQL tuple JSON; CMS871 dropped to 70% because `EncounterDay.dayNumber > 1` filtered all eligible event days after `dayNumber` was serialized as text.

Evidence:
- Native and forced Python fallback probes covered translated scalar comparisons, direct `quantityCompare`/temporal/FHIRPath calls, dynamic FHIR choice values, and randomized compatible/incompatible Quantity pairs.
- CMS159 failed before remediation and passes after remediation.
- CMS871 failed at 70% after the first EXPLORER changes, then passed 10/10 after constraining `fhirpath_number` projection to FHIR `value[x]` paths.
- Final verification: comparison parity pytest 6/6; native C++ CQL unittest 628 assertions; full `fhir4ds/` pytest 7166 passed with 5 skips; full conformance ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
