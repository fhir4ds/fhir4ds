# USER DIRECTIVES

This file is the primary mandate for the AI Initializer.

Human review is required before implementation begins. The ai loop should use
these directives to initialize a remediation campaign only after the human
approves this file and asks to proceed.

## Strategic Goal

Continue the `cqframework/cql-tests-runner` compatibility work after the FHIR
`$cql` facade compatibility layer has been implemented.

The current accepted baseline is:

- Requested targeted runner probes pass:
  - numeric intervals;
  - open intervals;
  - duration uncertainty;
  - quantity aggregates;
  - list-of-interval outputs.
- Final full runner report after facade work:
  - `1647 passed / 40 skipped / 44 failed / 0 errors`
  - report: `conformance/reports/cql_tests_runner_full_report_after_facade_final.json`
  - raw: `conformance/reports/cql_tests_runner_raw/results/202606041736_results.json`

Primary outcome: reduce the remaining 44 full-run failures by fixing the true
owning layer for each issue, while preserving the facade compatibility gains and
avoiding facade hacks that mask translator or runtime semantic gaps.

## Pipeline

1. feature_design
2. feature_implementation
3. code_review

## Feature Plan

No pre-approved implementation plan exists yet. Start with `feature_design`.
Produce a concise remediation design and sequencing proposal for user approval
before implementation.

The design must classify each remaining failure category by owning layer and
must propose the smallest safe acceptance slice for the first implementation
iteration.

## Required Checkpoint Before Remediation

Before starting remediation implementation, preserve the already completed FHIR
facade compatibility work as a checkpoint. If it has not already been committed,
ask the human whether to commit it first.

Suggested checkpoint commit message:

```text
Improve FHIR $cql facade compatibility with cql-tests-runner
```

Do not mix the new remediation changes with the facade compatibility checkpoint
unless the human explicitly instructs otherwise.

## Current Remaining Failure Categories

The latest full runner report shows 44 failures grouped as follows:

1. Long result preservation and runner comparison
   - 21 failures across arithmetic and aggregate Long cases.
   - Examples:
     - `1L + 2L`
     - `Sum({ 6L, 2L, 3L, 4L, 5L })`
     - `maximum Long`
     - `minimum Long`
   - Current symptom: expected runner value is a Long literal such as `100L`,
     but actual output is a JSON number such as `100`; max/min Long also lose
     precision as JavaScript numbers.

2. Ratio literal parsing and comparison
   - 6 failures.
   - Examples:
     - `1'cm':2'cm' = 1'cm':2'cm'`
     - `1'cm':2'cm' ~ 1'cm':2'cm'`
   - Current symptom: CQL parse error for ratio literal syntax.

3. Interval and list null semantics
   - 8 failures.
   - Examples:
     - `expand null`
     - `Interval(null, 5] meets Interval(null, 15)`
     - `Interval[11, null) meets after Interval[11, null)`
     - time precision uncertainty for `properly includes` / `properly included in`
     - `null contains 'a'`
   - Current symptom: runtime semantic result differs from official CQL
     expected null/false behavior.

4. `ToString` formatting
   - 3 failures.
   - Examples:
     - `ToString(125 'cm')`
     - `ToString(DateTime(2000, 1, 1))`
     - `ToString(@T09:30:01.003)`
   - Current symptom: runtime string formatting includes implementation
     transport markers or precision text that differs from CQL expected output.

5. Negative `Round` half behavior
   - 2 failures.
   - Examples:
     - `Round(-0.5)`
     - `Round(-1.5)`
   - Current symptom: current behavior rounds away from zero; expected runner
     output rounds toward zero for these cases.

6. Decimal equivalence precision
   - 2 failures.
   - Examples:
     - `1.5 ~ 1.55`
     - `1.50 ~ 1.55`
   - Current symptom: current equivalence returns false; expected output is true.

7. DateTime null precision equality
   - 1 failure.
   - Example:
     - `DateTime(2001, 1, 1, null) = DateTime(2001, 1, 1, null, null)`
   - Current symptom: current result is null; expected output is true.

8. Code-only `ToConcept` runner mismatch
   - 1 failure.
   - Example:
     - `ToConcept(Code { code: '8480-6' })`
   - Current symptom: normal FHIR `valueCodeableConcept` extraction appears as
     `[object Object]` in the runner comparison path for this code-only Concept
     expected shape.

## Ownership Guidance

Do not assume every remaining failure belongs in the translator. Use this
initial classification as the starting hypothesis and verify with focused
direct translator/runtime probes before changing code.

### Long Preservation

Likely owning layers:

- parser only if a literal parse edge case is discovered;
- translator expression metadata and result-type inference;
- aggregate translation/result metadata;
- facade serializer only as the final output consumer;
- possibly cql-tests-runner extractor behavior for true 64-bit Long comparison.

Important constraints:

- The parser already recognizes uppercase `L` Long literals.
- The facade serializer can emit Long literal text when metadata says `Long`,
  but many failing expressions currently reach the facade as Integer/Decimal or
  `Any`.
- Do not fix this by guessing Long in the facade from numeric value alone.
- Preserve CQL Long through arithmetic, unary, boundary, predecessor/successor,
  aggregate, and min/max paths.
- If the upstream runner cannot compare FHIR Long output because it parses
  expected Long as JavaScript `BigInt` but extracts actual FHIR numbers as
  JavaScript `number`, document that limitation and propose a runner extractor
  patch or local shim instead of distorting FHIR4DS semantics.

Likely files to inspect:

- `fhir4ds/cql/parser/parser.py`
- `fhir4ds/cql/translator/inference.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/translator/expressions/_functions.py`
- aggregate translation paths under `fhir4ds/cql/translator/`
- `fhir4ds/cql/fhir_server/result_serializer.py`

### Ratio Literals

Likely owning layers:

- parser and AST support for ratio literal syntax;
- translator lowering to structured Ratio JSON;
- comparison/equivalence dispatch for Ratio values.

Do not route ratio literals through ad hoc string parsing if the parser can
represent a structured Ratio selector. Use existing Quantity and Ratio runtime
helpers where possible.

Likely files to inspect:

- `fhir4ds/cql/parser/lexer.py`
- `fhir4ds/cql/parser/parser.py`
- `fhir4ds/cql/parser/ast_nodes.py`
- `fhir4ds/cql/translator/expressions/_core.py`
- `fhir4ds/cql/translator/expressions/_operators.py`
- `fhir4ds/cql/duckdb/udf/ratio.py`
- `fhir4ds/cql/duckdb/udf/conversion.py`

### Interval/List Null Semantics

Likely owning layers:

- DuckDB interval/list UDFs and macros;
- translator operator routing only if the wrong helper is selected.

Do not fix null semantics in the facade. A CQL null result and a false result
must be semantically correct before serialization.

Likely files to inspect:

- `fhir4ds/cql/duckdb/udf/interval.py`
- `fhir4ds/cql/duckdb/udf/list.py`
- `fhir4ds/cql/duckdb/macros/list.py`
- `fhir4ds/cql/translator/expressions/_operators.py`

### ToString Formatting

Likely owning layer:

- conversion UDF/runtime formatting.

Expected behavior should be CQL string output, not FHIR literal output:

- `ToString(DateTime(2000, 1, 1))` should return `2000-01-01`;
- `ToString(@T09:30:01.003)` should return `09:30:01.003`;
- `ToString(125 'cm')` should match the official CQL quantity string format.

Likely files to inspect:

- `fhir4ds/cql/duckdb/udf/conversion.py`
- `fhir4ds/cql/translator/expressions/_functions.py`

### Round, Decimal Equivalence, DateTime Equality

Likely owning layers:

- math UDF/runtime for `Round`;
- operator equivalence runtime/translator dispatch for decimal equivalence;
- temporal comparison helpers for DateTime precision/null-component equality.

Likely files to inspect:

- `fhir4ds/cql/duckdb/udf/math.py`
- `fhir4ds/cql/duckdb/udf/datetime.py` or temporal helper modules if present;
- `fhir4ds/cql/translator/expressions/_operators.py`
- comparison/equivalence helper modules under `fhir4ds/cql/duckdb/`.

### Code-only ToConcept Runner Mismatch

Treat this as a runner compatibility issue until proven otherwise.

Normal FHIR `valueCodeableConcept` output is the correct facade shape. Avoid
introducing a non-FHIR special case solely to satisfy the runner's current
single-code Concept extraction collapse behavior unless the human explicitly
approves a runner-specific compatibility shim.

## Implementation Constraints

- Do not begin implementation until the human approves the remediation design.
- Preserve the FHIR facade compatibility layer and its passing targeted probes.
- Do not hide unsupported behavior with `pytest.skip(...)`.
- Add xfail only for explicitly accepted known gaps; otherwise supported
  behavior should fail normally until fixed.
- Keep fixes in the true owning layer:
  - facade only for FHIR `Parameters` request/response compatibility;
  - translator for parse/lowering/type metadata/routing;
  - DuckDB UDFs/macros for CQL runtime semantics;
  - runner harness only for reporting or external runner integration.
- Preserve native-loaded and forced Python fallback DuckDB parity when changing
  UDFs/macros.
- Preserve CQL type distinctions:
  - Integer vs Long vs Decimal;
  - String vs Date/DateTime/Time;
  - Quantity vs scalar numeric;
  - Code vs Concept;
  - Ratio vs Quantity;
  - null vs false.
- Avoid facade-only type guessing for Long or semantic operators.
- Do not add `cqframework/cql-tests-runner` as a submodule.
- Do not make Node/Docker a normal package dependency.
- Any report status must reflect raw runner JSON failures even if the Node
  runner process exits successfully.

## Suggested First Design Questions

1. Which remaining failures can be fixed entirely inside FHIR4DS, and which
   need a runner extractor patch or local runner compatibility shim?
2. For Long, where is CQL Long metadata first erased after parsing?
3. Should Long remediation be attempted first despite the runner `BigInt`
   comparison limitation, or should Ratio/interval semantic fixes go first for
   faster repo-local wins?
4. For ratio literals, should the parser introduce a dedicated Ratio selector
   AST node or reuse an existing tuple/instance selector shape?
5. For interval/list null semantics, are direct DuckDB UDF surfaces already
   wrong, or only translated CQL routing?
6. What focused probes should become the acceptance slice for each category?

## Proposed Acceptance Slices

Design should choose one slice at a time. Candidate slices:

1. Ratio literal parser slice
   - Add parser/translator support for ratio literal syntax.
   - Runner probes:
     - `CqlComparisonOperatorsTest:Equal:RatioEqual`
     - `CqlComparisonOperatorsTest:Equal:RatioNotEqualDiffNumerator`
     - `CqlComparisonOperatorsTest:Equivalent:RatioEquivalent`

2. Interval/list null semantics slice
   - Fix null propagation and false/null distinctions for the failing interval
     and list cases.
   - Runner probes:
     - `CqlIntervalOperatorsTest:Expand:ExpandNull`
     - `CqlIntervalOperatorsTest:Meets:TestMeetsNull`
     - `CqlIntervalOperatorsTest:MeetsAfter:TestMeetsAfterNull`
     - `CqlListOperatorsTest:Contains:ContainsNullLeft`

3. ToString formatting slice
   - Fix CQL string conversion formatting for Quantity, DateTime, and Time.
   - Runner probes:
     - `CqlStringOperatorsTest:toString tests:QuantityToString`
     - `CqlStringOperatorsTest:toString tests:DateTimeToString1`
     - `CqlStringOperatorsTest:toString tests:TimeToString1`

4. Numeric/temporal operator semantics slice
   - Fix negative `Round`, decimal equivalence precision, and DateTime null
     precision equality.
   - Runner probes:
     - `CqlArithmeticFunctionsTest:Round:RoundNeg0D5`
     - `CqlArithmeticFunctionsTest:Round:RoundNeg1D5`
     - `CqlComparisonOperatorsTest:Equivalent:EquivFloat1Float1WithPrecision`
     - `CqlComparisonOperatorsTest:Equal:DateTimeEqTrue`

5. Long preservation slice
   - Preserve Long metadata through translator and evaluator paths.
   - Determine whether runner comparison can be satisfied without modifying the
     runner extractor.
   - Runner/direct probes:
     - `CqlArithmeticFunctionsTest:Add:Add1L2L`
     - `CqlArithmeticFunctionsTest:MaxValue:LongMaxValue`
     - `CqlAggregateFunctionsTest:Sum:SumTestLong`

## Verification Expectations

For each implemented slice:

- Add focused unit/integration tests at the owning layer.
- Run native-loaded and forced Python fallback parity where UDFs/macros change.
- Run direct operation probes through the FHIR `$cql` facade for representative
  expressions.
- Run targeted `cql-tests-runner --only` probes for the slice.
- After multiple slices or any cross-cutting semantic change, run the full
  `cql-tests-runner` suite and update the baseline report path/counts.

The final completion target is a full runner result with all repo-owned
failures resolved and any remaining runner-owned limitations documented with a
clear proposed upstream/local runner fix.

## Documentation Deliverables

Update documentation only after implementation decisions are approved and
validated.

Expected docs updates:

- compatibility matrix for remaining runner/FHIR/CQL Long behavior;
- notes for ratio literal support if parser behavior changes;
- updated conformance runner guide with the latest full-run baseline;
- known limitations for any runner-owned extractor mismatch that remains.

