# Upstream Test Data Issues — ecqm-content-qicore-2025

Issues identified during automated CQL-to-SQL benchmark validation against
[cqframework/ecqm-content-qicore-2025](https://github.com/cqframework/ecqm-content-qicore-2025)
at commit `c0747b57`.

Our translator achieves **42/47 measures at 100% accuracy**. The 5 remaining
failures are all caused by test data issues documented below.

---

## Issue 1: CMS135 / CMS145 — DENEXCEPPass MeasureReports have denominator-exception = 0

**Measures:** CMS135FHIRHFACEIorARBorARNIforLVSD, CMS145FHIRCADBetaBlockerTherapyPriorMIorLVSD
**Mismatches:** CMS135: 3, CMS145: 3
**Related:** [MADIE-2124](https://oncprojectracking.healthit.gov/support/projects/MADIE/issues/MADIE-2124)

### Description

Test cases whose names indicate they should **pass** the Denominator Exception population
have MeasureReport files with `denominator-exception` count = **0** instead of the
expected **1**. All affected cases use the CQL negation rationale pattern
(`[MedicationNotRequested]` with `doNotPerform: true`).

The test descriptions explicitly acknowledge the problem:
- CMS135: *"Denominator Exception deselected for now due to negation issue."*
- CMS145: *"CQL-Execution Issue 296"*

Only 3 of CMS135's 12 DENEXCEPPass cases are affected (the 3 with negation);
the 9 allergy/diagnosis-based cases correctly have count=1.

### CMS135 affected test cases (3)

#### Patient `1f64a697-a90b-4aaf-a315-fa84168ac2b4` — MedicalReason

- **MeasureReport**: `MeasureReport-a4ae566c-5d99-4477-9587-6a813e0d394d.json`
  ```json
  { "code": "denominator-exception", "count": 0 }
  ```
- **Test description**: *"Patient with 2 ambulatory encounters, Heart Failure Dx,
  and LVEF < 40% falls into Denominator Exception due to Medical Reason for not
  prescribing an Ace or Arb medication. Note: Denominator Exception deselected for
  now due to negation issue."*
- **Evidence**: `MedicationRequest/93bae8ed-7235-4d62-9e24-ea162e43f80f`
  - Profile: `qicore-mednotrequested`
  - `doNotPerform: true`
  - Medication: RxNorm `1091652` — azilsartan medoxomil 80 MG Oral Tablet
  - Reason: SNOMED `183966005` — **"Drug treatment not indicated (situation)"**

#### Patient `d297e68e-3f02-42a8-a59f-a5a4cecbd47d` — PatientReason

- **MeasureReport**: `MeasureReport-a0634097-c3b9-46ae-956b-7313c9c15413.json`
  ```json
  { "code": "denominator-exception", "count": 0 }
  ```
- **Test description**: *"Patient GE 18years old with two ambulatory encounters,
  HF diagnosis and LVEF <= 40% is not prescribed ACE/ARB medication for Patient
  Reason. Note: Denominator Exception deselected for now due to negation issue."*
- **Evidence**: `MedicationRequest/2fde93e1-6a76-49b2-aa40-e4a5064b6a0e`
  - Profile: `qicore-mednotrequested`
  - `doNotPerform: true`
  - Medication: RxNorm `1091652` — azilsartan medoxomil 80 MG Oral Tablet
  - Reason: SNOMED `160932005` — **"Financial problem (finding)"**

#### Patient `64e76766-9760-4385-a977-cbe8136ce425` — PatientDeclinedAceArb

- **MeasureReport**: `MeasureReport-fdfad332-382b-442d-ab2d-741d647c4fa2.json`
  ```json
  { "code": "denominator-exception", "count": 0 }
  ```
- **Test description**: *"Patient GE 18years old with two ambulatory encounters,
  HF diagnosis, and LVEF <= 40%. Patient declined ACE/ARB medication prescription.
  Note: Denominator Exception deselected due to negation issue."*
- **Evidence**: `MedicationRequest/275edb1b-ceaf-4c0e-a48e-32a903d869a3`
  - Profile: `qicore-mednotrequested`
  - `doNotPerform: true`
  - Medication: RxNorm `1091652` — azilsartan medoxomil 80 MG Oral Tablet
  - Reason: SNOMED `134397009` — **"ACE inhibitor declined (situation)"**

### CMS145 affected test cases (3)

All three reference **"CQL-Execution Issue 296"** in their test descriptions.

#### Patient `1f70822b-c513-4c3a-8162-49f0bb9c914b` — DENEXCEPPop2Pass Carvedilol25MGOralTabletPatRsn2

- **MeasureReport**: Group 2 `denominator-exception` = **0**
- **Evidence**: `MedicationRequest/04bce691-...`
  - Profile: `qicore-mednotrequested`, `doNotPerform: true`
  - Medication: carvedilol 25 MG
  - Reason: SNOMED `406149000` — **"Medication declined"**
  - authoredOn: 2026-04-05

#### Patient `4a3086cd-63f3-41c3-8ce9-f75b4b18b85c` — DENEXCEPPop1Pass MedNotOrderedPatRsn

- **MeasureReport**: Group 1 `denominator-exception` = **0**
- **Evidence**: `MedicationRequest/1b84067c-...`
  - Profile: `qicore-mednotrequested`, `doNotPerform: true`
  - Medication via `qicore-notDoneValueSet` extension (ValueSet `2.16.840.1.113883.3.526.3.1184` = Beta Blocker Therapy for LVSD)
  - Reason: SNOMED `406149000` — **"Medication declined"**
  - authoredOn: 2026-10-15

#### Patient `dd4e465a-3796-4d5d-af53-3e2ab1e4041b` — DENEXCEPPop1Pass Carvedilol25MGOralTabletPatRsn1

- **MeasureReport**: Group 1 `denominator-exception` = **0**
- **Evidence**: `MedicationRequest/2e61d93e-...`
  - Profile: `qicore-mednotrequested`, `doNotPerform: true`
  - Medication: carvedilol 25 MG
  - Reason: SNOMED `406149000` — **"Medication declined"**
  - authoredOn: 2026-02-01

### Suggested fix

Update the `denominator-exception` count from `0` to `1` in the MeasureReport for
all 6 affected test cases. The clinical resources (MedicationRequest with
`qicore-mednotrequested` profile, `doNotPerform: true`, and valid reason codes)
correctly justify the denominator exception per the CQL logic.

---

## Issue 2: CMS996 — Missing valueset 2.16.840.1.113883.3.3157.4056

**Measure:** CMS996FHIRAptTxforSTEMI
**Mismatches:** 2

### Description

The CQL declares (line 35):
```cql
valueset "Major Surgical Procedure": 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.3157.4056'
```

This valueset is not present anywhere in the repository:
- Not in `input/vocabulary/valueset/external/` (no file matching the OID)
- Not in `input/vocabulary/valueset/spreadsheets/`
- Not in the measure-specific bundle at `bundles/measure/CMS996*/valuesets-*-bundle.json`

The OID appears in 20+ library/measure JSON files under `bundles/` and `input/resources/`
as a reference, but no expansion or definition is provided.

### Impact

Without this valueset, `[Procedure: "Major Surgical Procedure"]` retrieves return
empty results, causing the Denominator Exclusion rule *"Major Surgical Procedure 21
Days or Less Before Start of or Starts During ED Encounter"* to miss qualifying patients.

Example: Patient `55a3b23f`, `Procedure/03a288d8-fefe-4518-90fb-655b486682d2` has
code `5A1955Z` (ICD-10 PCS) which should be checked against this valueset.

### Suggested fix

Add the valueset expansion for `2.16.840.1.113883.3.3157.4056` to the vocabulary
directory or the measure-specific valueset bundle.

---

## Issue 3: CMS157 — Test data dates are in 2025 but measurement period is 2026

**Measure:** CMS157OncologyPainIntensityQuantifiedFHIR
**Mismatches:** 3

### Description

The MeasureReport files specify a measurement period of `2026-01-01` to `2026-12-31`,
but the clinical resources in the test bundles use dates from 2023-2025. All
observations, encounters, and procedures fall outside the measurement period and are
correctly filtered out, causing all population counts to evaluate to zero.

### Patient `18a871b4-b7d2-4fca-bd04-155b44965f4e`

**MeasureReport** (`MeasureReport-f0187aac-ea4d-4e32-8473-3272225932e6.json`):
- `period.start`: `2026-01-01`, `period.end`: `2026-12-31`
- Expected: IPP=1 (Group 2), Denom=1, Numer=0

**Clinical resources (all in 2025):**

| Resource | ID | Date | Field |
|----------|----|------|-------|
| Encounter | `4f8008f2-5378-4f64-a47f-b9615924c099` | **2025-11-01** | `period.start` |
| Encounter | `fafdc17c-eb86-45e0-a891-0a7fd3d2a072` | **2025-01-06** | `period.start` |
| Observation | `6bff62fe-fdbe-4982-87b3-c7a30e409c77` | **2025-01-06** | `effectiveDateTime` |

The MeasureReport expects IPP=1 for Group 2, meaning these 2025 resources are
*intended* to qualify — but they fall outside the declared 2026 measurement period.

### Patient `6c1a8557-73be-4026-9ec6-f0699bfcbfda`

**MeasureReport** (`MeasureReport-e46e6347-c30c-4288-a4e3-ec6f7ae9be57.json`):
- `period.start`: `2026-01-01`, `period.end`: `2026-12-31`
- Expected: All populations = 0 (IPP Fail)

**Clinical resources:**
- `Encounter/d14e3cd2-479a-4795-ab5e-6931be791293` — period: **2025-05-25**

### Suggested fix

Shift all clinical resource dates forward to fall within the 2026 measurement
period (e.g., 2025-01-06 → 2026-01-06), or update the MeasureReport measurement
period to `2025-01-01` / `2025-12-31` to match the existing data.

---

## Issue 4: CMS1017 — Contradictory MeasureReport and non-UUID bundle IDs

**Measure:** CMS1017FHIRHHFI (Hospital-wide Hand Hygiene Compliance)
**Mismatches:** 3

### 4a. Non-UUID inner bundle IDs

Inner nested bundles use human-readable test-case slugs as IDs:

**File:** `input/tests/measure/CMS1017FHIRHHFI/tests-02d5c5f5-9487-42af-bb5e-dfc3aaeb70eb-bundle.json`
```json
"id": "tests-NumerPass-RVwithDiureticsOrderAtAdmission-bundle"
```

**File:** `input/tests/measure/CMS1017FHIRHHFI/tests-3ee27450-2fd5-4930-bfbb-e718074e4087-bundle.json`
```json
"id": "OBSERVPass-DenomMeasObsPassDueTo1DayAnd1MinLOS"
```

### 4b. Contradictory MeasureReport observation counts

**Patient `02d5c5f5-9487-42af-bb5e-dfc3aaeb70eb`**
(`MeasureReport-b89135b7-8b8c-483c-b679-3b4b3362b313.json`):

| Population | Count |
|-----------|-------|
| Initial Population | 1 |
| Denominator | 1 |
| Denominator Exclusion | 0 |
| **Numerator** | **1** |
| Numerator Exclusion | 0 |
| MeasureObservation_1_1_1 | **12** |
| MeasureObservation_1_2_1 | **1** |
| **measureScore** | **0.0** |

The test case is named `NumerPass-RVwithDiureticsOrderAtAdmission`, confirming the
patient should be in the Numerator (count=1). However:
- The `measureScore` of `0.0` contradicts being a numerator pass
- `MeasureObservation` counts of 12 and 1 are inconsistent with a single qualifying
  encounter (Numerator=1)

### Suggested fix

- Review and correct MeasureObservation counts and measureScore for consistency
  with population counts
- Consider using UUIDs for inner bundle IDs for consistency with FHIR best practices
