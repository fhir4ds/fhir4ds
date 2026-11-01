# QA Handoff — SOF-VD-12 / SKEPTIC (fresh rerun, 2026-07-03)

**Chunk**: SOF-VD-12 — Profiling, Shareable/Tabular ViewDefinition, Mappings,
XML/JSON.
**Spec**: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html
(v2.1.0-pre). ShareableViewDefinition requires url/name/status/fhirVersion/
column.type; TabularViewDefinition forbids collection columns and non-primitive
types; canonical URL/version/profile metadata preserved; JSON round-trips;
XML unsupported (no XML parser); unsupported mapping ignored/omitted; profile
metadata does not break execution.
**Personality**: SKEPTIC (Hypothesis Attacker).
**Command**: `python3 /mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-12_SKEPTIC/probe.py`
**Result**: **PASS — 12/12 hypotheses; 0 issues.**

## Hypotheses Tested (all rejected)

- **H1** Shareable profile requires url/name/status/fhirVersion/column.type — PASS.
- **H2** Tabular profile forbids collection columns — PASS.
- **H3** Tabular profile forbids non-primitive types (Address) — PASS.
- **H4** valid Shareable view accepted — PASS.
- **H5** JSON round-trip preserves official field names (resource/status/url/name/title/description/version/select) — PASS.
- **H6** invalid PublicationStatus rejected — PASS.
- **H7** canonical url preserved — PASS.
- **H8** version-suffixed profile canonical accepted — PASS.
- **H9** meta.profile canonical with whitespace rejected — PASS.
- **H10** unsupported mapping ignored and omitted from to_dict — PASS.
- **H11** XML/non-dict input rejected — PASS.
- **H12** profile metadata does not break execution (DuckDB run succeeds) — PASS.

## Probe

`/mnt/d/fhir4ds/.temp/qa/sof_vd_runs_2026_07_03/SOF-VD-12_SKEPTIC/probe.py`

## Notes

- All prior SOF-VD-12 fixes intact (SKEPTIC/HISTORIAN/EXPLORER 2026-05-20
  and 2026-06-01 fresh reruns). No source changes required.
- ViewDefinition pytest 1055/1055 PASS.
