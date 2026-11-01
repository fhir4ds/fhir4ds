# FP-02 EXPLORER — Engineer Handoff (2026-08-16, spec-compliance campaign)

**Workflow**: evolution (iteration 1, EXPLORER personality). All 3 filed issues RESOLVED;
1 new LOW issue discovered during verification, filed as QA-004 (DEFERRED).

## Triage table

| Issue | Category | Severity | Verdict |
| --- | --- | --- | --- |
| QA-001 non-N1 aggregate registry | PARITY_VIOLATION | MEDIUM | CONFIRMED -> RESOLVED |
| QA-002 temporal is/as typing + shape sniffing | PARITY_VIOLATION | MEDIUM | CONFIRMED -> RESOLVED |
| QA-003 boolean-ordering is_valid classification | SPEC_VIOLATION | LOW | CONFIRMED -> RESOLVED |
| QA-004 unknown-function chaining semantics (new) | PARITY_VIOLATION | LOW | DEFERRED |

## Fixes

### QA-001 — remove non-N1 aggregate functions from the Python engine registry
- `fhir4ds/fhirpath/engine/invocations/__init__.py`: removed `sum`/`min`/`max`/`avg`
  registry entries (added an explanatory comment). Ground: verified the full N1
  function list — these do not exist in FHIRPath N1/R4; native treats them as
  unknown -> empty; `fhirpath_is_valid` rejects them on both surfaces, so the
  fallback was evaluating expressions its own validator rejects.
- `fhir4ds/fhirpath/engine/invocations/aggregate.py`: removed the now-unused
  `avg_fn`/`sum_fn`/`min_fn`/`max_fn`/`_unwrap` helpers (kept `aggregate_macro`,
  the R4 §5.? aggregate function). The PUBLIC direct-helper API
  (`fhir4ds/fhirpath/duckdb/functions/math.py::sum_fn` etc.) is a separate module
  and is unchanged.

### QA-002 — temporal field typing for `is`/`as`/`type()` on both surfaces
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`:
  - DELETED both lexical shape-sniffing branches in `fn_isType` (`is` operates on
    the operand's TYPE per §6.3.1, not its lexical content). Model-unknown custom
    fields are FHIR.string on both surfaces now — consistent with `type().name`.
  - `fhirFieldType`: `issued` -> **instant** (R4: Observation/DiagnosticReport.issued
    are instant), added `authoredOn` -> dateTime.
  - Split the `dateTime || instant` lumped acceptance so the sibling primitives
    match exactly (`issued is dateTime` false, `issued is instant` true).
  - `fhirTypeIsA`: `{"instant","dateTime"}` -> `{"instant","Element"}` (canonical
    models/r4/type2Parent.json; R4 has no dateTime-derived primitives).
  - `infer_fhir_type` suffix list += `"Instant"` (mirrors Python
    `_CHOICE_TYPE_SUFFIXES`; fixes `effectiveInstant is instant`).
- `fhir4ds/fhirpath/models/r4/fhir_path_to_type.json` (data-driven metadata):
  += `.issued`->instant, `.authoredOn`->dateTime, `.date`->dateTime (146 entries).
- `fhir4ds/fhirpath/duckdb/fhir_types_generated.py`: TYPE_HIERARCHY
  `"instant"`: `"dateTime"` -> `"Element"` (stale edge; canonical JSON disagreed).
- Extension REBUILT and redeployed to `fhir4ds/fhirpath/duckdb/extensions/` AND
  the user site-packages copy.
- Post-fix 30-case dual-path matrix: 0 failures (authoredOn/issued/effectiveInstant/
  Composition.date/custom-unknown/birthDate/active).

### QA-003 — boolean-ordering validity classification
- `fhir4ds/fhirpath/duckdb/udf.py::_is_valid_empty_result_error` and
  `extensions/fhirpath/src/fhirpath_extension.cpp::FhirpathIsValidFunction`:
  added `"Comparison operators are not defined for Boolean operands"` to the
  accepted execution-type-error messages (same class as `1 > true`).
- Updated the stale pin in
  `test_comparison_parity.py::test_boolean_comparison_is_not_ordered`
  (`true > false` is_valid False -> True) with doctrine grounding.

## QA-004 (NEW, DEFERRED) — unknown-function chaining divergence

While verifying QA-001: `'{}.foo().empty()'` -> native `['true']` (unknown fn ->
empty, chain continues) vs fallback `[]` (unknown fn -> error -> whole expression
empty). Applies to ALL unknown functions, pre-existing (reproduced with `foo`
unrelated to my changes). The fallback is the §4.3-faithful reading; the native's
continue-with-empty is a documented load-bearing convention for ViewDefinition
resilience ("Unimplemented functions return NULL in boolean context"). Fixing
either direction has cross-surface consequences beyond this chunk's surgical
scope; only manifests for is_valid=False expressions. Filed LOW/DEFERRED for the
outer orchestrator.

## Validation (Recovery Gate)

- Reproducers: all pass on both engines (matrices in `.temp/qa/fp02_explorer_2026_08_16/`).
- Regression tests added:
  - `test_type_parity.py::test_temporal_field_type_specifiers_parity_fp02_explorer`
    (29 cases, value + parity assertions)
  - `test_operator_parity.py::test_non_spec_aggregate_functions_parity_fp02_explorer`
    (8 cases)
  - `test_operator_parity.py::test_ordering_type_error_validity_classification_fp02_explorer`
    (9 cases)
- `python3 -m pytest fhir4ds/fhirpath/` -> **1720 passed / 0 failed**.
- Full conformance `run_all.py` -> **2832/2832** (ViewDefinition 144/144,
  FHIRPath 935/935, CQL 1706/1706, DQM 47/47) — baseline held exactly.
- Probe re-runs: probe1 162 cases (3 channel-level "failures" are the pre-existing
  QA-004 chaining seam for `{}.sum().empty()`-style chains — top-level sum/min/max
  divergences all resolved); probe2 74 cases 0 failures.

## Residuals / follow-ups

- QA-004 unknown-function chaining semantics (LOW, DEFERRED).
- `.date`-named fields: name-only metadata cannot distinguish Composition.date
  (dateTime) from DocumentReference.date (instant); both surfaces now agree on
  dateTime for `date` fields (parity), which is R4-correct for the common case.
  Full R4 temporal-field coverage would need resource-qualified metadata in the
  native (the generated `models/r4/path2Type.json` has all 7,705 entries — a
  data-completeness follow-up, not this launch).
- `fhirFieldType` (native) vs `fhir_path_to_type.json` (Python) remain two
  curated surfaces to keep aligned when adding fields.
