# serve test fixtures

## `libraries/` — verbatim IG examples

`Library-SqlOnFhirExample.json`, `Library-UniquePatientAddressesQuery.json` and
`Library-OmopFhirPatientJoin.json` are unmodified copies of the SQL-on-FHIR v2
IG examples (line endings normalized to LF by the repo's `* text=auto`, like
every other file here):

    https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/Library-<id>.json

They are unmodified on purpose: they are the acceptance evidence that the
serve layer executes what the specification actually publishes (three required
parameters of three different FHIR types, two relatedArtifacts, a CTE with a
window function, and a three-way join across mixed FHIR/OMOP-ish views).

`Library-BloodPressureViewSqlView.json` is **not** from the IG. It is the
`blood_pressure_view` dependency that `Library-SqlOnFhirExample` references,
materialized as a SQLView Library instead of a ViewDefinition. Reason: the IG
query compares `blood_pressure_view.effective_date` against a `date` parameter,
so the dependency must expose a real SQL `DATE` column, and a ViewDefinition
emits temporal columns as `VARCHAR` (fixture-pinned by the official spec tests,
which assert string equality for date/dateTime). Casting in the SQLView keeps
the IG Library itself byte-identical. See `docs/design/serve-layer.md`.

## `viewdefinitions/` — the views the IG Libraries reference

Each carries the canonical URL the IG Library names in `relatedArtifact`:

| File | `url` | Referenced as |
| --- | --- | --- |
| `patient-view.json` | `https://example.org/ViewDefinition/patient_view` | `patient_view` |
| `patient-address-view.json` | `https://example.org/ViewDefinition/patient_address_view` | `patient_address_view` |
| `fhir-patient.json` | `https://example.org/fhir/ViewDefinition/Patient` | `fhir_patient` |
| `omop-person.json` | `https://example.org/omop/ViewDefinition/Patient` | `omop_person` |
| `diagnoses-view.json` | `https://example.org/ViewDefinition/diagnoses_view` | `diagnoses_view` |

Ids use hyphens because FHIR `id` is `[A-Za-z0-9-.]{1,64}` — underscores are
not allowed (the URLs keep the IG's underscore spellings).

The two OMOP-side views are FHIR projections standing in for OMOP tables: the
patient's OMOP identifiers (`urn:omop:person_id`, `urn:omop:source_system`)
carry the person key and source system, so `OmopFhirPatientJoin`'s
`omop_person.person_id = fhir_patient.mrn` join and its
`WHERE omop_person.source_system = :source_system` filter exercise real
cross-view joins without requiring a second physical dataset.

## `resources/bundle.json` — the synthetic dataset

Nine resources into the standard `resources` table
(`id`, `resourceType`, `resource`):

* **3 Patients** (`pt-1`..`pt-3`) — names, `active`, OMOP + MRN identifiers,
  1/2/1 addresses (the two-address patient exercises
  `ROW_NUMBER() ... PARTITION BY` in `UniquePatientAddressesQuery`), and
  `meta.lastUpdated` used as the address `updated_at`.
* **4 Observations** — blood-pressure panels (`85354-9`) with `8480-6` /
  `8462-4` components; `pt-3`'s is dated before the fixture query's
  `from_date`, so the date range filter is observable.
* **2 Conditions** — one each for `pt-1` and `pt-2`, so the OMOP join's inner
  join drops `pt-3` (2 rows out of 3 patients).

`effectiveDateTime` values deliberately carry no timezone: they are cast to
`DATE` by the blood-pressure SQLView.
