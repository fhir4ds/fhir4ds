# Gap Analysis: Generated SQL vs Manual SQL (CMS165)

**Date:** 2026-02-28
**Scope:** Compare `cql-measures/CMS165/generated_sql.sql` against `cql-measures/CMS165/manual_sql.sql` and the design spec in `docs/DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md`.

---

## Summary

The generated SQL has **significant structural and semantic gaps** compared to the manual reference. The translator produces output that looks like CQL-to-SQL but falls short on: (1) external library CTE resolution, (2) precomputed column reuse, (3) correlated-subquery-to-JOIN conversion, (4) status/fluent function application, (5) complex expression translation (BP components, interval overlap, etc.), and (6) several CQL patterns that are untranslated or broken. Below is a prioritized catalog of every gap found.

---

## 1. Missing CTEs (Referenced but Not Defined)

The generated SQL references these CTEs in `EXISTS` or `SELECT` clauses, but they **do not appear in the WITH block**:

| Missing CTE | Referenced From |
|---|---|
| `"AdultOutpatientEncounters.Qualifying Encounters"` | `"Initial Population"` |
| `"Hospice.Has Hospice Services"` | `"Denominator Exclusions"` |
| `"AIFrailLTCF.Is Age 66 to 80 with Advanced Illness and Frailty or Is Age 81 or Older with Frailty"` | `"Denominator Exclusions"` |
| `"AIFrailLTCF.Is Age 66 or Older Living Long Term in a Nursing Home"` | `"Denominator Exclusions"` |
| `"PalliativeCare.Has Palliative Care in the Measurement Period"` | `"Denominator Exclusions"` |
| `"SDE.SDE Ethnicity"`, `"SDE.SDE Payer"`, `"SDE.SDE Race"`, `"SDE.SDE Sex"` | SDE defines |

**Root cause:** The translator does not inline/expand external library definitions. It emits a string reference (`"Library.DefineName"`) but never generates the CTE body. The manual SQL expands each library define into its own full CTE (e.g., `"Has Hospice Services"` with 6 UNION ALL branches, `"Has Criteria Indicating Frailty"` with 5 branches, etc.).

**Impact:** The query will fail at runtime — DuckDB will report "table not found" for every missing CTE.

**Fix priority:** **P0 — Blocking.** Without this, no measure can execute.

---

## 2. Missing Retrieve CTEs for External Libraries

The generated SQL only emits retrieves for resources directly referenced in the main CQL file. The manual SQL has ~30 retrieve CTEs covering all external libraries:

| Library | Missing Retrieve CTEs |
|---|---|
| AdultOutpatientEncounters | Office Visit, Annual Wellness Visit, Preventive Care Established, Preventive Care Initial, Home Healthcare Services, Virtual Encounter, Telephone Visits |
| Hospice | Hospice Encounter, Hospice Diagnosis, Hospice Care Ambulatory (ServiceRequest + Procedure), Hospice care MDS (Observation 45755-6) |
| PalliativeCare | Palliative Care Encounter, Palliative Care Diagnosis, Palliative Care Intervention, FACIT-Pal (Observation 71007-9) |
| AIFrailLTCF | Advanced Illness, Frailty Diagnosis, Frailty Encounter, Frailty Device (DeviceRequest), Medical equipment used (Observation 98181-1), Frailty Symptom, Housing Status (Observation 71802-3), Dementia Medications (MedicationRequest) |
| SDE | Coverage: Payer Type |

**Root cause:** Same as #1 — external library retrieves are never scanned or emitted.

**Fix priority:** **P0** — Required by the missing define CTEs above.

---

## 3. Precomputed Columns Not Used in Define CTEs

The generated SQL does precompute some columns in retrieve CTEs (e.g., `onset_date`, `abatement_date`, `period`), but the define CTEs **do not reference them**. Instead, they call FHIRPath UDFs redundantly on `resource`.

### Example: "Essential Hypertension Diagnosis"

**Generated (wrong):**
```sql
SELECT p.patient_id, (
  SELECT * FROM "Condition: Essential Hypertension" AS Hypertension
  WHERE intervalOverlaps(
    CASE WHEN fhirpath_text(Hypertension.resource, 'abatementDateTime') IS NOT NULL
      THEN intervalFromBounds(
        COALESCE(fhirpath_date(Hypertension.resource, 'onsetDateTime'), Hypertension.recorded_date),
        fhirpath_date(Hypertension.resource, 'abatementDateTime'), ...)
    ...
  )
) AS value FROM _patients AS p
```

**Manual (correct):**
```sql
SELECT t1.patient_id, t1.resource
FROM "Condition: Essential Hypertension" t1
WHERE (t1.verification_status IS NULL OR t1.verification_status IN (...))
  AND t1.onset_date < DATE '{mp_start}' + INTERVAL 6 MONTHS
  AND COALESCE(t1.abatement_date, DATE '9999-12-31') >= DATE '{mp_start}'
```

The manual version uses `t1.onset_date`, `t1.abatement_date`, `t1.verification_status` — all precomputed in the retrieve CTE. The generated version re-invokes `fhirpath_date()` and `fhirpath_text()` on every row.

**Root cause:** Phase 3 placeholder resolution is not replacing FHIRPath calls with column references from the column registry.

**Fix priority:** **P1 — Performance.** The SQL is O(n) slower due to redundant Python UDF calls.

---

## 4. Correlated Subqueries Instead of JOINs

The design spec explicitly targets replacing correlated subqueries with JOINs, but the generated SQL is dominated by them.

### 4.1 Scalar subquery wrapping for resource-row defines

Every resource-row define (e.g., `"Essential Hypertension Diagnosis"`, `"Pregnancy or Renal Diagnosis"`, `"End Stage Renal Disease Procedures"`) is wrapped as:

```sql
SELECT p.patient_id, (SELECT * FROM "CTE" AS alias WHERE ...) AS value
FROM _patients AS p
```

This is a **correlated scalar subquery** that:
- Executes once per patient row
- Cannot return multiple columns
- Produces wrong results if >1 row matches (SQL error or silently drops rows)

**Manual equivalent:** Direct `FROM "CTE" WHERE ...` with no patient-scoped wrapper, or `EXISTS` subquery where appropriate.

### 4.2 EXISTS without patient correlation

```sql
-- Generated (wrong): no patient_id correlation!
WHERE EXISTS (SELECT 1 FROM "Essential Hypertension Diagnosis" sub LIMIT 1)
```

```sql
-- Manual (correct): correlated to current patient
WHERE EXISTS (SELECT 1 FROM "Essential Hypertension Diagnosis" t2 WHERE t2.patient_id = t1.patient_id)
```

The generated `EXISTS` checks if **any** row exists globally, not per-patient. This means if any single patient has hypertension, all patients pass the filter.

**Fix priority:** **P0 — Correctness.** Results are wrong.

### 4.3 Denominator uses both LEFT JOIN and EXISTS

```sql
-- Generated
LEFT JOIN "Initial Population" AS j1 ON j1.patient_id = p.patient_id
WHERE EXISTS (SELECT 1 FROM "Initial Population" AS sub WHERE sub.patient_id = p.patient_id LIMIT 1)
```

The JOIN is redundant with the EXISTS. Per the design spec, for PATIENT_SCALAR boolean defines, use `LEFT JOIN ... IS NOT NULL` — no need for EXISTS.

**Fix priority:** P2

---

## 5. Status Function Application Missing

CQL uses fluent functions from `Status.cql` to filter resources by status. The generated SQL does not apply these filters.

| CQL Fluent Function | Expected Filter | Generated |
|---|---|---|
| `.verified()` | `verification_status IS NULL OR IN ('confirmed','unconfirmed','provisional','differential')` | Not applied |
| `.isObservationBP()` | `status IN ('final','amended','corrected')` | Not applied |
| `.isProcedurePerformed()` | `status = 'completed'` | Not applied |
| `.isEncounterPerformed()` | `status = 'finished'` | Not applied |
| `.isInterventionOrder()` | `status IN ('active','completed') AND intent IN (5 codes)` | Not applied |
| `.isAssessmentPerformed()` | `status IN ('final','amended','corrected')` | Not applied |
| `.isSymptom()` | `status IN ('preliminary','final','amended','corrected')` | Not applied |
| `.isDeviceOrderPersonalUseDevices()` | `status IN ('active','completed') AND intent IN (5 codes)` | Not applied |
| `.isMedicationActive()` | `status = 'active' AND intent IN (5 codes)` | Not applied |

**Root cause:** Fluent functions from included libraries are not being resolved and translated.

**Fix priority:** **P0 — Correctness.** Without status filters, the query includes cancelled, entered-in-error, and other invalid resources.

---

## 6. Interval/Temporal Expression Gaps

### 6.1 `prevalenceInterval()` translation broken

The generated SQL calls `intervalOverlaps()` with inline `fhirpath_date()` + `intervalFromBounds()` calls. The manual SQL decomposes this to simple date comparisons using precomputed columns:

```sql
-- Manual: prevalenceInterval overlaps [start, start+6months)
AND t1.onset_date < DATE '{mp_start}' + INTERVAL 6 MONTHS
AND COALESCE(t1.abatement_date, DATE '9999-12-31') >= DATE '{mp_start}'
```

The generated version uses CQL UDF calls (`intervalFromBounds`, `intervalOverlaps`) which are slower and harder to debug.

### 6.2 "during day of" precision not applied

The CQL `during day of "Measurement Period"` means both start and end of the period must be checked at DATE precision. The generated SQL uses `BETWEEN ... CAST(intervalStart(...) AS DATE) AND CAST(intervalEnd(...) AS DATE)` which is approximately right but doesn't match the manual pattern of checking `>= mp_start AND < mp_end`.

### 6.3 "on or before end of" incorrect boundary

`mp_end` is exclusive (open interval). The generated SQL uses `<= intervalEnd(...)` which may include the wrong boundary. The manual uses `< DATE '{mp_end}'`.

### 6.4 `effective.latest()` over-complicated

The generated SQL creates a nested subquery to find the latest effective date:
```sql
(SELECT sub.resource FROM (SELECT r.resource, ... ORDER BY effective_date DESC LIMIT 1))
```

The manual SQL simply uses the precomputed `effective_date` column from the retrieve CTE.

**Fix priority:** P1 — Correctness and performance.

---

## 7. Blood Pressure Component Translation

### 7.1 Component lookup by LOINC code

**Generated (wrong):** Uses a massive COALESCE across all possible value[x] types:
```sql
COALESCE(fhirpath_text(BPComponent, 'valueDateTime'), fhirpath_text(BPComponent, 'valuePeriod'),
  fhirpath_text(BPComponent, 'valueTiming'), ... 17 more ...)
```

**Manual (correct):** Uses FHIRPath `where()` predicate in retrieve CTE:
```sql
fhirpath_number(t1.resource, 'component.where(code.coding.exists(code = ''8480-6'')).valueQuantity.value') AS systolic_value
```

The generated version doesn't filter by LOINC code at all — it doesn't distinguish systolic from diastolic.

### 7.2 `singleton from` translation

The generated SQL uses `array_length(...) = 1` check with massive COALESCE, which is semantically wrong and syntactically broken. The manual SQL avoids `singleton from` entirely by precomputing the component values.

**Fix priority:** **P0 — Correctness.** BP numerator logic is completely broken.

---

## 8. `_patient_demographics` CTE Missing

The generated SQL has no `_patient_demographics` CTE. The `AgeInYearsAt` call uses:
```sql
AgeInYearsAt(CAST(getvariable('patient_resource') AS VARCHAR), intervalEnd(...))
```

This is a single-patient UDF call that requires `patient_resource` to be set as a DuckDB variable. In population mode, this doesn't work — you need a per-patient age calculated from the Patient resource's birthDate.

The manual SQL uses a dedicated CTE:
```sql
_patient_demographics AS (
  SELECT patient_id, birth_date,
    (EXTRACT(YEAR FROM ...) - EXTRACT(YEAR FROM birth_date) - CASE ... END)::INTEGER AS age_at_mp_end
  FROM _patients INNER JOIN resources ON ...
)
```

**Fix priority:** **P0 — Correctness.** Age filtering is wrong in population mode.

---

## 9. `_encounter_index` Performance CTE Missing

The manual SQL creates an `_encounter_index` CTE to precompute encounter ID and class code using native `fhirpath_text()` calls once, rather than evaluating the UDF inside every JOIN condition. The generated SQL has no equivalent.

**Fix priority:** P2 — Performance optimization.

---

## 10. Union Semantics

### 10.1 Missing UNION for multi-valueset retrieves

CQL `"Pregnancy or Renal Diagnosis"` unions 8 condition retrieves. The generated SQL only references `"Condition: Pregnancy"` — missing the other 6 condition valuesets entirely.

### 10.2 UNION vs UNION ALL

The manual SQL uses `UNION ALL` for patient_id-only defines (provably disjoint resource types) and `UNION` where deduplication is needed. The generated SQL uses plain `UNION` everywhere but doesn't emit the multi-branch structure at all.

**Fix priority:** P0 — Correctness (missing branches), P2 — Performance (UNION vs UNION ALL).

---

## 11. `without ... such that` Translation

The CQL `without DisqualifyingEncounter such that ...` anti-join is critical for "Qualifying Blood Pressure Reading". The generated SQL attempts this but produces broken output with nested subqueries on `fhirpath_text(BloodPressure.resource, 'effective')` that don't make sense as a FROM source.

The manual SQL uses clean `NOT EXISTS` with proper correlation:
```sql
AND NOT EXISTS (
  SELECT 1 FROM "Encounter: Encounter Inpatient" t2
  WHERE t2.patient_id = t1.patient_id
    AND t1.effective_date BETWEEN t2.period_start AND COALESCE(t2.period_end, t2.period_start)
)
```

**Fix priority:** P0 — Correctness.

---

## 12. `First()`/`Last()` with Sorting

### 12.1 `Last("Blood Pressure Days" sort asc)`

Generated: `LIST_EXTRACT((SELECT * ...), -1)` — uses LIST operations which are wrong and likely crash.

Manual: `MAX(t1.bp_date)` — simple aggregation for "last in ascending sort".

### 12.2 `First("Qualifying Blood Pressure Reading" ... sort asc)`

Generated: `LIST_EXTRACT((SELECT ...), 1)` — same LIST problem.

Manual: `ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY ... ASC NULLS LAST) WHERE rn = 1`

**Fix priority:** P0 — Correctness.

---

## 13. Measurement Period Handling

Generated: `CAST(getvariable('measurement_period') AS VARCHAR)` passed to UDFs like `intervalStart()`, `intervalEnd()`.

Manual: Template parameters `{mp_start}` and `{mp_end}` as DATE literals.

The generated approach works for single-patient evaluation but is: (a) harder to debug, (b) relies on UDFs for simple date access, (c) doesn't match the spec's template parameter approach.

**Fix priority:** P2 — Usability/consistency.

---

## 14. `getEncounter()` Fluent Function

The generated SQL has a complex inline `CASE WHEN (SELECT COUNT(*) ...) = 1 THEN ... ELSE NULL END` for `singleton from [Encounter] E where E.id = reference.getId()`. The manual SQL uses the precomputed `_encounter_index` CTE and a simple JOIN.

**Fix priority:** P1 — Performance + readability.

---

## 15. SDE Defines

Generated: `(SELECT * FROM "SDE.SDE Ethnicity") AS value` — references non-existent CTEs.

Manual: Direct FHIRPath extension calls on Patient resource:
```sql
fhirpath_text(t2.resource, 'extension(''http://hl7.org/.../us-core-ethnicity'').extension(''ombCategory'').valueCoding.code')
```

**Fix priority:** P1 — These are required for complete measure output.

---

## Prioritized Action Plan

### Phase 1: Make It Run (P0 — Correctness)

1. **External library expansion** — Resolve `include` libraries, emit their retrieve and define CTEs
2. **Patient-correlated EXISTS** — Add `WHERE sub.patient_id = p.patient_id` to all EXISTS subqueries
3. **Status function translation** — Translate `.verified()`, `.isObservationBP()`, etc. to WHERE clauses
4. **`_patient_demographics` CTE** — Generate birthday-aware age calculation for population mode
5. **Multi-valueset union defines** — Emit all branches for `"Pregnancy or Renal Diagnosis"`, `"End Stage Renal Disease Procedures"`, etc.
6. **BP component lookup** — Use FHIRPath `component.where(code.coding.exists(...))` in retrieve CTE
7. **`without...such that` anti-join** — Translate to `NOT EXISTS` with proper correlation
8. **`First()`/`Last()` with sorting** — Use `ROW_NUMBER()` window function, not `LIST_EXTRACT()`

### Phase 2: Make It Fast (P1 — Performance)

9. **Precomputed column reuse** — Phase 3 must replace FHIRPath calls with column references
10. **Correlated subquery → JOIN conversion** — Apply the design spec's shape-driven JOIN strategy
11. **Interval overlap decomposition** — Replace `intervalOverlaps()` UDF with simple date comparisons
12. **`_encounter_index` CTE** — Precompute encounter id+class for BP reading JOIN
13. **SDE translation** — Extension-based FHIRPath for ethnicity, race, sex

### Phase 3: Polish (P2 — Optimization)

14. **UNION ALL for disjoint sets** — Where resource types prove disjointness
15. **Measurement period as template params** — `{mp_start}`, `{mp_end}` instead of UDF calls
16. **Eliminate redundant JOINs** — e.g., Denominator's double reference to Initial Population
17. **`getvariable()` consolidation** — Single approach for parameter access

---

## Architecture Implementation Gaps

Beyond CMS165-specific issues, the following **design spec features are not yet implemented**:

| Spec Feature | Status |
|---|---|
| Three-phase pipeline (translate → build CTEs → resolve placeholders) | Partially — Phase 3 resolution doesn't replace property access |
| `RowShape` inference (PATIENT_SCALAR, RESOURCE_ROWS, PATIENT_MULTI_VALUE) | Unknown — output suggests shapes are not driving CTE wrapping |
| Shape-driven CTE wrapping | Not visible — all defines get `SELECT p.patient_id, (subquery) AS value` |
| `CTEReference` tracking with `ExprUsage` | Not visible — EXISTS vs SCALAR not distinguished |
| Cartesian fanout prevention | Not tested — no multi-row JOINs are generated |
| Column registry → property optimization | Not working — FHIRPath calls not replaced |
| Fresh `SQLQueryBuilder` per definition | Unknown |
| Topological sort | Working (dependency order looks correct) |
| `singleton from` with cardinality check | Wrong — uses `LIST_EXTRACT` |
| Temporal precision alignment | Partially — `CAST AS DATE` used in some places |
| NULL handling with `COALESCE` | Not visible |
