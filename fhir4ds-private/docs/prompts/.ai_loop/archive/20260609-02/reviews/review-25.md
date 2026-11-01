# Review 25 Findings

Milestone review after 25 completed spec-compliance chunks (`FP-01` through `CQL-05`).

Scope covered the current public DuckDB C++ and Python fallback surfaces, CQL/FHIRPath boundary behavior, bundled native extension freshness, exception hygiene, and focused regression tests around the accumulated CQL/FHIRPath changes.

## Findings

### REV-001 - CQL native catch-all parse fallbacks

- **Severity**: MEDIUM
- **Status**: VERIFIED
- **Category**: ERROR_HANDLING
- **Evidence**: `ParseUncertainRange` and `cql_precision` caught all exceptions while parsing numeric input. That can hide allocation/fatal failures as ordinary invalid input.
- **Resolution**: Replaced the catch-all handlers with `catch (const std::exception&)` in `extensions/cql/src/cql_extension.cpp` and `extensions/cql/src/cql/boundary.cpp`.
- **Verification**: CQL native build passed; `./build/release/test/unittest "*cql*"` passed 612 assertions.

### REV-002 - Vectorized `fhirpath()` missed choice-type assertion fallback

- **Severity**: HIGH
- **Status**: VERIFIED
- **Category**: BACKEND_PARITY
- **Evidence**: Scalar wrappers had choice-field handling for expressions such as `value.is(Integer)`, but the vectorized public `fhirpath()` surface could diverge from `fhirpath_bool()` and from the native path on FHIR choice values.
- **Resolution**: Applied the same choice assertion/ofType fallback path to `fhirpath_udf()` and added parity coverage in FHIRPath and CQL structural tests.
- **Verification**: Focused parity pytest passed 20/20; full conformance passed 2822/2822; full `pytest fhir4ds` passed 7150 with 5 skips.

### REV-003 - CQL `ToQuantity` finite Decimal overflow

- **Severity**: MEDIUM
- **Status**: VERIFIED
- **Category**: DATA_HANDLING / PARITY
- **Evidence**: Python fallback could accept an extremely large finite decimal string, overflow it during float materialization, and emit JSON that did not represent a finite CQL Quantity value.
- **Resolution**: Added finite Decimal and finite float guards in `fhir4ds/cql/duckdb/udf/quantity.py`; invalid or non-representable values now return SQL NULL like the native path.
- **Verification**: Focused CQL temporal/complex parity passed; full conformance passed 2822/2822; full `pytest fhir4ds` passed 7150 with 5 skips.

### REV-004 - `fhirpath_is_valid()` accepted truly unknown functions

- **Severity**: MEDIUM
- **Status**: VERIFIED
- **Category**: API_CONTRACT / PARITY
- **Evidence**: `fhirpath_is_valid('foo()')` could return true because parsing produced a function-call AST even though the function was not known to either backend.
- **Resolution**: Added native AST function-name validation and aligned Python fallback handling so truly unknown functions are invalid, while known functions such as `lowBoundary()` remain valid when supported by the public surface.
- **Verification**: Native and forced Python fallback both return false for `foo()`, true for `1.lowBoundary()`, true for `Patient.ofType(Patient).type().name`, and false for `%unknown`; focused parity pytest passed 20/20; native FHIRPath SQL tests passed 294 assertions.

## Deferred Existing Debt

The native FHIR type hierarchy remains hand-maintained in `extensions/fhirpath/src/fhirpath/evaluator.cpp`. This was already recorded as review-20 deferred architecture debt and was not reopened as a new review-25 blocker because no current public parity failure was reproduced. Future work should prefer generated/shared model metadata rather than extending those tables manually.

## Verification

- CQL native build: passed.
- CQL native tests: `./build/release/test/unittest "*cql*"` passed 612 assertions.
- FHIRPath native build: passed.
- FHIRPath native tests: `./build/release/test/unittest "*fhirpath*"` passed 294 assertions.
- Bundled FHIRPath extension SHA-256 matches rebuilt binary: `346a3cd3b2033d4699934808eb599f3021a592cb1197339cfafbcc4138441b22`.
- Focused parity pytest: 20 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath R4 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
- Full pytest: 7150 passed, 5 skipped, 9 warnings.
- `git diff --check`: clean.

No open review-25 findings remain.
