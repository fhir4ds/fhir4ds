# QA Handoff - SOF-VD-12 SKEPTIC

## Scope
SQL-on-FHIR ViewDefinition profiling, Shareable ViewDefinition, Tabular ViewDefinition, mappings, XML, and JSON.

## Hypotheses Tested
- Root CanonicalResource metadata (`url`, `version`, `status`) may be silently dropped because the dataclass only models a small ViewDefinition-specific subset.
- `meta.profile` may be ignored, so Shareable and Tabular profile constraints may not activate.
- JSON field-name handling may drift from the official singular names such as `constant`.
- XML may be unsupported without a clear public contract.
- Profile metadata may accidentally change SQL execution or native/fallback FHIRPath behavior.

## Evidence
- Probe script: `.temp/qa/sof_vd12_skeptic/probe_sof_vd12.py`
- Official spec checked:
  - ViewDefinition base model is derived from CanonicalResource and includes inherited `url`, `version`, and `status`.
  - ShareableViewDefinition requires `url`, `name`, `fhirVersion`, and `select.column.type`.
  - TabularViewDefinition forbids collection columns and requires primitive column types.
  - XML and JSON representations are published for the logical model.

## Findings
- `QA-001` MEDIUM: parser accepts and then drops root `url`, `version`, and `status`; `meta.profile=ShareableViewDefinition` is ignored and does not enforce Shareable required fields.
- `QA-002` MEDIUM: `meta.profile=TabularViewDefinition` is ignored and allows `collection=true` plus complex `HumanName` output.
- `QA-003` LOW: XML parsing is unsupported but fails as generic invalid JSON and is not explicitly documented as unsupported.

## Validation
- `python3 .temp/qa/sof_vd12_skeptic/probe_sof_vd12.py`: reproduced all three gaps; official PatientDemographics-style execution matched native C++ and forced Python fallback.
- `python3 -m pytest fhir4ds/viewdef/tests -q | tail -n 50`: 888 passed.
