# QA Handoff - SOF-VD-12 EXPLORER

## Scope
SQL-on-FHIR ViewDefinition profiling, Shareable ViewDefinition, Tabular
ViewDefinition, mappings, XML, and JSON.

## Spec Basis
- SQL-on-FHIR v2.0.0 ViewDefinition ties each instance to one FHIR resource type
  and allows profiling for shareable/tabular needs:
  https://sql-on-fhir.org/ig/2.0.0/StructureDefinition-ViewDefinition.html
- ShareableViewDefinition requires URL, name, FHIR version declaration, and
  column FHIR types for cross-runner interpretation:
  https://sql-on-fhir.org/ig/StructureDefinition-ShareableViewDefinition.html
- TabularViewDefinition constrains columns to scalar primitive values:
  https://sql-on-fhir.org/ig/StructureDefinition-TabularViewDefinition.html
- The IG publishes XML and JSON representations; this implementation documents
  XML input as unsupported and accepts the JSON representation.

## Exploration
- Created `.temp/qa/sof_vd_12_explorer_probe.py`.
- Tested combined Shareable+Tabular profiles with `|2.0.0` suffixes and an
  unrelated local profile.
- Tested unsupported profile URL alias
  `http://sql-on-fhir.org/ig/StructureDefinition/ShareableViewDefinition`.
- Tested top-level unsupported `mapping` field with identity/URI/name.
- Tested JSON round trip through `parse_view_definition()` and `to_dict()`.
- Tested XML input rejection.
- Executed a metadata-heavy Patient view under native C++ FHIRPath registration
  and forced Python fallback.

## Result
No CRITICAL/HIGH/MEDIUM issues found.

Observed intentional/documented boundary:
unsupported top-level `mapping` input is ignored and omitted from `to_dict()`.
It did not affect generated SQL or native/fallback execution.

## Validation
- `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_12_explorer_probe.py`
  passed. Native and fallback rows matched:
  `[("p1", True, "female"), ("p2", False, "male")]`.
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py fhir4ds/viewdef/tests/integration/test_duckdb.py::test_shareable_metadata_does_not_change_execution_native_and_fallback -q`
  passed: 150/150.
- `python3 -m pytest fhir4ds/viewdef -q` passed: 894/894.
- `python3 conformance/scripts/run_viewdef.py | grep -E "..."`
  passed: 134/134.

- `python3 conformance/scripts/run_all.py | grep -E "..."`
  passed: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.
