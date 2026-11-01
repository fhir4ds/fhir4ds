# Engineer Handoff — FP-17 iteration 1 (EXPLORER)

## Issue QA-001 (HIGH → INTENDED, terminal)

Initial remediation implemented the QA-proposed toBoolean-conversion semantics for §6.5
boolean-logic operands in four places (C++ `collectionIsBool`/`fn_not` via a new
`singletonBooleanCoerce` helper, core `logic._singleton_boolean`, core `existence.not_fn`,
duckdb `operators._get_boolean_value`), rebuilt and redeployed the native extension.

## Recovery Gate triggered

Full conformance run dropped to 2831/2832: official R4 fixture `testLiterals/testIntegerBooleanNotTrue`
(`(0).not() = false` → expected `true`) failed. The official test suite is normative evidence
that non-boolean singletons — including toBoolean-convertible ones such as `0`, `1.0`, `'false'` —
are TRUTHY (true) in Singleton Evaluation of Collections for boolean logic. The QA finding was a
misreading of the spec's first conversion branch; the original truthy behavior was correct.

## Actions

- Reverted all four code changes and restored the bundled and site-packages
  `fhirpath.duckdb_extension` binaries from git (`git checkout --`).
- Replaced the reverted behavior tests with permanent regression guards asserting the
  truthy semantics, anchored to the official fixtures:
  - `fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py`
    (`test_boolean_operators_treat_non_boolean_singletons_as_truthy`,
    `test_not_treats_non_boolean_singletons_as_truthy`)
  - `fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py`
    (`test_boolean_operators_treat_non_boolean_singletons_as_truthy`, dual native/fallback)
- Re-ran validation: parity + regression tests 84 passed; full conformance
  **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — baseline restored.

QA-001 reclassified INTENDED with full evidence in `evolution.json`.
