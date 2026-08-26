# Feedback: P1.2 External Library CTEs + Related Issues in Regenerated SQL

**Date:** 2026-02-28
**Audience:** Implementation team
**Input:** Regenerated `cql-measures/CMS165/generated_sql.sql`

---

## What Improved (Good Work)

1. **`_patient_demographics` CTE now emitted** (P1.3 done) — line 7-9
2. **Age calculation uses `date_diff('year', pd.birth_date, ...)`** — line 65
3. **Profile-differentiated retrieve CTEs** — e.g., `"Condition: Essential Hypertension (encounter)"` vs `"(problems)"` — lines 10-54
4. **BP profile columns precomputed** — `systolic_value`, `diastolic_value` with LOINC-code FHIRPath in `"Observation (us-core-blood-pressure)"` — line 17
5. **`verification_status` precomputed** in Condition retrieve CTEs — lines 11, 13, etc.
6. **Multi-valueset unions visible** — `"Pregnancy or Renal Diagnosis"` now references all 8 branches — line 71
7. **EXISTS subqueries no longer have LIMIT 1** (mostly) — lines 65, 74, 98
8. **Demographics JOIN added to all defines** — `LEFT JOIN _patient_demographics AS pd`

---

## P1.2: External Library CTEs Still Missing

> **✅ FIXED (2026-02-28)** — All 9 external library CTEs now appear in generated SQL.
>
> **Root causes fixed:**
> 1. **Parser: block comments before `library` keyword** — Parser now skips `LINE_COMMENT` and `BLOCK_COMMENT` tokens automatically via `_skip_comments()` in `current()`, `peek()`. This fixed `SupplementalDataElements` and `Status` library loading.
> 2. **Parser: `sort by expression asc/desc`** — `parse_sort_clause()` now accepts trailing `asc`/`desc` after the sort expression (CQL allows direction before OR after). This fixed `AdvancedIllnessandFrailty` library loading.
> 3. **Parser: keyword tokens as identifiers** — `_parse_identifier_name()` now accepts `DISPLAY`, `CALLED`, `ASC`, `DESC`, `SORT`, `BY` as identifiers. This fixed tuple field names like `{ code: ..., display: ... }` in `SupplementalDataElements`.
> 4. **Parser: anonymous tuple selectors** — `_parse_brace_expression()` now distinguishes `{ name: expr }` (tuple selector) from `{ expr, expr }` (list literal). This fixed `SupplementalDataElements` query expressions.
>
> **Remaining:** FHIRHelpers (`&` concatenation) and QICoreCommon (`Resource` type in function params) still fail to parse. These are lower priority since FHIRHelpers functions are handled by UDFs and QICoreCommon utility functions are not directly referenced in define CTEs.

~~The core problem is unchanged — **no CTEs for external library definitions appear in the SQL**.~~ The following are ~~referenced but never defined~~ now all defined:

| Referenced CTE (line) | Library | Status |
|---|---|---|
| `"AdultOutpatientEncounters.Qualifying Encounters"` | AdultOutpatientEncounters | ✅ Present |
| `"Hospice.Has Hospice Services"` | Hospice | ✅ Present |
| `"AIFrailLTCF.Is Age 66 to 80 with Advanced Illness..."` | AIFrailLTCF | ✅ Present |
| `"AIFrailLTCF.Is Age 66 or Older Living Long Term..."` | AIFrailLTCF | ✅ Present |
| `"AIFrailLTCF.Has Criteria Indicating Frailty"` | AIFrailLTCF | ✅ Present |
| `"AIFrailLTCF.Has Advanced Illness..."` | AIFrailLTCF | ✅ Present |
| `"AIFrailLTCF.Has Dementia Medications..."` | AIFrailLTCF | ✅ Present |
| `"AIFrailLTCF.Is Age 66 or Older with Advanced Illness..."` | AIFrailLTCF | ✅ Present |
| `"PalliativeCare.Has Palliative Care..."` | PalliativeCare | ✅ Present |
| `"SDE.SDE Ethnicity"` | SDE | ✅ Present |
| `"SDE.SDE Payer"` | SDE | ✅ Present |
| `"SDE.SDE Race"` | SDE | ✅ Present |
| `"SDE.SDE Sex"` | SDE | ✅ Present |

---

## New Issues Introduced by This Round of Changes

### Issue A: Duplicate Retrieve CTEs (Profile Suffix Problem)

**Status: ⬜ Open**

The same Condition valueset now produces **two identical retrieve CTEs** differentiated only by profile suffix:

```
"Condition: Essential Hypertension (encounter)"  -- line 46
"Condition: Essential Hypertension (problems)"   -- line 52
```

These CTEs have **identical SQL bodies** — same resource type, same valueset, same columns. The profile suffix `(encounter)` vs `(problems)` comes from `ConditionEncounterDiagnosis` vs `ConditionProblemsHealthConcerns` QICore profiles, but both map to FHIR `Condition` and use the same valueset URL. There's no need to query the `resources` table twice.

**Fix:** Deduplicate retrieve CTEs with the same `(resourceType, valueset_url)` combination. The profile is metadata about the CQL source, not a SQL filter distinction. One retrieve CTE per `(resourceType, valueset_url)` is correct. The define CTE can reference the single retrieve CTE from either profile path.

### Issue B: EXISTS Subqueries Still Missing Patient Correlation

> **✅ FIXED (2026-02-28)** — All EXISTS subqueries now have `WHERE sub.patient_id = p.patient_id` correlation. LIMIT 1 also removed from all EXISTS.
>
> **Root causes fixed:**
> 1. `_translate_exists_expression()` and `_build_correlated_exists()` used `SQLRaw` for FROM clause, which `_correlate_exists_ast()` couldn't match (it only checked for `SQLIdentifier`). Changed to use `SQLAlias(expr=SQLIdentifier(...), alias="sub")`.
> 2. `_correlate_exists_ast()` updated to handle both `SQLIdentifier` and `SQLAlias` wrapping `SQLIdentifier` for FROM clause detection.
> 3. Already-correlated EXISTS with residual LIMIT 1 now have LIMIT removed.

~~Some EXISTS subqueries were fixed (line 65 — no LIMIT 1), but **patient correlation is still missing** in most of them.~~

### Issue C: Demographics JOIN Unconditionally Added to Every CTE

> **✅ FIXED (2026-02-28)** — Demographics JOIN now only added to CTEs that actually use age functions.
>
> **Implementation:**
> 1. Added `uses_demographics: bool` field to `DefinitionMeta` dataclass.
> 2. `_translate_age_at_function()` sets `context._needs_demographics = True` when using `pd.birth_date`.
> 3. `translate_definition()` captures this flag and stores it on the `DefinitionMeta`.
> 4. `_generate_joins_for_definition()` checks `meta.uses_demographics` before adding the demographics JOIN.
>
> Result: Only `"Initial Population"` CTE gets the demographics JOIN (it's the only one that uses `pd.birth_date` for age calculation).

~~Every define CTE now has `LEFT JOIN _patient_demographics AS pd ON pd.patient_id = p.patient_id`, even CTEs that don't use age.~~

### Issue D: `verified()` Translated as `list_filter()` Instead of WHERE Clause

**Status: ⬜ Open**

Line 62 shows `verified()` being translated as a runtime list filter:
```sql
list_filter(
  (("Condition: Essential Hypertension (problems)") UNION ("Condition: Essential Hypertension (encounter)")),
  r -> fhirpath_text(r, 'verificationStatus.coding.code') IN ('confirmed', 'provisional')
)
```

This is wrong in multiple ways:
1. **`list_filter` is a DuckDB list function**, not a SQL row filter — it operates on arrays, not result sets
2. **The filter is incomplete** — CQL `verified()` should allow NULL verification status (the `implies` operator means null passes). Generated SQL only allows `'confirmed', 'provisional'`, missing `'unconfirmed'` and `'differential'`
3. **Should be a WHERE clause** on the retrieve CTE or define CTE, not a runtime lambda

**Expected output:**
```sql
"Essential Hypertension Diagnosis" AS (
    SELECT t1.patient_id, t1.resource
    FROM "Condition: Essential Hypertension" t1
    WHERE (t1.verification_status IS NULL
           OR t1.verification_status IN ('confirmed', 'unconfirmed', 'provisional', 'differential'))
      AND t1.onset_date < DATE '{mp_start}' + INTERVAL '6 months'
      AND COALESCE(t1.abatement_date, DATE '9999-12-31') >= DATE '{mp_start}'
)
```

**Root cause:** The fluent function translator is treating `.verified()` as a collection filter (lambda over list) instead of as a SQL WHERE predicate. The fluent function template likely needs to produce a `WHERE` clause fragment, not a `list_filter()` call.

### Issue E: `prevalenceInterval() overlaps` Still Using UDF Calls

**Status: ⬜ Open**

Line 62:
```sql
COALESCE(fhirpath_date(Hypertension.resource, 'onsetDateTime'), fhirpath_date(Hypertension.resource, 'recordedDate'))
  < dateAddQuantity(intervalStart(CAST(getvariable('measurement_period') AS VARCHAR)), ...)
AND COALESCE(NULL, '9999-12-31') >= intervalStart(...)
```

Problems:
1. **`COALESCE(NULL, '9999-12-31')`** — the abatement_date argument is literal NULL. It should reference the precomputed `abatement_date` column from the retrieve CTE, not hard-code NULL
2. **Still using `fhirpath_date()` calls** instead of the precomputed `onset_date` column
3. **Still using `intervalStart(getvariable(...))`** instead of template params or decomposed dates

### Issue F: `"End Stage Renal Disease Procedures"` CTE is Garbled

**Status: ⬜ Open**

Line 58-59:
```sql
SELECT p.patient_id, CASE WHEN intervalEnd(intervalFromBounds(
    fhirpath_text(fhirpath_text(ESRDProcedure, 'performed'), 'start'),
    fhirpath_text(fhirpath_text(ESRDProcedure, 'performed'), 'end'), true, false))
    <= intervalEnd(CAST(getvariable('measurement_period') AS VARCHAR))
  THEN COALESCE(
    CASE WHEN fhirpath_text(("Procedure: Kidney Transplant"), 'status') = 'completed'
      THEN ("Procedure: Kidney Transplant") ELSE NULL END,
    CASE WHEN fhirpath_text(("Procedure: Dialysis Services"), 'status') = 'completed'
      THEN ("Procedure: Dialysis Services") ELSE NULL END)
  ELSE NULL END AS value
```

Problems:
1. **`ESRDProcedure` is unresolved** — not bound to any FROM clause
2. **COALESCE of entire CTEs** — `("Procedure: Kidney Transplant")` is a table reference, not a scalar. Can't COALESCE two tables
3. **Status filter is inline CASE** instead of WHERE clause
4. **Should be a UNION of two branches**, each selecting from its own retrieve CTE with WHERE filters

**Expected:**
```sql
"End Stage Renal Disease Procedures" AS (
    SELECT t1.patient_id FROM "Procedure: Kidney Transplant" t1
    WHERE t1.status = 'completed'
      AND COALESCE(t1.performed_end_date, t1.performed_date) < DATE '{mp_end}'
    UNION ALL
    SELECT t1.patient_id FROM "Procedure: Dialysis Services" t1
    WHERE t1.status = 'completed'
      AND COALESCE(t1.performed_end_date, t1.performed_date) < DATE '{mp_end}'
)
```

### Issue G: First/Last Still Using LIST_EXTRACT

**Status: ⬜ Open**

Despite the code changes for window functions, lines 83, 86, 92 still show:
```sql
LIST_EXTRACT((SELECT * FROM "Blood Pressure Days" AS BPDays), -1) AS value
LIST_EXTRACT((SELECT CASE WHEN array_length(COALESCE(...)) ...
```

The `_translate_first_last_with_window()` method was added but the branch condition `isinstance(node.source, Query)` isn't matching these CQL expressions. The CQL AST for `Last("Blood Pressure Days" BPDays sort asc)` may not produce a `Query` node as the source — investigate what the parser actually emits.

### Issue H: BP Component (Singleton From) Still Broken

**Status: ⬜ Open**

Lines 86, 92 still have the massive 17-way COALESCE for `value[x]` types. The precomputed `systolic_value` / `diastolic_value` columns exist in the retrieve CTE (line 17) but are never referenced by the define CTEs.

**Root cause:** The `singleton from (BPReading.component BPComponent where BPComponent.code ~ "Systolic blood pressure" return BPComponent.value as Quantity)` expression is being translated generically instead of being recognized as a pattern that maps to the precomputed column.

### Issue I: Procedure Retrieve CTEs Missing Precomputed Columns

**Status: ⬜ Open**

Lines 25-29: `"Procedure: Kidney Transplant"` and `"Procedure: Dialysis Services"` have NO precomputed columns — only `patient_id` and `resource`. They need at minimum `performed_date`, `performed_end_date`, and `status`.

### Issue J: Encounter Retrieve CTEs Missing Period Columns

**Status: ⬜ Open**

Line 49-50: `"Encounter: ESRD Monthly Outpatient Services"` has `period` as a single column but needs `period_start` and `period_end` as separate DATE-typed columns. The generic `"Encounter"` CTE (line 31-32) has `effective_date` columns which are wrong for Encounter (should be `period_start`/`period_end`).

---

## Priority Recommendations

The issues above cascade from a few root causes. Fix them in this order:

### 1. ~~Fix P1.2 (External Library CTEs) — THE BLOCKER~~ ✅ DONE

~~The `_process_includes()` → `run_optimization_phases()` pipeline needs to be wired up.~~ All external library CTEs now appear in generated SQL. Parser fixes enabled loading of SDE, Status, and AIFrailLTCF libraries.

### 2. ~~Fix EXISTS Patient Correlation (P1.1 regression)~~ ✅ DONE

~~The LIMIT 1 was removed inconsistently and the patient correlation is still missing.~~ All EXISTS now have `WHERE sub.patient_id = p.patient_id` and no LIMIT 1.

### 3. Fix Verified() and Status Fluent Functions (P1.4)

The `list_filter(... , r -> ...)` pattern is fundamentally wrong. Fluent functions that filter a collection should produce a SQL WHERE clause, not a DuckDB list lambda. This likely requires changing how the fluent function translator composes its output — it should return a predicate that gets added to the CTE's WHERE, not wrap the source in a `list_filter`.

### 4. Deduplicate Profile-Suffixed Retrieve CTEs

Remove the `(encounter)` / `(problems)` suffix logic. Both QICore Condition profiles map to the same FHIR Condition resource type with the same valueset. One retrieve CTE per `(resourceType, valueset_url)` is correct.

### 5. ~~Fix Demographics JOIN Scoping~~ ✅ DONE

~~Track which definitions actually use age functions and only add the demographics JOIN to those CTEs.~~ Demographics JOIN now only added when `DefinitionMeta.uses_demographics` is True.

### 6. Fix Retrieve CTE Columns

Procedure CTEs need `performed_date`, `performed_end_date`, `status`. Encounter CTEs need `period_start`, `period_end`, `status`. These are needed for the define CTEs to use precomputed columns instead of FHIRPath UDF calls.
