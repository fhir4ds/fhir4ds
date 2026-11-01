# 🎯 USER DIRECTIVES

<!--
This file is the PRIMARY MANDATE for the AI Initializer.
Edit this file to define your strategic goals, pipeline, and focus areas.
-->

## Strategic Goal
Resolve the 0.0.9 CQL translator regression where `as FHIR.Coding` and related FHIR complex data type targets are rejected as unknown named types during translation.

## Pipeline
1. bug_fix
2. code_review

## Feature Plan

## Specific Bug Fix

Severity: HIGH
Category: SPEC_VIOLATION

### Bug Statement
Casting an extension `value[x]` expression to `FHIR.Coding` with the CQL `as` operator fails during translation:

```cql
return E.value as FHIR.Coding
```

The failure blocks the standard typed extraction pattern for extension values and surfaces through both direct CQL translation and DQM compilation.

### Reproducer
No DuckDB connection or data is required. The failure occurs during translation.

```bash
pip install fhir4ds-v2==0.0.8
python repro_fhir_coding.py
```

```python
from fhir4ds.cql import translate_cql

CQL = """
library Repro version '1.0'

using FHIR version '4.0.1'

context Patient

define "Extension Value As Coding":
  singleton from (
    Patient.extension E
      where E.url = 'http://example.org/some-extension'
      return E.value as FHIR.Coding
  )
"""

translate_cql(CQL)
```

Actual failure:

```text
fhir4ds.cql.errors.TranslationError: CQL type operator 'as' references unknown type 'FHIR.Coding'
```

DQM surface:

```text
DQMError: Compilation failed for group 'group-0': CQL type operator 'as' references unknown type 'FHIR.Coding'
```

### Expected Behavior
- `translate_cql()` accepts `E.value as FHIR.Coding` as a valid FHIR complex data type assertion.
- `translate_cql()` also accepts other FHIR complex/primitive data type targets used in FHIRHelpers-style patterns, including `FHIR.instant`.
- Existing successful behavior for `FHIR.Period` must remain unchanged.
- Runtime type assertion semantics must remain shape-aware: matching FHIR dynamic choice values pass through, mismatches evaluate to null, and string/numeric transport shape must not be treated as type evidence.

### Suspected Root Cause
The known-type allowlist in `fhir4ds/cql/translator/expressions/_operators.py::_is_known_named_type_target` recognizes CQL system types such as `Code` and `Concept`, and recognizes some FHIR targets such as `FHIR.Period`, but does not include the FHIR `Coding` data type or FHIR primitive `instant`.

The fallback lookups do not cover this case:
- Profile registry lookup is not a general FHIR data type registry.
- `fhir_schema.resources` covers FHIR resource types, not all FHIR complex data types or primitives.

### Required Fix
- Generalize named type target recognition so valid FHIR R4 data types used by CQL `is`, `as`, and strict `cast` are accepted, including at minimum `FHIR.Coding` and `FHIR.instant`.
- Prefer a schema/registry-backed FHIR data type set if one already exists in the codebase; otherwise add a focused canonical set of FHIR R4 primitive and complex data type names near the existing type-target classification logic.
- Preserve the distinction between FHIR resources, FHIR data types, CQL system clinical types, and unsupported names.
- Do not bypass runtime shape guards. Translation should accept valid type targets, but dynamic FHIR values must still be asserted by actual FHIRPath/FHIR choice type where applicable.

### Validation Requirements
- Add focused regression coverage for:
  - `Patient.extension E return E.value as FHIR.Coding`
  - `Patient.extension E return E.value as FHIR.instant`
  - the existing `FHIR.Period` success case as a non-regression control
  - an invalid type target that must still raise `TranslationError`
- Add or update DQM compilation coverage so the DQM layer no longer wraps this as a compilation failure.
- Run a direct translation smoke check equivalent to the reproducer.
- Run the focused CQL translator test file(s) touched by the regression.
- Run `python3 conformance/scripts/run_all.py`.

### Completion Report Requirement
When remediation is complete, explain:
- the confirmed root cause,
- the exact translator/type-classification change,
- why the fix covers FHIR data types generally rather than only the one reproducer,
- the regression tests added,
- all validation commands and outcomes.

## Focus Areas
- Keep the remediation tightly scoped to CQL named type target recognition and typed assertion semantics.
- Do not run fresh exploratory QA before the targeted fix.
- Preserve package metadata and public import behavior; if package metadata changes are required, keep version constants and install snippets aligned.
- Maintain 100% conformance. The final gate must include `python3 conformance/scripts/run_all.py`.
