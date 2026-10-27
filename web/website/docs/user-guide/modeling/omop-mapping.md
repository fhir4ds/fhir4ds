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
  and the RxNorm ConceptMap.

Hugging Face serves dataset files with CORS enabled, so the browser
(including DuckDB-WASM) fetches them directly — no server, no token
(the repo is public).

Four samples cover the two-layer story:

| Sample | Layer | Rows (25-pt cohort) |
|---|---|---|
| OMOP person | ViewDefinition | 25 |
| OMOP encounters | ViewDefinition | 1,284 |
| OMOP medications | ViewDefinition (MedicationRequest arm) | 1,170 |
| OMOP medications | SQLQuery (5-arm union, composed live) | 1,488 |

Append `?data=local` to the app URL to run against the compact
committed fixtures instead (8-patient slice + a 36-code RxNorm slice) —
this is what the e2e suite uses, so tests stay offline and fast.

### ConceptMap transport: chunked resources

The full standard RxNorm set (157k concepts) cannot be shipped as one
monolithic ConceptMap: DuckDB (and DuckDB-WASM) exhaust memory unnesting
JSON arrays that large. The dataset ships one thin ConceptMap **per 20
elements**; the conceptmap ViewDefinition flattens them back into the
long mapping table. The shipped subset covers the two standard classes
real medication data uses — Clinical Drug (SCD) and Branded Drug (SBD):
56,836 mappings, ~90% of the cohort's medication requests resolve; the
rest (packs and quantified forms outside SCD/SBD) surface concept 0 with
their source values, the OMOP no-map convention. Element `display`
fields are omitted (not needed for mapping); `equivalence` is retained
because FHIR requires it. Extend by appending more chunked ConceptMap
lines.

## Try it

- Notebook: `docs/notebooks/omop-mapping.ipynb`
- Viewing Room: `?suite=omop` — the four OMOP samples above, resolving
  concepts live in the browser
- Conformance: `python3 conformance/scripts/run_omop.py` (37 checks —
  schema, required fields, grain, mapping, vd-conformance)
