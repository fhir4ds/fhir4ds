# Feedback: Round 3 Verification of Issue Fixes

**Date:** 2026-02-28
**Audience:** Implementation team
**Input:** Regenerated `cql-measures/CMS165/generated_sql.sql`, diff of `cte_builder.py`, `expressions.py`, `fluent_functions.py`, `types.py`

---

## What Was Fixed (Good Work)

### ✅ P1.2 — External Library CTEs (THE BLOCKER)

All external library CTEs are now emitted. This is major progress.

| CTE | Status |
|---|---|
| `"AdultOutpatientEncounters.Qualifying Encounters"` | ✅ Present |
| `"Hospice.Has Hospice Services"` | ✅ Present |
| `"AIFrailLTCF.Is Age 66 or Older with Advanced Illness and Frailty"` | ✅ Present |
| `"AIFrailLTCF.Is Age 66 to 80 with Advanced Illness and Frailty..."` | ✅ Present |
| `"AIFrailLTCF.Has Criteria Indicating Frailty"` | ✅ Present |
| `"AIFrailLTCF.Has Advanced Illness in Year Before or During..."` | ✅ Present |
| `"AIFrailLTCF.Has Dementia Medications in Year Before or During..."` | ✅ Present |
| `"AIFrailLTCF.Is Age 66 or Older Living Long Term in a Nursing Home"` | ✅ Present |
| `"PalliativeCare.Has Palliative Care in the Measurement Period"` | ✅ Present |
| `"SDE.SDE Ethnicity"` / `"SDE.SDE Payer"` / `"SDE.SDE Race"` / `"SDE.SDE Sex"` | ✅ Present |

### ✅ Issue A — Profile Suffix Deduplication

The `PROFILES_REQUIRING_SUFFIX` allowlist approach is correct. `"Condition: Essential Hypertension"` is now one CTE instead of two. Profiles that don't change SQL (e.g., ConditionEncounterDiagnosis vs ConditionProblemsHealthConcerns) no longer create duplicates.

### ✅ Issue B — EXISTS Patient Correlation

All EXISTS subqueries in `"Initial Population"`, `"Denominator Exclusions"`, `"Numerator"` now have `WHERE sub.patient_id = p.patient_id`. `list_filter()` is completely gone from the output.

### ✅ Issue D — `verified()` No Longer Uses `list_filter`

The predicate now correctly includes all 4 status values:
`'confirmed', 'unconfirmed', 'provisional', 'differential'`
And NULL is handled (IS NULL OR IN (...)).

### ✅ Issue G — ROW_NUMBER Used for First/Last

The `_translate_first_last_with_window()` path is now being hit. Window function approach is correct in principle.

---

## Issues Still Broken

### ❌ Issue C — Demographics JOIN Missing from Library CTEs

The fix removed the _unconditional_ JOIN (good), but **library define CTEs that reference `pd.birth_date` have no JOIN at all**:

```sql
-- Line 134: AIFrailLTCF.Is Age 66 or Older...
SELECT p.patient_id, (date_diff('year', pd.birth_date, ...) >= 66 ...) AS value
FROM _patients p
-- MISSING: LEFT JOIN _patient_demographics AS pd ON pd.patient_id = p.patient_id
```

Lines 134, 138, and 154 all reference `pd.birth_date` without the JOIN. This will throw a "column not found" error at runtime. The scoping logic works for `Initial Population` (main library) but does not carry over to included library definitions.

**Fix:** The included library optimization pipeline must also track `needs_patient_demographics` and add the JOIN to those CTEs.

---

### ❌ Issue D (Partial) — `verified()` Applied to Wrong Expression

The predicate values are correct, but `verified()` is being called on **CTE table references** instead of **row resource columns**. In `"Essential Hypertension Diagnosis"`:

```sql
-- WRONG: ("Condition: Essential Hypertension") is a table reference, not a JSON value
COALESCE(
  fhirpath_text(("Condition: Essential Hypertension"), 'verificationStatus.coding.code'),
  fhirpath_text(("Condition: Essential Hypertension"), 'verificationStatus.coding.code')
) IS NULL OR ...

-- CORRECT: should use the row alias resource column
Hypertension.verification_status IS NULL
OR Hypertension.verification_status IN ('confirmed', 'unconfirmed', 'provisional', 'differential')
```

Two sub-problems:
1. The `resource_expr` passed to `_build_verified_ast()` is the CTE identifier, not the row alias's resource column. `_ensure_resource_column()` is returning the wrong thing.
2. The COALESCE has **the same argument twice** — `fhirpath_text(cte_ref, 'verificationStatus.coding.code')` appears as both COALESCE arguments. This is a bug in the retrieve CTE's `verification_status` column computation, not in `verified()`.

The `verification_status` precomputed column **exists** on the retrieve CTE (e.g., `"Condition: Essential Hypertension"`) — it should be referenced as `Hypertension.verification_status` in the define CTE's WHERE clause.

---

### ❌ Issue E — `prevalenceInterval()` Still Broken

`"Essential Hypertension Diagnosis"` still has:

```sql
COALESCE(fhirpath_date(Hypertension.resource, 'onsetDateTime'),
         fhirpath_date(Hypertension.resource, 'recordedDate'))
  < dateAddQuantity(intervalStart(...), ...)
AND COALESCE(NULL, '9999-12-31') >= intervalStart(...)  -- literal NULL!
```

Three problems:
1. **`Hypertension` alias is unresolved** — the CTE `FROM _patients AS p` has no `JOIN "Condition: Essential Hypertension" AS Hypertension`. The alias comes from the CQL query `[Condition: "Essential Hypertension"] Hypertension` but is never bound in SQL.
2. **`COALESCE(NULL, '9999-12-31')`** — the abatement_date is hard-coded NULL instead of referencing `Hypertension.abatement_date` from the precomputed column.
3. **FHIRPath UDFs still used** instead of the precomputed `onset_date` and `abatement_date` columns.

---

### ❌ Issue F — "End Stage Renal Disease Procedures" Still Garbled

Unchanged from last round. Still contains:
```sql
COALESCE(
  CASE WHEN fhirpath_text(("Procedure: Kidney Transplant"), 'status') = 'completed'
       THEN ("Procedure: Kidney Transplant") ELSE NULL END,
  ...
)
```
`("Procedure: Kidney Transplant")` is a table reference — cannot be COALESCE'd. `ESRDProcedure` alias is unresolved.

---

### ❌ Issue G (Partial) — Sort Key is NULL

ROW_NUMBER window functions are generated, but `ORDER BY NULL` is wrong:

```sql
ROW_NUMBER() OVER (PARTITION BY patient_ref ORDER BY NULL ASC NULLS LAST, ...)
```

The CQL sort expression (e.g., sort by effective date) is not being extracted and translated. `NULL` as a sort key makes the ordering non-deterministic — ties broken only by `$.id`, which is arbitrary. Affects `"Most Recent Blood Pressure Day"`, `"Lowest Diastolic Reading..."`, `"Lowest Systolic Reading..."`.

---

### ❌ Issues I/J — Procedure/Encounter Columns Not in Generated CTEs

The `period_start`, `period_end`, and `performed_end_date` were added to `CHOICE_TYPE_COLUMNS` in `types.py` but **do not appear in the generated retrieve CTEs**:

```sql
-- "Procedure: Kidney Transplant": still only has patient_id and resource
SELECT DISTINCT r.patient_ref AS patient_id, r.resource FROM resources r ...

-- "Encounter: ESRD Monthly Outpatient Services": period, not period_start/period_end
SELECT DISTINCT r.patient_ref AS patient_id, r.resource, fhirpath_date(r.resource, 'period') AS period ...
```

Adding columns to the constant is step 1 — the `build_retrieve_cte()` call chain must also be triggered for these resource types. Likely the CTE builder is only computing columns for profiles whose retrieves were processed by the optimization pipeline, and these specific resources are not going through that path.

---

## New Issues Introduced This Round

### New Issue K — SDE Library CTEs Have Unresolved Variable References

```sql
"SDE.SDE Ethnicity" AS (
  SELECT p.patient_id,
    struct_pack('codes', jsonConcat([fhirpath_text(E, 'ombCategory')], ...)) AS value
  FROM _patients p
)
```

`E` is not defined anywhere — it's a CQL alias for the ethnicity extension that was never bound in SQL. Same for `R` in `"SDE.SDE Race"`.

`"SDE.SDE Sex"` uses `CAST(getvariable('patient_resource') AS VARCHAR)` which is a per-patient variable not available in population SQL.

---

### New Issue L — Coverage CTE Named with AST Repr

```sql
"Coverage: BinaryExpression(operator='in', left=Identifier(name='type'), right=Identifier(name='Payer Type'))" AS (
```

The valueset expression for SDE Payer wasn't resolved to a string — the raw AST object was stringified instead. The CTE name should be something like `"Coverage: Payer Type"`.

---

### New Issue M — Library CTEs Are Syntactically Invalid SQL

Several library define CTEs contain `SELECT` statements joined by `OR` without EXISTS wrapping, which is not valid SQL:

```sql
-- From "AIFrailLTCF.Has Criteria Indicating Frailty":
(SELECT * FROM "DeviceRequest: Frailty Device" AS FrailtyDeviceOrder WHERE ... IS NOT NULL
 OR SELECT * FROM "ObservationScreeningAssessment: Medical equipment used" AS EquipmentUsed WHERE ...
 OR ...)
```

This is syntactically invalid. The pattern `SELECT * FROM table1 ... IS NOT NULL OR SELECT * FROM table2 ...` is not valid SQL. Each branch should be wrapped in `EXISTS(SELECT 1 FROM ... WHERE ...)` and the EXISTS results combined with OR.

The same pattern appears in `"Hospice.Has Hospice Services"` and `"PalliativeCare.Has Palliative Care in the Measurement Period"`.

Root cause: The library define translation is generating multi-branch OR conditions where each branch is a full subquery, but the EXISTS wrapping is being lost or incorrectly applied.

---

### New Issue N — Unresolved Query Aliases Throughout Library CTEs

Many library CTEs reference CQL query aliases (the `such that` binding variable) that are never bound in SQL:

| CTE | Unresolved Alias |
|---|---|
| `"Essential Hypertension Diagnosis"` | `Hypertension` |
| `"End Stage Renal Disease Procedures"` | `ESRDProcedure` |
| `"AdultOutpatientEncounters.Qualifying Encounters"` | `ValidEncounter` |
| `"AIFrailLTCF.Has Criteria Indicating Frailty"` | `FrailtyDiagnosis`, `LastHousingStatus` |
| `"AIFrailLTCF.Has Advanced Illness..."` | `AdvancedIllnessDiagnosis` |
| `"AIFrailLTCF.Is Age 66 or Older Living Long Term..."` | `LastHousingStatus` |

In each case the CQL expression had a `from ... Q such that ...` pattern, and the alias `Q` should become the row variable in a JOIN or correlated subquery. Instead the alias appears bare in the generated SQL.

---

## Test Failures (3 tests broken by this round's changes)

```
FAILED tests/unit/test_choice_type_columns.py::TestChoiceTypeColumnsConstant::test_has_all_required_columns
FAILED tests/unit/test_union_profile_urls.py::TestUnionWithProfiles::test_union_with_different_profiles_same_valueset
FAILED tests/unit/test_union_profile_urls.py::TestUnionWithProfiles::test_pregnancy_or_renal_diagnosis_pattern
```

### Fix 1: `test_choice_type_columns.py` line 32-47

Add the 3 new columns to the expected set:
```python
expected_columns = {
    "effective_date", "effective_datetime",
    "onset_date", "abatement_date", "recorded_date",
    "performed_date", "performed_end_date",   # ← add performed_end_date
    "authored_date", "status", "verification_status",
    "value_quantity", "value_code",
    "systolic_value", "diastolic_value",
    "period_start", "period_end",             # ← add period_start, period_end
}
```

### Fix 2: `test_union_profile_urls.py` lines 47-48 and 86-88

These tests assert the OLD behavior (profile suffixes). Update to match the new behavior (deduplication):

- `test_union_with_different_profiles_same_valueset`: change assertion to `assert len(condition_ctes) == 1` (one CTE, not two, since both profiles map to same FHIR Condition with same SQL)
- `test_pregnancy_or_renal_diagnosis_pattern`: remove assertions for `(problems)` and `(encounter)` suffixes; assert 3 CTEs instead of 6 (one per valueset, no profile suffix)

---

## Priority Order for Next Round

1. **Fix test failures** — Update 2 test files to match current behavior (mechanical, 30 min)
2. **Fix Issue M (syntactically invalid SQL)** — The OR-joined bare SELECT statements in Hospice, AIFrailLTCF, PalliativeCare CTEs crash immediately. Root cause: the multi-branch OR logic from included libraries must wrap each source in `EXISTS(SELECT 1 FROM ...)`.
3. **Fix Issue N (unresolved query aliases)** — CQL `from ... Q where/such that ...` patterns must produce SQL JOINs with the alias bound. This is the same root cause as Issue E and F.
4. **Fix Issue C (demographics JOIN in library CTEs)** — Add `LEFT JOIN _patient_demographics AS pd` to AIFrailLTCF age CTEs.
5. **Fix Issue K/L (SDE CTEs)** — SDE defines need proper patient extension lookup via FHIRPath, not unresolved aliases.
6. **Fix Issue G (sort key NULL)** — Extract and translate the CQL sort expression for ROW_NUMBER ORDER BY.
