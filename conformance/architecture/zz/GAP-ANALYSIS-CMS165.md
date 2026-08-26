# Gap Analysis: CMS165 CQL-to-SQL Translation

**Date:** 2026-02-27
**CQL Source:** `cql-measures/CMS165/CMS165FHIRControllingHighBP.cql`
**Generated SQL:** `cql-measures/CMS165/generated_sql.sql`
**Reference Spec:** `docs/cql-translator-technical-spec.md`

---

## Executive Summary

This document identifies CQL patterns used in CMS165 that are **not properly translated** to SQL, or where the translation deviates from the technical specification. Gaps are categorized by severity and impact.

**Overall Status:**
- ✅ Core patterns working (exists, LEFT JOINs, UNION)
- ⚠️ Several patterns have incomplete/incorrect translations
- ❌ Some patterns generate SQL that may not execute correctly

---

## Gap Categories

| Severity | Meaning |
|----------|---------|
| 🔴 **CRITICAL** | SQL will fail to execute or produce wrong results |
| 🟠 **HIGH** | SQL generates but logic is incorrect |
| 🟡 **MEDIUM** | SQL works but inefficient or verbose |
| 🔵 **LOW** | Minor deviation, cosmetic or documentation |

---

## Gap Analysis

### Gap 1: `.verified()` Fluent Function Not Applied

**Severity:** 🟠 HIGH

**CQL (lines 39-41):**
```cql
define "Essential Hypertension Diagnosis":
  ( ( [ConditionProblemsHealthConcerns: "Essential Hypertension"]
    union [ConditionEncounterDiagnosis: "Essential Hypertension"]
  ).verified ( ) ) Hypertension
```

**Expected SQL:**
```sql
"Essential Hypertension Diagnosis" AS (
  SELECT p.patient_id, ...
  FROM _patients AS p
  WHERE EXISTS (
    SELECT 1 FROM "Condition: Essential Hypertension" Hypertension
    WHERE Hypertension.patient_id = p.patient_id
      AND (Hypertension.verification_status IS NULL
           OR Hypertension.verification_status IN ('confirmed', 'unconfirmed', ...))
      AND intervalOverlaps(...)
  )
)
```

**Actual SQL (line 31-32):**
```sql
"Essential Hypertension Diagnosis" AS (
  SELECT p.patient_id, (SELECT * FROM "Condition: Essential Hypertension" AS Hypertension
    WHERE intervalOverlaps(...)) AS value FROM _patients AS p
)
```

**Problem:** The `.verified()` function should add verification status filtering but is not applied. The function body (from Status.cql) checks:
```cql
resource.verificationStatus is null
  or resource.verificationStatus in "Condition Verification Status"
```

**Impact:** Conditions without proper verification status may be incorrectly included.

**Root Cause:** AST-level function inlining for `.verified()` may not be properly substituting the function body into the WHERE clause.

---

### Gap 2: QICore Profile Types Not Differentiated

**Severity:** 🟡 MEDIUM

**CQL:**
```cql
[ConditionProblemsHealthConcerns: "Essential Hypertension"]
union [ConditionEncounterDiagnosis: "Essential Hypertension"]
```

**Expected SQL:**
```sql
-- Should have profile-based filtering
SELECT ... FROM resources WHERE resourceType = 'Condition'
  AND (fhirpath_text(resource, 'meta.profile') LIKE '%ConditionProblemsHealthConcerns%'
       OR fhirpath_text(resource, 'meta.profile') LIKE '%ConditionEncounterDiagnosis%')
  AND in_valueset(...)
```

**Actual SQL:**
```sql
SELECT ... FROM resources WHERE resourceType = 'Condition' AND in_valueset(...)
```

**Problem:** QICore profile types (`ConditionProblemsHealthConcerns`, `ConditionEncounterDiagnosis`) are not distinguished. Both resolve to the same `resourceType = 'Condition'` query.

**Impact:** May include conditions that don't match the intended QICore profile.

**Note:** This may be acceptable if the FHIR data doesn't use profiles, but violates strict CQL semantics.

---

### Gap 3: `without...such that` Pattern Translation Issues

**Severity:** 🔴 CRITICAL

**CQL (lines 108-115):**
```cql
define "Qualifying Blood Pressure Reading":
  ( ( ( [USCoreBloodPressureProfile] ).isObservationBP ( ) ) BloodPressure
    without ( ( [Encounter: "Encounter Inpatient"]
      union [Encounter: "Emergency Department Evaluation and Management Visit"]
    ).isEncounterPerformed ( ) ) DisqualifyingEncounter
    such that BloodPressure.effective.latest ( ) during day of DisqualifyingEncounter.period
```

**Expected SQL:**
```sql
SELECT BloodPressure.*
FROM "Observation" BloodPressure
WHERE BloodPressure.effective_date BETWEEN mp_start AND mp_end
  AND NOT EXISTS (
    SELECT 1 FROM "Encounter: Inpatient" DisqualifyingEncounter
    WHERE DisqualifyingEncounter.patient_id = BloodPressure.patient_id
      AND BloodPressure.effective_date BETWEEN
          DisqualifyingEncounter.period_start
          AND COALESCE(DisqualifyingEncounter.period_end, DisqualifyingEncounter.period_start)
  )
```

**Actual SQL (line 46-47):**
```sql
"Qualifying Blood Pressure Reading" AS (
  (SELECT * FROM "Observation" AS BloodPressure WHERE ...)
  UNION (SELECT * FROM "Observation" AS BloodPressure WHERE NOT array_contains(...) AND ...)
)
```

**Problem:** The `without...such that` pattern is not translated as a `NOT EXISTS` subquery. Instead, it appears to be split into two UNION branches with complex logic that may not correctly implement the exclusion semantics.

**Impact:** Blood pressure readings during disqualifying encounters may not be properly excluded.

---

### Gap 4: `.component` Filtering with `singleton from` Incorrect

**Severity:** 🔴 CRITICAL

**CQL (lines 91-95):**
```cql
singleton from(BPReading.component BPComponent
  where BPComponent.code ~ "Systolic blood pressure"
  return BPComponent.value as Quantity
)
```

**Expected SQL (per spec §6.3):**
```sql
fhirpath_number(BPReading.resource,
  'component.where(code.coding.exists(code = ''8480-6'')).valueQuantity.value'
) AS systolic_value
```

**Actual SQL (line 56, 62):**
```sql
CASE WHEN array_length(COALESCE(
  fhirpath_text(BPComponent, 'valueDateTime'),
  fhirpath_text(BPComponent, 'valuePeriod'),
  ... -- 15 more value type checks
), 1) = 1
THEN LIST_EXTRACT(COALESCE(...), 1)
ELSE NULL END
```

**Problems:**
1. `BPComponent` is not defined in the scope - should be iterating over `BPReading.component`
2. The code filter `where BPComponent.code ~ "Systolic blood pressure"` is not applied
3. Uses verbose COALESCE chain instead of targeted FHIRPath expression

**Impact:** Will likely fail or return incorrect values. The component filtering is not implemented.

---

### Gap 5: `First(... sort asc)` Not Using ROW_NUMBER()

**Severity:** 🟠 HIGH

**CQL (lines 88-96):**
```cql
define "Lowest Systolic Reading on Most Recent Blood Pressure Day":
  First("Qualifying Blood Pressure Reading" BPReading
    where BPReading.effective.latest() same day as "Most Recent Blood Pressure Day"
    return singleton from(BPReading.component BPComponent
      where BPComponent.code ~ "Systolic blood pressure"
      return BPComponent.value as Quantity
    )
    sort asc
  )
```

**Expected SQL (per spec §9.2):**
```sql
SELECT patient_id, systolic_value
FROM (
    SELECT t1.patient_id, t1.systolic_value,
           ROW_NUMBER() OVER (PARTITION BY t1.patient_id
                              ORDER BY t1.systolic_value ASC NULLS LAST) AS rn
    FROM "Qualifying Blood Pressure Reading" t1
    WHERE t1.effective_date = (SELECT ...)
) ranked
WHERE rn = 1
```

**Actual SQL (line 62):**
```sql
LIST_EXTRACT((SELECT ... FROM "Qualifying Blood Pressure Reading" AS BPReading ...), 1)
```

**Problems:**
1. Uses `LIST_EXTRACT(..., 1)` instead of `ROW_NUMBER()` with `WHERE rn = 1`
2. `sort asc` is not translated - just takes first element
3. Per spec §3.12, this should enforce cardinality check or at least warn

**Impact:** Returns arbitrary first element, not the actual minimum.

---

### Gap 6: `same day as` Not Casting to DATE

**Severity:** 🟠 HIGH

**CQL (line 90):**
```cql
where BPReading.effective.latest() same day as "Most Recent Blood Pressure Day"
```

**Expected SQL (per spec §3.3):**
```cql
CAST(BPReading.effective_date AS DATE) =
CAST((SELECT resource FROM "Most Recent Blood Pressure Day" LIMIT 1) AS DATE)
```

**Actual SQL (line 56):**
```sql
CAST((SELECT sub.resource FROM (...) ORDER BY effective_date DESC LIMIT 1) AS DATE) =
CAST((SELECT resource FROM "Most Recent Blood Pressure Day" LIMIT 1) AS DATE)
```

**Problem:** The comparison appears to be correctly cast to DATE, but the subquery structure is overly complex. The `"Most Recent Blood Pressure Day"` CTE returns a resource blob, not a date, which is then cast - this is incorrect.

**Expected:** The CTE should return a DATE value directly, not a resource that needs casting.

---

### Gap 7: `.getEncounter()` Reference Resolution Complex

**Severity:** 🟡 MEDIUM

**CQL (lines 121-124):**
```cql
define fluent function getEncounter(reference Reference):
  singleton from ( [Encounter] E
    where E.id = reference.reference.getId ( )
  )
```

**Generated SQL (line 47):**
```sql
CASE WHEN (SELECT COUNT(*) FROM "Encounter" AS E
           WHERE E.id = fhirpath_text(fhirpath_text(fhirpath_text(BloodPressure.resource, 'encounter'), 'reference'), 'id')) = 1
THEN (SELECT resource FROM "Encounter" AS E WHERE ... LIMIT 1)
ELSE NULL END
```

**Problems:**
1. Triple-nested `fhirpath_text` calls are inefficient
2. Per spec §3.12, should use `CASE WHEN COUNT(*) = 1 THEN ... ELSE NULL END` (correctly implemented)
3. The pattern is verbose - could be simplified with precomputed columns

**Impact:** Performance overhead, but functionally correct.

---

### Gap 8: Quantity Comparison Not Using UDF

**Severity:** 🟡 MEDIUM

**CQL (line 83):**
```cql
"Lowest Systolic Reading on Most Recent Blood Pressure Day" < 140 'mm[Hg]'
```

**Generated SQL (line 59):**
```sql
(SELECT resource FROM "Lowest Systolic Reading..." AS sub WHERE sub.patient_id = p.patient_id LIMIT 1)
< parse_quantity('{"value": 140.0, "unit": "mm[Hg]", ...}')
```

**Problem:** The comparison uses `<` directly with `parse_quantity()` result. Per spec §3.14, should use:
```sql
quantity_lt(systolic_value, parse_quantity('{"value": 140.0, ...}'))
```

**Impact:** May produce incorrect comparisons if units don't match.

---

### Gap 9: Date Arithmetic Not Using UDF

**Severity:** 🟡 MEDIUM

**CQL (line 42):**
```cql
where Hypertension.prevalenceInterval ( ) overlaps Interval[start of "Measurement Period", start of "Measurement Period" + 6 months )
```

**Generated SQL (line 32):**
```sql
dateAddQuantity(intervalStart(CAST(getvariable('measurement_period') AS VARCHAR)),
                '{"value": 6.0, "unit": "month", "system": "http://unitsofmeasure.org"}')
```

**Status:** This appears correct - using `dateAddQuantity` UDF as expected.

---

### Gap 10: `during day of Period` Not Correctly Translated

**Severity:** 🟠 HIGH

**CQL (line 113):**
```cql
such that BloodPressure.effective.latest ( ) during day of DisqualifyingEncounter.period
```

**Expected SQL (per spec §3.3):**
```sql
BloodPressure.effective_date BETWEEN DisqualifyingEncounter.period_start
    AND COALESCE(DisqualifyingEncounter.period_end, DisqualifyingEncounter.period_start)
```

**Actual SQL:** Pattern not clearly visible in the complex UNION structure.

**Problem:** The `during day of Period` pattern should expand to a date range check using precomputed `period_start` and `period_end` columns.

---

### Gap 11: `ends on or before` Not Using Interval Functions

**Severity:** 🟠 HIGH

**CQL (line 72):**
```cql
where ESRDProcedure.performed.toInterval ( ) ends on or before end of "Measurement Period"
```

**Generated SQL (line 29):**
```sql
intervalEnd(intervalFromBounds(fhirpath_text(fhirpath_text(ESRDProcedure.resource, 'performed'), 'start'),
                               fhirpath_text(fhirpath_text(ESRDProcedure.resource, 'performed'), 'end'),
                               true, false))
  <= intervalEnd(CAST(getvariable('measurement_period') AS VARCHAR))
```

**Problems:**
1. Double-nested `fhirpath_text(fhirpath_text(...))` is unusual
2. The pattern is verbose - should use precomputed `performed_start` and `performed_end` columns

**Expected:**
```sql
ESRDProcedure.performed_end <= intervalEnd(getvariable('measurement_period'))
```

---

### Gap 12: `starts on or before` Pattern

**Severity:** 🟠 HIGH

**CQL (line 76):**
```cql
where ESRDEncounter.period starts on or before end of "Measurement Period"
```

**Generated SQL (line 26):**
```sql
intervalStart(ESRDEncounter.period) <= intervalEnd(CAST(getvariable('measurement_period') AS VARCHAR))
```

**Status:** Appears correct, using `intervalStart` on precomputed period column.

---

### Gap 13: External Library CTE References

**Severity:** 🔵 LOW

**CQL (lines 35-36):**
```cql
and exists AdultOutpatientEncounters."Qualifying Encounters"
```

**Generated SQL (line 35):**
```sql
AND EXISTS (SELECT 1 FROM "AdultOutpatientEncounters.Qualifying Encounters" sub LIMIT 1)
```

**Status:** Correctly prefixed with library name.

---

### Gap 14: `Last(... sort asc)` Not Using ROW_NUMBER()

**Severity:** 🟠 HIGH

**CQL (lines 126-129):**
```cql
define "Most Recent Blood Pressure Day":
  Last("Blood Pressure Days" BPDays
    sort asc
  )
```

**Generated SQL (line 53):**
```sql
LIST_EXTRACT((SELECT * FROM "Blood Pressure Days" AS BPDays), -1)
```

**Problems:**
1. Uses `LIST_EXTRACT(..., -1)` to get last element
2. `sort asc` is not translated in the subquery
3. Should use `ROW_NUMBER() OVER (ORDER BY ... DESC) WHERE rn = 1` per spec §9

**Expected:**
```sql
SELECT patient_id, bp_day
FROM (
    SELECT patient_id, bp_day,
           ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY bp_day DESC) AS rn
    FROM "Blood Pressure Days"
) ranked
WHERE rn = 1
```

---

## AST and Transformation Analysis

### AST Node Types and Handling Locations

| Pattern | AST Node | Has Needed Data? | Handling Function | File Location |
|---------|----------|------------------|-------------------|---------------|
| `without...such that` | `WithClause` | ✅ YES | `_translate_with_clause()` | `queries.py:802-871` |
| `singleton from` with where | `SingletonExpression` | ⚠️ PARTIAL | `_apply_singleton_from()` | `expressions.py:2828-2904` |
| `.verified()` | `MethodInvocation` | ✅ YES | `_build_verified_ast()` | `fluent_functions.py:873-942` |
| `First/Last(... sort)` | `FirstExpression`/`LastExpression` + `SortClause` | ✅ YES | `_translate_first_expression()` | `expressions.py:2763-2795`, `aggregation.py:112-193` |
| `same day as` | `BinaryExpression` | ✅ YES | `_translate_same_operator()` | `expressions.py:3712-3773` |
| `during day of Period` | `BinaryExpression` | ✅ YES | `_translate_during_operator()` | `expressions.py:3775-3812` |

---

## Summary Table

| Gap | Pattern | Severity | AST Ready? | Fix Location |
|-----|---------|----------|------------|--------------|
| 1 | `.verified()` not applied | 🟠 HIGH | ✅ YES | Verify call path from Query |
| 2 | QICore profiles not differentiated | 🟡 MEDIUM | N/A | Design decision |
| 3 | `without...such that` incorrect | 🟢 IMPLEMENTED | ✅ YES | No fix needed |
| 4 | `singleton from` with component filter | 🔴 CRITICAL | ⚠️ PARTIAL | `expressions.py:2828-2904` |
| 5 | `First(... sort)` not using ROW_NUMBER | 🟢 IMPLEMENTED | ✅ YES | No fix needed |
| 6 | `same day as` CTE returns wrong type | 🟢 IMPLEMENTED | ✅ YES | No fix needed |
| 7 | `.getEncounter()` verbose | 🟡 MEDIUM | ✅ YES | Optimization |
| 8 | Quantity comparison without UDF | 🟡 MEDIUM | ✅ YES | `expressions.py` |
| 9 | Date arithmetic | 🟢 OK | ✅ YES | Working |
| 10 | `during day of Period` | 🟡 MEDIUM | ✅ YES | Add COALESCE |
| 11 | `ends on or before` verbose | 🟡 MEDIUM | ✅ YES | Optimization |
| 12 | `starts on or before` | 🟢 OK | ✅ YES | Working |
| 13 | External library refs | 🟢 OK | ✅ YES | Working |
| 14 | `Last(... sort)` not using ROW_NUMBER | 🟢 IMPLEMENTED | ✅ YES | No fix needed |

---

## Revised Gap Analysis (Based on Code Investigation)

After analyzing the codebase, several patterns marked as "gaps" are actually **already implemented**. The real issues are:

### ✅ Already Implemented (No Fix Needed)

| Pattern | Implementation | Location |
|---------|---------------|----------|
| `without...such that` | `NOT EXISTS` subquery generation | `queries.py:859-868` |
| `.verified()` | `list_filter()` with status check | `fluent_functions.py:920-942` |
| `First/Last(... sort)` | `ROW_NUMBER() OVER ... WHERE rn=1` | `aggregation.py:415-518` |
| `same day as` | `CAST(X AS DATE) = CAST(Y AS DATE)` | `expressions.py:3750-3754` |

### 🔴 Actually Needs Fix

#### Gap 4: `singleton from` with `where` filter on component array

**The Problem:**
The `SingletonExpression` AST only has a `source` attribute. When the source is a Query like:
```cql
singleton from(BPReading.component BPComponent
  where BPComponent.code ~ "Systolic blood pressure"
  return BPComponent.value as Quantity
)
```

The Query AST has the `where` clause, but the current translation doesn't generate proper FHIRPath `.where()` calls.

**AST Data Available:**
- `SingletonExpression.source` → contains the Query AST
- `Query.where` → contains the filter condition
- `Query.return_clause` → contains the value projection

**Current Behavior:**
```sql
CASE WHEN array_length(source, 1) = 1 THEN LIST_EXTRACT(source, 1) ELSE NULL END
```

**Expected Behavior:**
```sql
fhirpath_number(resource, 'component.where(code.coding.exists(code = ''8480-6'')).valueQuantity.value')
```

**Fix Location:** `expressions.py:2828-2904` — `_apply_singleton_from()`
- Detect if source is a Query with `where` clause on component array
- Generate FHIRPath `.where()` expression instead of SQL list operations

#### Gap 10: `during day of Period` NULL handling

**The Problem:**
Current implementation:
```sql
CAST(X AS DATE) BETWEEN CAST(intervalStart(Y) AS DATE) AND CAST(intervalEnd(Y) AS DATE)
```

If `period_end` is NULL (ongoing period), `intervalEnd()` returns NULL, and `BETWEEN ... AND NULL` may not work as expected.

**Expected:**
```sql
CAST(X AS DATE) BETWEEN CAST(intervalStart(Y) AS DATE)
  AND COALESCE(CAST(intervalEnd(Y) AS DATE), CAST(intervalStart(Y) AS DATE))
```

**Fix Location:** `expressions.py:3775-3812` — `_translate_during_operator()`
- Add COALESCE for NULL end date handling

#### Gap 1: `.verified()` Not Applied in Query Context

**The Problem:**
`.verified()` is implemented in `fluent_functions.py`, but when used in a Query context like:
```cql
([Condition: "Essential Hypertension"]).verified()
```

The function call may not be properly invoked because the Query translation path differs from the expression path.

**Investigation Needed:**
- Check if `MethodInvocation` for `.verified()` is being dispatched correctly when source is a `Retrieve`
- Verify the call path: `Query` → `expression` → `MethodInvocation` → `fluent_functions.py`

**Fix Location:** Likely in `queries.py` or `expressions.py` method invocation dispatch

---

## Recommended Fixes by Priority

### Priority 1: Critical (Must Fix)

1. **Gap 4: `singleton from` with component filtering**
   - **File:** `expressions.py:2828-2904` — `_apply_singleton_from()`
   - **Fix:** Detect Query with `where` clause on component arrays, generate FHIRPath `.where()` expression
   - **AST Data:** Available (`SingletonExpression.source` → Query → `where` clause)

### Priority 2: High (Should Fix)

2. **Gap 1: `.verified()` not applied in Query context**
   - **File:** `queries.py` or `expressions.py` (method invocation dispatch)
   - **Fix:** Ensure `MethodInvocation` for `.verified()` is dispatched when source is a Retrieve
   - **AST Data:** Available (`MethodInvocation` with method="verified")

3. **Gap 10: `during day of Period` NULL handling**
   - **File:** `expressions.py:3775-3812` — `_translate_during_operator()`
   - **Fix:** Add `COALESCE(intervalEnd(Y), intervalStart(Y))` for NULL end dates
   - **AST Data:** Available

### Priority 3: Medium (Nice to Have)

4. **Gap 8: Quantity comparison without UDF**
   - **File:** `expressions.py` (quantity comparison handling)
   - **Fix:** Use `quantity_lt/gt/eq` UDFs instead of direct `<`/`>` operators

5. **Gap 7 & 11: Verbose patterns (`.getEncounter()`, nested fhirpath)**
   - **Optimization:** Add precomputed columns for commonly accessed paths

6. **Gap 2: Profile filtering**
   - **Design decision:** Only needed if FHIR data uses QICore profiles

---

## Test Cases Needed

To validate fixes, add test cases for:

1. `without...such that` with temporal condition
2. `singleton from` with `where` filter on array elements
3. `First/Last` with explicit `sort` clause
4. `.verified()` function application
5. `same day as` comparison between dates
6. Quantity comparison with unit handling
7. `during day of Period` with interval bounds

---

---

## Additional Gaps Identified (2026-02-27)

### Gap 15: Choice Type Columns Not Using COALESCE

**Severity:** 🔴 CRITICAL

**Problem:**
Properties like `effective[x]` in FHIR have multiple possible types (effectiveDateTime, effectivePeriod). The current implementation creates separate columns with the **same alias**, which causes incorrect SQL:

**Expected SQL:**
```sql
COALESCE(
  fhirpath_date(r.resource, 'effectiveDateTime'),
  fhirpath_date(r.resource, 'effectivePeriod.start')
)::DATE AS effective_date
```

**Actual SQL (line 17):**
```sql
fhirpath_date(r.resource, 'effectiveDateTime') AS effective_date,
fhirpath_date(r.resource, 'effectivePeriod.start') AS effective_date
-- Two columns with same alias!
```

**Root Cause:**
`cte_builder.py:build_retrieve_cte()` lines 167-182 creates columns individually without grouping by logical column name. Should use `build_precomputed_column_sql()` from `types.py` which handles choice types.

**AST Data:** ✅ YES
- `CHOICE_TYPE_COLUMNS` in `types.py` maps column names to multiple FHIRPath alternatives
- Example: `{'effective_date': ['effectiveDateTime', 'effectivePeriod.start']}`

**Fix Location:**
- `cte_builder.py:build_retrieve_cte()` — group properties by column name
- Use `build_precomputed_column_sql()` for choice type COALESCE

---

### Gap 16: Missing CTEs from Dependent Libraries

**Severity:** 🔴 CRITICAL

**Problem:**
CMS165 uses `union` to combine multiple retrieve sources:
```cql
[ConditionProblemsHealthConcerns: "Pregnancy"]
union [ConditionEncounterDiagnosis: "Pregnancy"]
union [ConditionProblemsHealthConcerns: "End Stage Renal Disease"]
union [ConditionEncounterDiagnosis: "End Stage Renal Disease"]
-- ... more unions
```

Generated SQL is missing CTEs for:
- `Condition: End Stage Renal Disease`
- `Condition: Chronic Kidney Disease Stage 5`
- `Condition: Kidney Transplant Recipient`

**Root Cause:**
Investigation shows `find_all_placeholders()` DOES recurse into `SQLUnion`. The CTEs may be created but not appearing in final SQL. Need to verify:
1. `placeholder.py:resolve_placeholders()` handles union operands correctly
2. `retrieve_optimizer.py` includes all union sources in its analysis

**AST Data:** ✅ YES
- AST correctly represents unions with multiple retrieve sources
- Each retrieve has its own valueset reference

**Fix Location:**
- `placeholder.py` — verify placeholder resolution for SQLUnion
- `retrieve_optimizer.py` — verify all union sources generate CTEs

---

### Gap 17: Correlated Subqueries Instead of JOINs

**Severity:** 🟠 HIGH

**Problem:**
PATIENT_SCALAR definitions create correlated subqueries instead of LEFT JOINs:

**Current SQL (lines 26, 29, 32):**
```sql
"End Stage Renal Disease Encounter" AS (
  SELECT p.patient_id,
    (SELECT * FROM "Encounter: ESRD Monthly Outpatient Services" AS ESRDEncounter
     WHERE intervalStart(ESRDEncounter.period) <= ...) AS value
  FROM _patients AS p
)
```

**Expected SQL (per spec):**
```sql
"End Stage Renal Disease Encounter" AS (
  SELECT p.patient_id, ESRDEncounter.resource AS value
  FROM _patients AS p
  LEFT JOIN "Encounter: ESRD Monthly Outpatient Services" AS ESRDEncounter
    ON ESRDEncounter.patient_id = p.patient_id
    AND intervalStart(ESRDEncounter.period) <= ...
)
```

**Root Cause:**
`translator.py:_wrap_definition_cte()` lines 726-737 creates:
```python
if row_shape == RowShape.PATIENT_SCALAR:
    # Creates: SELECT p.patient_id, (expr) AS value FROM _patients p
```

Should use `_generate_joins_for_definition()` for JOIN-based approach.

**AST Data:** ✅ YES
- RowShape enum correctly identifies PATIENT_SCALAR
- Expression AST has all filter conditions needed for JOIN ON clause

**Fix Location:**
- `translator.py:_wrap_definition_cte()` lines 726-737
- Use LEFT JOIN pattern instead of scalar subquery

---

## Updated Summary Table

| Gap | Pattern | Severity | AST Ready? | Fix Location |
|-----|---------|----------|------------|--------------|
| 1 | `.verified()` not applied | 🟠 HIGH | ✅ YES | Query → method dispatch |
| 2 | QICore profiles | 🟡 MEDIUM | N/A | Simple mapping |
| 3 | `without...such that` | 🟢 IMPLEMENTED | ✅ YES | No fix needed |
| 4 | `singleton from` with where | 🔴 CRITICAL | ⚠️ PARTIAL | `expressions.py:2828-2904` |
| 5 | `First/Last(... sort)` | 🟢 IMPLEMENTED | ✅ YES | No fix needed |
| 6 | `same day as` | 🟢 IMPLEMENTED | ✅ YES | No fix needed |
| 7 | `.getEncounter()` verbose | 🟡 MEDIUM | ✅ YES | Optimization |
| 8 | Quantity comparison | 🟡 MEDIUM | ✅ YES | Use UDF |
| 9 | Date arithmetic | 🟢 OK | ✅ YES | Working |
| 10 | `during day of Period` | 🟡 MEDIUM | ✅ YES | Add COALESCE |
| 11 | `ends on or before` verbose | 🟡 MEDIUM | ✅ YES | Optimization |
| 12 | `starts on or before` | 🟢 OK | ✅ YES | Working |
| 13 | External library refs | 🟢 OK | ✅ YES | Working |
| 14 | `Last(... sort)` | 🟢 IMPLEMENTED | ✅ YES | No fix needed |
| **15** | **Choice Type COALESCE** | **🔴 CRITICAL** | **✅ YES** | **`cte_builder.py:167-182`** |
| **16** | **Missing CTEs from unions** | **🔴 CRITICAL** | **✅ YES** | **`placeholder.py` / `retrieve_optimizer.py`** |
| **17** | **Correlated subqueries** | **🟠 HIGH** | **✅ YES** | **`translator.py:726-737`** |

---

## Priority Fix Order (Revised)

### Tier 1: Critical (Blocks Correct Execution)

| Order | Gap | Issue | Fix Location |
|-------|-----|-------|--------------|
| 1 | 15 | Choice Type COALESCE | `cte_builder.py:build_retrieve_cte()` |
| 2 | 16 | Missing CTEs | `placeholder.py` / `retrieve_optimizer.py` |
| 3 | 4 | `singleton from` with where | `expressions.py:_apply_singleton_from()` |

### Tier 2: High (Produces Wrong Results)

| Order | Gap | Issue | Fix Location |
|-------|-----|-------|--------------|
| 4 | 17 | Correlated subqueries | `translator.py:_wrap_definition_cte()` |
| 5 | 1 | `.verified()` not applied | Query dispatch path |
| 6 | 10 | `during day of` NULL handling | `expressions.py:_translate_during_operator()` |

### Tier 3: Medium (Optimizations)

| Order | Gap | Issue | Fix Location |
|-------|-----|-------|--------------|
| 7 | 2 | Profile type mapping | Design decision |
| 8 | 8 | Quantity comparison UDF | `expressions.py` |
| 9 | 7, 11 | Verbose patterns | Precomputed columns |

---

## Discussion Points

### 1. Profile Handling (Gap 2)

**User's Point:** Profiles are just type annotations that map to base resource types. No complex filtering needed.

**Clarification:**
- `ConditionProblemsHealthConcerns` → `resourceType = 'Condition'`
- `ConditionEncounterDiagnosis` → `resourceType = 'Condition'`
- The specific logic (verification status, clinical status) is in `QICoreCommon.cql` fluent functions

**Recommendation:** Create a simple profile → resourceType mapping. No WHERE clause filtering by profile URL.

### 2. Choice Type Strategy (Gap 15)

**Current Code:**
```python
# cte_builder.py creates columns individually
for prop in properties:
    col_sql = f"fhirpath_date(r.resource, '{prop.fhirpath}') AS {prop.alias}"
```

**Fix:**
```python
# Group by logical column name, use COALESCE for choice types
from .types import CHOICE_TYPE_COLUMNS

for col_name, fhirpaths in CHOICE_TYPE_COLUMNS.items():
    if len(fhirpaths) > 1:
        coalesce_exprs = [f"fhirpath_date(r.resource, '{fp}')" for fp in fhirpaths]
        col_sql = f"COALESCE({', '.join(coalesce_exprs)})::DATE AS {col_name}"
```

### 3. JOIN vs Subquery Strategy (Gap 17)

**Why JOINs are better:**
1. Database optimizer can choose join order
2. Indexes can be used on both sides
3. Clearer execution plan
4. Easier to reason about

**Implementation:**
- Move filter conditions from scalar subquery to JOIN ON clause
- Use LEFT JOIN for PATIENT_SCALAR (may return NULL)
- Use INNER JOIN for PATIENT_MULTI_VALUE (must exist)

---

## References

- Technical Spec: `docs/cql-translator-technical-spec.md`
- Design Doc: `docs/DESIGN-CONTEXT-AWARE-TRANSLATION_V2.md`
- CQL Measure: `cql-measures/CMS165/CMS165FHIRControllingHighBP.cql`
- Generated SQL: `cql-measures/CMS165/generated_sql.sql`
- Types Module: `cql-py/src/cql_py/translator/types.py` (CHOICE_TYPE_COLUMNS)
- CTE Builder: `cql-py/src/cql_py/translator/cte_builder.py`
- Placeholder Resolution: `cql-py/src/cql_py/translator/placeholder.py`
