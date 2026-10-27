---
id: omop-mapping
title: OMOP CDM v5.5 Mapping
sidebar_label: OMOP Mapping
description: Map FHIR R4 resources to OMOP CDM v5.5 tables with a ViewDefinition library — concept resolution at query time through ConceptMap view joins.
---

# OMOP CDM v5.5 Mapping

fhir4ds ships a ViewDefinition library that maps FHIR R4 resources to
OMOP CDM v5.5 tables. Concepts resolve **at query time** through the
rev-2 view-as-join-target architecture — no ETL staging of vocabulary
tables, no offline code mapping step.

## Architecture

```
monolithic FHIR ConceptMap resource          (the standard converter contract —
  │                                           one ConceptMap, groups per source system)
  ▼  conceptmap ViewDefinition (flatten)
omop.omop_conceptmap virtual table          (vocabulary_id | concept_code | concept_id ...)
  ▲
  └── Join.view ◀── every event ViewDefinition joins it ON (source system, code)
        │
        ▼
omop.person / visit_occurrence / condition_occurrence / ... (13 views, composed)
```

The chain is spec-grounded: SQL-on-FHIR composition semantics state that
"each referenced result acts as a virtual table for the referencing
query" — the engine may materialize the view's result or inline it.

Unmapped codes keep their source values with `concept_id = 0` (valid
OMOP); mappings can be swapped by restaging the ConceptMap without
touching a single ViewDefinition.

## The ConceptMap contract

The converter (the medterm4ds Athena pipeline, or any producer) emits a
standard FHIR ConceptMap: one group per source system
(`http://loinc.org`, `http://snomed.info/sct`, RxNorm, ICD-10-CM, CVX,
...), elements carrying `code` → `target.code` = the OMOP `concept_id`
as a string, `target.equivalence` of `equivalent`/`equal`/`wider`/
`subsumes`. The conceptmap ViewDefinition takes the FIRST
equivalence-passing target per code — a strict `(system, code) →
concept_id` functional dependency — so a code with multiple targets can
never fan out event rows.

Small curated supplements (`conceptmap-supplements.json`) cover codes no
Athena vocabulary provides: administrative-gender → Gender domain
concepts, v3-ActCode encounter classes → Visit concepts, and condition
categories → Type Concepts.

## Using the library

```python
import fhir4ds
from fhir4ds.viewdef.omop_runner import create_omop_views

con = fhir4ds.create_connection()
con.execute("CREATE TABLE resources (resource JSON)")
# stage FHIR resources + your ConceptMap(s) into `resources` ...
create_omop_views(con, source_table="resources")

con.execute("SELECT * FROM omop.person").df()
```

`create_omop_views` composes the whole `omop.*` schema:

- **Dependency inference**: each view's `Join.view` targets are resolved
  to their source ViewDefinitions and materialized in topological order
  (join targets first; cycles and unknown targets are typed errors).
- **Unions**: `drug_exposure` materializes its four arms
  (MedicationRequest / MedicationStatement / MedicationAdministration /
  Immunization) then a table-level `UNION ALL`.
- **Projections**: natural-key strings become stable positive 63-bit
  integer ids (`person_id`, `visit_occurrence_id`, ...); concept columns
  become `BIGINT` with `COALESCE 0` defaults.

The composition is manifest-driven (`manifest.json`); the generic runner
(`fhir4ds.viewdef.runner`) composes any view family the same way.

## Coverage

| OMOP table | FHIR source | Notes |
|---|---|---|
| person | Patient | gender via concept join; birthDate splits |
| visit_occurrence | Encounter | class → Visit concept; type 32810 default |
| condition_occurrence | Condition | SNOMED > ICD-10-CM coding precedence; category → Type Concept |
| procedure_occurrence | Procedure | SNOMED > CPT4 precedence; quantity 1 |
| drug_exposure | MedicationRequest + Statement + Administration + Immunization | 4-arm union; per-arm provenance type concepts |
| device_exposure | DeviceUsage | EHR type default |
| measurement / observation | Observation | value-type split: Quantity-valued → measurement |
| death | Patient.deceased | dateTime extraction |

ETL assumptions (type-concept defaults, provider/care-site 0-policy,
observation_period as a THEMIS ETL concern) are documented in the
[manifest](https://github.com/fhir4ds/fhir4ds/blob/main/fhir4ds/viewdef/resources/omop/manifest.json).
Field mappings are mined from the OMOP-on-FHIR v5.4-R4 project with
per-file attribution; the v5.5 delta (optional fields only) is noted
there too.

## Sample data

The Viewing Room's **OMOP** sample suite runs on real generated data —
a 25-patient [Synthea](https://synthetichealth.github.io/synthea/) R4
cohort (MIT; seed-pinned) — hosted on Hugging Face:

- [fhir4ds/omop-demo](https://huggingface.co/datasets/fhir4ds/omop-demo)
  — NDJSON bundles (patients, encounters, medications + immunizations)
  and one ConceptMap carrying every vocabulary mapping.

Hugging Face serves dataset files with CORS enabled, so the browser
(including DuckDB-WASM) fetches them directly — no server, no token
(the repo is public).

Four samples cover the two-layer story:

| Sample | Layer | Rows (25-pt cohort) |
|---|---|---|
| OMOP person | ViewDefinition | 25 |
| OMOP encounters | ViewDefinition | 1,284 |
| OMOP medications | ViewDefinition (MedicationRequest arm) | 1,143 |
| OMOP medications | SQLQuery (5-arm union, composed live) | 1,461 |

Append `?data=local` to the app URL to run against the compact
committed fixtures instead (8-patient slice + a 36-code RxNorm slice) —
this is what the e2e suite uses, so tests stay offline and fast.

### The ConceptMap: one resource, every vocabulary

A single ConceptMap resource carries all mappings, with one `group` per
source system:

| group source | mappings | covers |
|---|---|---|
| `.../rxnorm` | 108,421 | product-level RxNorm classes: Clinical Drug (SCD), Branded Drug (SBD), Quant Clinical Drug (SCDC), Quant Branded Drug, Clinical Pack (GPCK), Branded Pack (BPCK), Clinical Drug Comp, Branded Drug Comp |
| `.../sid/cvx` | 255 | immunization vaccine codes |
| `administrative-gender`, `v3-ActCode`, `condition-category` | 7 | person/encounter/condition supplements |

Every coded row in the cohort resolves — 54/54 RxCUIs (1,143/1,143
mentions) and 13/13 CVX codes. 27 MedicationRequests in the raw Synthea
output carry no medication code at all (`medicationCodeableConcept` is
null); they are not shipped, since a drug exposure with no drug has
nothing to map.

Element `display` fields are omitted (not needed for mapping);
`equivalence` is retained because FHIR requires it.

**Chunking is no longer needed.** Earlier revisions of this dataset
chunked the map at 20 elements per resource because the ViewDefinition
engine's `forEach` lowering was O(N × payload) and exhausted memory on
large arrays. That lowering now uses a pipelined unnest (compute the
array once per parent row, then unnest), so a single 108k-element
ConceptMap executes in well under a second and 100k-element maps are the
recommended shape.

## Try it

- Notebook: `docs/notebooks/omop-mapping.ipynb`
- Viewing Room: `?suite=omop` — the four OMOP samples above, resolving
  concepts live in the browser
- Conformance: `python3 conformance/scripts/run_omop.py` (37 checks —
  schema, required fields, grain, mapping, vd-conformance)
