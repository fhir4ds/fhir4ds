# SQL Optimization Plan V2

**Created:** 2026-02-23
**Status:** Draft for Review
**Priority:** High

---

## Context

The current CMS165 SQL is ~110K characters and hangs on execution. This plan addresses the root causes identified by the architect review.

---

## Agreed Priorities

| Priority | Change | Impact |
|----------|--------|--------|
| **P1** | Convert scalar subqueries to JOINs | 10-100x speedup + correctness |
| **P2** | Pre-compute fhirpath chains in CTEs | 17x fewer function calls |
| **P3** | ROW_NUMBER() for latest/first | Fixes correctness bug |
| **P4** | US-Core Profile mapping | Fixes resource resolution |

---

## CTE Structure Design

### Tier 1: ValueSet CTEs

Named by valueset alias (from CQL):
```sql
"vs_Essential Hypertension" AS (
    SELECT DISTINCT r.patient_ref, r.resource
    FROM resources r
    WHERE r.resourceType = 'Condition'
      AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/2.16.840.1.113883.3.464.1003.104.12.1011')
)
```

**Naming convention**: `vs_{valueset alias}` where alias is the quoted name from CQL

### Tier 2: Retrieval CTEs

Named `{resourceType/Profile}: {valueset alias}`:
```sql
"Condition: Essential Hypertension" AS (
    SELECT
        r.patient_ref,
        r.resource,
        -- Pre-computed columns (P2)
        fhirpath_choice(r.resource, 'onset') AS onset_date,
        fhirpath_text(r.resource, 'verificationStatus.coding.code') AS status
    FROM "vs_Essential Hypertension" r
)
```

**Naming convention**: `{resourceType}: {valueset alias}` for standard resources, or `{Profile}: {valueset alias}` for profile-based retrievals

---

## Implementation Tasks

### Phase 1: US-Core Profile Mapping (P4)

**Files to modify**: `cql-py/src/cql_py/translator/patterns/retrieve.py`

**Task**: Map US-Core profiles to FHIR resource types

```python
US_CORE_PROFILE_MAP = {
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient": "Patient",
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-condition": "Condition",
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation": "Observation",
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-blood-pressure": "Observation",
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-encounter": "Encounter",
    "http://hl7.org/fhir/us/core/StructureDefinition/us-core-procedure": "Procedure",
    "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-condition-encounter-diagnosis": "Condition",
    "http://hl7.org/fhir/us/qicore/StructureDefinition/qicore-observation": "Observation",
    # ... more mappings
}
```

**Logic**:
1. Extract `meta.profile` array from resource
2. Match against known profile URLs
3. Fall back to `resourceType` column if no match

---

### Phase 2: ValueSet CTE Generation (Tier 1)

**Files to modify**: `cql-py/src/cql_py/translator/translator.py`

**Task**: Generate ValueSet CTEs before definition CTEs

**Location**: `translate_library_to_population_sql()` method

**Logic**:
1. Collect all unique valueset references during translation
2. For each valueset, generate a Tier 1 CTE
3. Name CTE by valueset alias (quoted name from CQL)
4. Include patient_ref for correlation

**Generated SQL**:
```sql
WITH
  -- Tier 1: ValueSet CTEs
  "vs_Essential Hypertension" AS (
    SELECT DISTINCT r.patient_ref, r.resource
    FROM resources r
    WHERE r.resourceType = 'Condition'
      AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/...')
  ),
  "vs_Office Visit" AS (
    SELECT DISTINCT r.patient_ref, r.resource
    FROM resources r
    WHERE r.resourceType = 'Encounter'
      AND in_valueset(r.resource, 'type', 'http://cts.nlm.nih.gov/fhir/ValueSet/...')
  ),
  -- ... more valueset CTEs
```

---

### Phase 3: Pre-compute fhirpath Chains (P2)

**Files to modify**: `cql-py/src/cql_py/translator/translator.py`

**Task**: Pre-compute commonly used fhirpath chains as CTE columns

**Approach**: Inline in CTE definition (not a UDF)

**Pattern to detect**:
```sql
COALESCE(
    fhirpath_text(resource, 'effectiveDateTime'),
    fhirpath_text(resource, 'effectivePeriod'),
    fhirpath_text(resource, 'effectiveTiming'),
    ... -- 15+ more
)
```

**Generated SQL**:
```sql
"Observation: BP Readings" AS (
    SELECT
        r.patient_ref,
        r.resource,
        -- Pre-computed once
        COALESCE(
            fhirpath_text(r.resource, 'effectiveDateTime'),
            fhirpath_text(r.resource, 'effectivePeriod.start'),
            fhirpath_text(r.resource, 'effectiveTiming')
        ) AS effective_date,
        fhirpath_text(r.resource, 'status') AS status,
        fhirpath_text(r.resource, 'valueQuantity.value') AS value
    FROM "vs_BP Readings" r
)
```

**Columns to pre-compute**:
| Choice Type Field | Alternatives |
|-------------------|--------------|
| effective | effectiveDateTime, effectivePeriod.start, effectiveTiming, effectiveInstant |
| onset | onsetDateTime, onsetPeriod.start, onsetTiming |
| abatement | abatementDateTime, abatementPeriod.start |
| value | valueQuantity, valueCodeableConcept, valueString |

---

### Phase 4: Convert Scalar Subqueries to JOINs (P1)

**Files to modify**: `cql-py/src/cql_py/translator/translator.py`

**Task**: Replace correlated scalar subqueries with JOINs in final SELECT

**Current (bad)**:
```sql
SELECT p.patient_id,
       fhirpath_text((SELECT sq.resource FROM _sq_14 sq WHERE sq.patient_ref = p.patient_id), 'status')
FROM patients p
```

**Target (good)**:
```sql
SELECT p.patient_id, fhirpath_text(bp.resource, 'status')
FROM patients p
LEFT JOIN "Observation: BP Readings" bp ON bp.patient_ref = p.patient_id
```

**Changes**:
1. Build LEFT JOINs for each definition CTE in final SELECT
2. Remove scalar subquery references
3. Use pre-computed columns where available

---

### Phase 5: Window Functions for Latest/First (P3)

**Files to modify**: `cql-py/src/cql_py/translator/patterns/aggregation.py`

**Task**: Replace ORDER BY LIMIT 1 with ROW_NUMBER()

**Current (broken)**:
```sql
SELECT resource FROM (
    SELECT resource FROM observations
    ORDER BY effective_date DESC
    LIMIT 1  -- Returns ONE row total, not per patient!
)
```

**Target (fixed)**:
```sql
SELECT patient_ref, resource
FROM (
    SELECT
        patient_ref,
        resource,
        ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY effective_date DESC) AS rn
    FROM "Observation: BP Readings"
) ranked
WHERE rn = 1
```

**Implementation**:
1. Detect First/Last patterns in CQL
2. Generate window function CTE instead of ORDER BY LIMIT 1
3. Partition by patient_ref

---

## Final SQL Structure

```sql
WITH
  -- ===== TIER 1: ValueSet CTEs =====
  "vs_Essential Hypertension" AS (
    SELECT DISTINCT r.patient_ref, r.resource
    FROM resources r
    WHERE r.resourceType = 'Condition'
      AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/...')
  ),

  "vs_BP Readings" AS (
    SELECT DISTINCT r.patient_ref, r.resource
    FROM resources r
    WHERE r.resourceType = 'Observation'
      AND in_valueset(r.resource, 'code', 'http://cts.nlm.nih.gov/fhir/ValueSet/...')
  ),

  -- ===== TIER 2: Retrieval CTEs (with pre-computed columns) =====
  "Condition: Essential Hypertension" AS (
    SELECT
      r.patient_ref,
      r.resource,
      COALESCE(
        fhirpath_text(r.resource, 'onsetDateTime'),
        fhirpath_text(r.resource, 'onsetPeriod.start')
      ) AS onset_date,
      fhirpath_text(r.resource, 'verificationStatus.coding.code') AS status
    FROM "vs_Essential Hypertension" r
  ),

  "Observation: BP Readings" AS (
    SELECT
      r.patient_ref,
      r.resource,
      COALESCE(
        fhirpath_text(r.resource, 'effectiveDateTime'),
        fhirpath_text(r.resource, 'effectivePeriod.start')
      ) AS effective_date,
      fhirpath_text(r.resource, 'status') AS status
    FROM "vs_BP Readings" r
    WHERE fhirpath_text(r.resource, 'status') IN ('final', 'amended', 'corrected')
  ),

  -- Window function for "most recent"
  "Observation: Most Recent BP" AS (
    SELECT patient_ref, resource, effective_date
    FROM (
      SELECT *,
             ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY effective_date DESC) AS rn
      FROM "Observation: BP Readings"
    ) ranked
    WHERE rn = 1
  ),

  -- ===== TIER 3: Definition CTEs =====
  "Initial Population" AS (
    SELECT DISTINCT p.patient_ref AS patient_id
    FROM resources p
    INNER JOIN "Condition: Essential Hypertension" h ON h.patient_ref = p.patient_ref
    LEFT JOIN "Observation: Most Recent BP" bp ON bp.patient_ref = p.patient_ref
    WHERE p.resourceType = 'Patient'
      AND h.onset_date <= '2024-12-31'
      AND AgeInYearsAt(p.resource, '2024-12-31') BETWEEN 18 AND 85
  ),

  -- ===== FINAL SELECT: JOINs only (no scalar subqueries) =====
  patients AS (
    SELECT DISTINCT patient_ref AS patient_id
    FROM resources
    WHERE patient_ref IS NOT NULL
  )

SELECT
  p.patient_id,
  CASE WHEN "Initial Population".patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS "Initial Population",
  CASE WHEN "Denominator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS "Denominator",
  CASE WHEN "Numerator".patient_id IS NOT NULL THEN TRUE ELSE FALSE END AS "Numerator"
FROM patients p
LEFT JOIN "Initial Population" ON p.patient_id = "Initial Population".patient_id
LEFT JOIN "Denominator" ON p.patient_id = "Denominator".patient_id
LEFT JOIN "Numerator" ON p.patient_id = "Numerator".patient_id
ORDER BY p.patient_id
```

---

## Expected Size Reduction

| Metric | Current | Target |
|--------|---------|--------|
| SQL Size | ~110K chars | ~15-20K chars |
| fhirpath calls per row | 50+ | 3-5 |
| Subquery depth | 5-7 levels | 2 levels |
| CTEs | 40+ | 25-30 |

---

## Testing Strategy

1. **Unit tests**: Test each phase independently
2. **Integration test**: Run CMS165 SQL and verify it executes
3. **Correctness test**: Compare results with expected values

---

## Risks

| Risk | Mitigation |
|------|------------|
| Profile mapping incomplete | Start with common profiles, add more as needed |
| Window function performance | Add WHERE filter before window function |
| JOIN cardinality | Use DISTINCT where appropriate |

---

## Questions for Review

1. Should we prefix ValueSet CTEs with `vs_` or just use the quoted name directly?
2. For profile mapping, should we check `meta.profile` first or `resourceType` first?
3. Should we create separate CTEs for "most recent" patterns or inline the window function?

---

## Approval

- [ ] Priority order confirmed
- [ ] CTE naming convention confirmed
- [ ] Profile mapping approach confirmed
- [ ] Ready to implement
