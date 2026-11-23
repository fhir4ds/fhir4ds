---
id: piqi
title: Data Quality with PIQI
sidebar_label: PIQI
description: "Score clinical data quality with the PIQI framework: SAM checks and weighted rubrics authored as ViewDefinitions and SQLQuery Libraries, executed on DuckDB with PIQI Index scorecards."
---

# Data Quality with PIQI

[PIQI](https://piqiframework.org) (Patient Information Quality Improvement) is a published framework for scoring the quality of clinical data: a taxonomy of quality dimensions (HDQT), a catalog of **SAMs** (Specific Assessment Methods — pass/fail checks bound to data attributes), **rubrics** that sequence weighted criteria, and a per-message **scorecard** (the PIQI Index).

`fhir4ds.piqi` implements the framework on the SQL-on-FHIR stack you already use: the PIQI clinical data model (10 US-Core-based data classes) is a set of **ViewDefinitions**, and every SAM and rubric is a **SQLQuery Library** executed through the existing `fhir4ds.sqlquery` runner — dependencies resolve by canonical URL, cycles are detected, parameters bind through prepared statements. Nothing here is a CQL measure: the scorecard is a first-class surface, not a `MeasureReport`.

Three guarantees the implementation pins by test:

1. **Deterministic scoring.** Same inputs → byte-identical scorecard JSON; every SAM query ends in a deterministic `ORDER BY`.
2. **Bound parameters only.** No string interpolation of any parameter value into SQL, ever.
3. **Row absence = "could not assess".** SAMs emit only `pass`/`fail` rows; a check that cannot run contributes no row (the prerequisite's own failure carries the item).

## 1. Install

```bash
pip install fhir4ds-v2
```

## 2. Quickstart: score a corpus

Load the PIQI data-class views over your `resources` table, then evaluate the packaged sample rubric:

```python
import duckdb
from fhir4ds.piqi import load_piqi_views, evaluate_rubric

conn = duckdb.connect(config={"allow_unsigned_extensions": True})
from fhir4ds.fhirpath.duckdb import register_fhirpath
register_fhirpath(conn)

conn.execute("CREATE TABLE resources (resource JSON)")
conn.execute("INSERT INTO resources VALUES (?)", [
    '{"resourceType": "Patient", "id": "pat-1", "gender": "male",'
    ' "birthDate": "1966-05-18"}',
])

load_piqi_views(conn)   # 10 views materialized in schema `piqi`

scorecard = evaluate_rubric(conn, "sample")
scorecard.potential_item_score   # denominator: scorable items
scorecard.total_item_score       # numerator: passed items
scorecard.piqi_index             # 0..100
scorecard.critical_failure_count
scorecard.data_class_frequency   # {'Demographics': 1, ...}
```

The scorecard fields follow the PIQI Handbook contract: potential/total item scores, PIQI Index, critical failure count, data-class frequency, optional weighted variants, a per-dimension fail rollup, and — in verbose mode — one issue per failure naming the patient, element, attribute, SAM and HDQT dimension:

```python
scorecard = evaluate_rubric(conn, "sample", verbose=True)
for issue in scorecard.issues:
    print(issue.patient_id, issue.data_class, issue.entity,
          issue.sam_mnemonic, issue.dimension, issue.detail)

scorecard.to_dict()   # stable JSON export
```

## 3. Running a single SAM

SAMs return rows with the uniform schema `(patient_id, element_id, data_class, entity, sam_mnemonic, result, detail)`. Run one by instance id, optionally scoped to a patient:

```python
from fhir4ds.piqi import run_sam

rows = run_sam(conn, "piqi-sam-labresult-resultvalue-ispopulated")
rows[0]["result"]    # 'pass' | 'fail'
```

Parameterized SAMs (regex, allowed-value lists) take their parameters through DuckDB prepared statements:

```python
from fhir4ds.piqi import build_parameterized_sam, run_parameterized_sam

sam = build_parameterized_sam("Attr_MatchesRegex", "Condition", "condition")
rows = run_parameterized_sam(conn, sam, {"pattern": "^[A-Z]"})
```

## 4. What ships in the box

- **10 data-class views** (`piqi.<name>`): Allergy, Condition, Demographics, HealthAssessment, Immunization, LabResult, MedicalDevice, Medication, Procedure, VitalSign — each flattening its FHIR resource into the PIQI attribute shape (`<attr>_text`, `<attr>_codings`, value numbers, reference-range bounds).
- **64 SAM instances**: the guide's standard catalog bound across the classes — populated/numeric/date checks, concept completeness (`Concept_HasCode` / `HasCodeSystem` / `HasDisplay` / `IsComplete`), temporal past/future checks, range validity, class-level duplicate detection, and plausibility checks with clearly-marked placeholder content tables.
- **Prerequisite chains**: a SAM whose prerequisite failed emits no row; the prerequisite's own FAIL carries the item — the PIQI attribution rule.
- **The HDQT taxonomy** as an enum (`PIQIDimension`): 4 categories, 12 dimensions, with an alias table absorbing the guides' own spelling inconsistencies.

## 5. Authoring your own rubric

Rubrics are versioned FHIR content: criteria (data class + entity + SAM, with parameters), scoring effect, weight, criticality, and optional conditional SAMs. Author one with `build_rubric` and evaluate it like the packaged sample:

```python
from fhir4ds.piqi import build_rubric, evaluate_rubric

library, criteria = build_rubric(
    name="my_lab_quality",
    description="Core LabResult completeness checks",
    criteria=[
        {"data_class": "LabResult", "entity": "test",
         "sam": "labresult-test-iscomplete",
         "scoring_effect": "scoring", "criticality": False},
        {"data_class": "LabResult", "entity": "resultValue",
         "sam": "labresult-resultvalue-ispopulated",
         "scoring_effect": "scoring", "criticality": True},
    ],
)

scorecard = evaluate_rubric(conn, (library, criteria))
```

Conditional-SAM failures contribute neither numerator nor denominator; prerequisite failures increment the denominator but attribute to the prerequisite's dimension; informational criteria (weight 0) contribute statistics only. Weighted reporting switches on automatically when some weight is not 0 or 1.

## 6. Terminology SAMs

The terminology-dependent checks (`Concept_IsValidMember`, `Concept_IsConsistent`) validate codes against a ValueSet — the local `valueset_codes` cache first, then a terminology endpoint. With neither available they return an explicit `could not assess` result rather than a verdict:

```python
from fhir4ds.piqi import run_terminology_sam, COULD_NOT_ASSESS

rows = run_terminology_sam(
    conn, "Concept_IsValidMember",
    data_class="LabResult", entity="test",
    valueset="http://example.org/fhir/ValueSet/glucose-tests",
)
rows[0]["result"] is COULD_NOT_ASSESS   # True when unresolvable
```

Pass `endpoint=` (a `TerminologyEndpoint`) to consult a server — see the [Terminology Service guide](/docs/user-guide/terminology/terminology-service/).

## 7. Where to go next

- [PIQI API Reference](/docs/api-reference/piqi/) — scorecard facade, authoring builders, registry and terminology surfaces.
- [ViewDefinition Modeling](/docs/user-guide/modeling/viewdef/) — the flattening layer the PIQI views are written against.
- [Digital Quality Measures](/docs/user-guide/quality/dqm/) — CQL-based *measure* evaluation, for when the question is population membership rather than data quality.
