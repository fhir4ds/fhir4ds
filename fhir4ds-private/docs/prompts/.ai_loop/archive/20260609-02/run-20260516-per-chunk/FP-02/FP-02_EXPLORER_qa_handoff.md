# QA Handoff - FP-02 EXPLORER

## Scope
FHIRPath sections 4.2 Operators, 4.3 Function Invocations, 4.4 Null/Empty propagation, and 4.5 Singleton Evaluation of Collections. Public DuckDB surfaces were tested through native C++ registration and forced Python fallback registration.

## Spec Basis
FHIRPath N1 section 4.5 defines singleton evaluation for single-input functions/operators: singleton non-Boolean nodes used where Boolean is expected evaluate truthy; empty propagates; multi-item inputs signal an error. Section 6.5 states Boolean operators first evaluate operands as Booleans using section 4.5, then apply three-valued logic. Section 6.5.3 applies the same rule to `not()`.

## Probes
Created `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp02_explorer_probe.py` and `fp02_forced_fallback_probe.py` to compare `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, and `fhirpath_number` across native and forced Python fallback paths.

Targeted expressions included empty literal operators (`{} | 'x'`, `'x' & {}`, `1 + {}`), singleton Boolean abuse (`true and gender`, `zero and true`, `gender.not()`), multi-item error resilience (`telecom and true`, `iif(telecom, 1, 2)`), lazy branches (`iif(true, 'ok', telecom.toString())`), and precedence checks (`1 + 2 * 3`, `-1.abs()`).

## Findings
- QA-001: Standalone forced Python fallback still uses `fhirpathpy` for Boolean operator and `iif()` cases, producing non-spec results such as `['female']` for `true and gender`, `[false]` for `zero and true`, and `[]` for non-strict `iif(gender, 'yes', 'no')`.
- QA-002: The bundled native extension binary returns empty for `gender.not()`, while the checked-in C++ source already implements singleton truthiness for `not()`. This appears to be a stale binary/regression packaging issue.

## Validation During QA
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` passed before remediation, but it missed standalone fallback startup and operand-order cases.
