# Engineer Handoff — SOF-VD-07 HISTORIAN

Issue fixed:
- `QA-001` HIGH: forced Python fallback returned NULL for `$this.linkId` columns inside SQL-on-FHIR `select.repeat`, while native/C++ returned the repeated node value. This violated repeat column context parity because repeat columns evaluate against each repeated node and `$this` is an explicit current-focus reference.

Root cause:
- `fhir4ds.fhirpath.duckdb.evaluator.FHIRPathEvaluator` handled any expression beginning with `$` as one variable name. `$this.linkId` was resolved as variable `this.linkId` rather than resolving `$this` first and evaluating the trailing `linkId` path against the current focus.

Fix:
- `EvaluationContext.get_variable("this")` now returns the current context resource when no explicit iteration value is active, matching native DuckDB behavior.
- The fallback evaluator now splits `$name.path` variable expressions and evaluates the tail against the resolved variable/current-focus value.
- Added regression coverage for direct `$this` focus behavior, `$this.linkId` repeat columns, and `$this.item` repeat expressions.

Validation:
- Fresh probe: `python3 .temp/qa/sof_vd_07_historian_probe.py 64` passed with native and forced fallback matching.
- Focused pytest: `python3 -m pytest fhir4ds/viewdef/tests/integration/test_duckdb.py::TestRepeat -q` passed 5/5.
- Focused variable pytest: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/unit/test_variables.py::TestIterationVariables -q` passed 7/7.
- Broader pytest: `python3 -m pytest fhir4ds/viewdef fhir4ds/fhirpath/duckdb/tests/unit/test_variables.py -q` passed 898/898.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Full package pytest: `7386 passed, 5 skipped, 9 warnings`.
