# QA Handoff — SOF-VD-12/HISTORIAN

## Scope
SQL-on-FHIR ViewDefinition profiling and representations: ShareableViewDefinition, TabularViewDefinition, JSON field names, XML unsupported stance, canonical URL/version/status/profile metadata, and native/fallback DuckDB execution.

## Spec Sources Consulted
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.profile.json.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ShareableViewDefinition.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ShareableViewDefinition.profile.json.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-TabularViewDefinition.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-TabularViewDefinition.profile.json.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-TabularViewDefinition.profile.xml.html

## Fresh Probe
Ran `python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd12_historian_probe.py`.

Confirmed clean behavior for:
- Shareable JSON field-name and metadata round-trip.
- Existing Shareable column-type and Tabular collection constraints.
- Explicit XML unsupported parse error.
- Metadata-heavy Tabular DuckDB execution parity under native C++ and forced Python fallback.

## Finding
`SOF-VD-12-HISTORIAN-001` HIGH: Supported Shareable/Tabular profile validation misses required `ViewDefinition.status`.

Evidence from fresh probe:
- `parse_view_definition()` accepted a ShareableViewDefinition with supported profile metadata but no `status`.
- `validate_view_definition()` returned no warning for a direct TabularViewDefinition dataclass missing `status`.

Expected:
- The supported profile validator should reject strict parser/direct serializer/generator paths and warn in permissive validation when ShareableViewDefinition or TabularViewDefinition is declared without `status`.

## Suggested Fix
Extend `validate_supported_view_profiles()` so supported Shareable/Tabular profile declarations require `ViewDefinition.status` before emitting or generating profiled JSON/SQL. Add parser tests for parse, `to_dict()`, and permissive validator warnings; keep existing valid profile tests updated with `status`.
