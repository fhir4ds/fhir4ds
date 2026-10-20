# Design Note: Context-Patient Audit Leaves in the Translator

Status: APPROVED (Muse-gate adjudication + independent review, both
converged) — amended design below supersedes the draft seams.

## Gate outcomes (2026-10-20)

Independent review + design-gate adjudication (both LGTM with
amendments):

1. Seam A moves from precompute-WHERE detection (fragile under mixed
   defines where the precompute predicate mixes `birth_date` and
   retrieve CTE references) to METADATA ATTACHMENT at the age-family
   translation site (`_functions.py` `_translate_age_function` /
   `_translate_age_at_function` — the true provenance boundary; they
   already set `context._needs_demographics`), using the existing
   `_audit_target` attribute protocol consumed by
   `_extract_audit_target` / `_maybe_wrap_audit_comparison`.
2. `operator: 'derived'` / `threshold: 'context'` IS part of the S22f
   contract (the EvidencePopover + the retired-backfill test assert
   it) → the `audit_patient_property` macro is RETAINED, and MUST land
   in BOTH `macros/audit.py` AND `web/cql-cleanroom/src/lib/cql-macros.ts`
   in the same change (`test_macro_sync.py` fails CI otherwise).
3. Targets are already non-constant (aggregated subqueries);
   `'Patient/' || _pt.patient_id` is strictly simpler — but `_pt`
   scope survival through `_correlate_exists_ast` (correlation.py) and
   `_rewrite_cte_references` (cte_manager.py) must be VERIFIED, not
   assumed.
4. Audit macros are Python SQL macros registered on BOTH engine paths
   by `register_all_macros` (extension.py) — NO native C++ rebuild
   needed (the draft §3 was wrong: cql_extension.cpp has zero audit
   registrations).
5. Partial-birthDate value spelling parity (backfill reads raw
   resource JSON; the macro path carries `fhirpath_date(...)`
   output — `1975-03`, `1980`) gets an explicit regression pin BEFORE
   the S22f backfill is removed.

## Problem

Defines deriving from CONTEXT-PATIENT properties (the `_patients` CTE's
`patient_resource` / `birth_date` columns — `AgeInYearsAt`,
`Patient.gender = …`, `Patient.deceased`, …) emit either
`audit_leaf(...)` (NO evidence — renders "no contributing resources")
or `audit_comparison(..., target NULL, ...)`. Today the S22f
explain-seam backfill (`_add_context_patient_leaves` in
`operations/capabilities/evaluate.py`) re-reads the CQL text at
explain time and synthesizes `{target: Patient/<id>, attribute:
<prop>, value: <v>, operator: 'derived'}` leaves. That backfill is a
post-hoc text heuristic OUTSIDE the audit pipeline; the leaf should be
born IN the translated SQL.

## Observed lowering (audit_mode="full", today)

`AgeInYearsAt(@2024-01-01) >= 18` lowers to a precompute CTE +
`audit_leaf(EXISTS(...))` in the define CTE — evidence `[]`.

`Patient.gender = 'female'` lowers to
`audit_comparison(fhirpath_text(_pt.patient_resource, 'gender') = 'female',
'=', fhirpath_text(...), 'female', 'gender', CAST(NULL AS VARCHAR))` —
a leaf EXISTS but its `target` is NULL (no winner-resource id exists:
the operand is the patient row, not a retrieve).

## Design (as amended by the gates)

### 1. New macro: `audit_patient_property` (retained — gate §2)

```sql
CREATE OR REPLACE MACRO audit_patient_property(
    val, patient_id_expr, attr, prop_value
) AS (
    struct_pack(
        result   := val,
        evidence := list_value(struct_pack(
            target      := 'Patient/' || CAST(patient_id_expr AS VARCHAR),
            attribute   := CAST(attr AS VARCHAR),
            value       := CAST(prop_value AS VARCHAR),
            operator    := 'derived',
            threshold   := 'context',
            trace       := CAST([] AS VARCHAR[])
        ))::<EVIDENCE_STRUCT_TYPE>
    )
);
```

Ported to `cql-macros.ts` in the SAME change (macro-sync contract,
`test_macro_sync.py`).

### 2. Translator emission — amended seams

**(a) Age family — metadata attachment at the translation site**: the
age-function translators (`_translate_age_function` /
`_translate_age_at_function` in `_functions.py`) attach a
`_patient_property` marker (property name + value SQL expression,
mirroring the `_audit_target` attribute protocol) on the returned
`SQLExpression` when they read `_pt.birth_date`. When
`_maybe_wrap_audit_comparison` (or the define-CTE audit wrapper) sees
a comparison whose operand carries `_patient_property` AND the audit
evidence would otherwise be a bare `audit_leaf`, it emits
`audit_patient_property(EXISTS(...), _pt.patient_id, 'birthDate',
_pt.birth_date)`. Mixed defines keep their `audit_and` trees — the
leaf scopes to the age subexpression only.

**(b) audit_comparison target fill**: `_extract_audit_target` learns
patient-row operands — `fhirpath_text(_pt.patient_resource, '<attr>')`
calls produce target `'Patient/' || _pt.patient_id` (the attribute
already flows from the call's path argument). This fills the
NULL-target gender / deceased[x] comparisons.

### 3. Dual-engine parity (corrected by gate §4)

Audit macros are Python SQL macros registered on BOTH engine paths by
`register_all_macros` (extension.py) — cql_extension.cpp carries ZERO
audit registrations. The ONLY extra surface is the browser
`cql-macros.ts` port (§1). No native rebuild.

### 4. Retiring the S22f backfill

Order (gate §5): pin partial-birthDate spelling parity FIRST
(regression on `1975-03` / `1980` forms through the macro path — the
backfill reads raw resource JSON while the macro path carries
`fhirpath_date(...)` output), then remove
`_add_context_patient_leaves`, then swap the operations test to
macro-sourced assertions (age leaf: operator 'derived'; gender leaf:
operator '=' with the filled target).

### 5. Downstream consumers

- EvidencePopover: renders target/attribute/value generically —
  Playwright pin (InAgeRange row shows Patient/<id> · birthDate).
- compare_evidence / runDiff: artifacts are population booleans —
  leaf additions do not alter them; verify + pin.
- verify --evidence CI artifacts: same struct type; pin one golden
  leaf.
- DQM audit engine: consumes effective_result masks, not leaves;
  verify untouched.

## Verification checklist (from the gates)

1. `_pt` scope survival through `_correlate_exists_ast`
   (correlation.py) and `_rewrite_cte_references` (cte_manager.py) —
   verified by execution tests, not assumed.
2. Partial-birthDate parity regression BEFORE backfill removal.
3. `test_macro_sync.py` green with the cql-macros.ts port.
4. Operations + devserver + cleanroom e2e suites green at each phase.
