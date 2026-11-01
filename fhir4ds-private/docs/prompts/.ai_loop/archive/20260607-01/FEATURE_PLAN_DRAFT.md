# Feature Plan Draft: CQL Tests Runner Remediation

## Objective

Reduce the remaining `cqframework/cql-tests-runner` failures after the FHIR
`$cql` facade compatibility layer. The accepted baseline is
`1647 passed / 40 skipped / 44 failed / 0 errors` in
`conformance/reports/cql_tests_runner_full_report_after_facade_final.json`.

The work must fix behavior in the owning layer rather than adding facade-only
workarounds. The facade remains responsible for FHIR `Parameters` shape; parser,
translator, and DuckDB UDF/macros remain responsible for CQL syntax, typing,
routing, and semantics.

## Spec Alignment

Primary specification: HL7 CQL 1.5.3, especially:

- CQL Reference and Logical Specification for equality/equivalence,
  interval/list operators, conversion operators, Ratio, Long, Quantity,
  DateTime, Time, and String conversion.
- The Logical Specification states interval `Meets`, `MeetsBefore`, and
  `MeetsAfter` return null if either argument is null and use Start/End
  semantics for boundaries.
- The CQL Reference defines Ratio conversion text as
  `<quantity>:<quantity>`, and Ratio equality/equivalence must compare
  structured ratio values rather than parse errors.
- `ToString` must produce CQL string output, not FHIR literal output.
- Date/DateTime/Time comparisons and equivalence must preserve partial
  precision and null-component semantics.

Primary conformance evidence:

- `conformance/reports/cql_tests_runner_raw/results/202606041736_results.json`
- Targeted runner probes listed in `USER_DIRECTIVES.md`.

## Architecture

The work is split by layer:

- Parser/AST: add Ratio literal syntax if needed.
- Translator: lower new Ratio AST and preserve static type metadata/routing.
- DuckDB UDF/macros: fix semantic runtime behavior for interval/list null
  semantics, Round, ToString formatting, decimal equivalence, and DateTime
  equality.
- FHIR facade: keep existing type serialization. Do not add semantic fixes here
  except consuming improved metadata.
- Runner harness/docs: document runner-owned limitations for Long and code-only
  Concept if they cannot be represented by current runner extraction.

## Implementation Plan

1. Establish direct probes for each remaining category.
   - Use direct parser/translator/runtime probes before changing code.
   - Confirm whether each failure reproduces outside the FHIR facade.

2. Implement repo-owned semantic slices in low-risk order.
   - Slice A: `ToString` formatting.
   - Slice B: `Round`, decimal equivalence, DateTime null precision equality.
   - Slice C: interval/list null semantics.
   - Slice D: Ratio literal parser/translator/runtime comparison.

3. Investigate Long preservation.
   - Find where `Long` metadata is erased after parsing.
   - Preserve Long metadata through translator/evaluator paths where local code
     can do so correctly.
   - Prove whether the current runner can compare actual Long values without a
     runner extractor change. If not, document the limitation and do not distort
     FHIR output.

4. Investigate code-only `ToConcept`.
   - Confirm normal FHIR `valueCodeableConcept` remains correct.
   - Treat the remaining runner comparison shape as runner-owned unless a clean
     FHIR-compatible representation exists.

5. Update docs only after validated implementation.
   - Update compatibility matrix and runner baseline if the full runner count
     changes.

## Test Strategy

For every slice:

- Add focused parser/translator/UDF tests at the owning layer.
- Run forced Python fallback and native-loaded DuckDB parity for UDF/macros.
- Run direct FHIR `$cql` facade operation probes.
- Run targeted `cql-tests-runner --only` probes for each changed category.

After multiple slices:

- Run focused facade tests:
  `python3 -m pytest fhir4ds/cql/tests/unit/test_fhir_server_serializer.py fhir4ds/cql/tests/unit/test_fhir_server_parameters.py fhir4ds/cql/tests/unit/test_fhir_server_public_api.py fhir4ds/cql/tests/integration/test_fhir_server_operation.py -q`
- Run relevant CQL DuckDB integration tests.
- Run the full `cql-tests-runner` suite and update report counts.

## Acceptance Criteria

- Previously passing facade targeted probes remain passing.
- All repo-owned failures in the 44-failure baseline are resolved or have a
  documented, evidence-backed reason they are runner-owned.
- No semantic fix is implemented only in the facade.
- No `pytest.skip(...)` hides supported behavior.
- Code review finds no new high/medium correctness risks.

