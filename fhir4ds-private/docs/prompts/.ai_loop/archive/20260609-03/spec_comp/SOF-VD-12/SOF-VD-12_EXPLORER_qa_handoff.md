# QA Handoff: SOF-VD-12 / EXPLORER

Scope: SQL-on-FHIR ViewDefinition profiling and representations, with EXPLORER stress on combined profile declarations, JSON round trips, unsupported XML behavior, ignored mapping metadata, and metadata-heavy execution.

Spec anchors consulted:
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ShareableViewDefinition.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-TabularViewDefinition.html
- https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.profile.json.html

Fresh probe:
- `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd12_explorer_probe.py`
- Covered combined Shareable+Tabular `meta.profile` URLs with version suffixes, root `profile` round trip, canonical metadata retention for `resourceType`/`id`/`meta`/`url`/`version`/`name`/`status`/`title`/`description`, singular JSON field names, unsupported top-level `mapping` ignored and omitted, explicit XML parse rejection, invalid PublicationStatus rejection, present-null status rejection, Tabular collection rejection, and permissive validator warnings for direct invalid profiled dataclasses.
- Executed the same metadata-heavy valid view through native-loaded DuckDB FHIRPath and forced Python fallback.

Result: no product defects found. The only probe adjustment was correcting the scratch script's repo-root insertion to avoid importing an installed/stale package, matching existing ViewDefinition agent guidance.

Validation:
- Probe: PASS
- `python3 -m pytest fhir4ds/viewdef/tests/unit/test_parser.py -q`: 214 passed
- `python3 -m pytest fhir4ds/viewdef/tests -q`: 984 passed
- `python3 conformance/scripts/run_viewdef.py`: 134/134 passed
- `python3 conformance/scripts/run_all.py`: overall 2822/2822 passed
