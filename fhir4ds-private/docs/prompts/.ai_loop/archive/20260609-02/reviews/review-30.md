# Review 30 Findings

Milestone review after 30 completed spec-compliance chunks (`FP-01` through `CQL-10`).

Scope covered the current CQL public DuckDB surface across native C++ extension,
Python fallback, bundled extension freshness, browser/C++-only direct UDF calls,
translator SQL generation, official conformance, and full package pytest.

## Findings

### REV-030-001 - Boundary exponent normalization in native C++

- **Severity**: MEDIUM
- **Status**: VERIFIED
- **Category**: BACKEND_PARITY
- **Evidence**: `HighBoundary('1e2', 0)` and `LowBoundary('1e2', 0)` returned `1e2` in the native extension while Python fallback returned normalized `100`.
- **Resolution**: Native boundary numeric handling now returns normalized decimal text when no fill digits are needed.

### REV-030-002 - Native date quantity helper input validation

- **Severity**: HIGH
- **Status**: VERIFIED
- **Category**: DATA_HANDLING
- **Evidence**: `dateAddQuantity` accepted huge finite quantities, invalid temporal strings, invalid Quantity JSON, and year-precision dates could format as `2025T`.
- **Resolution**: Native date quantity helpers now reject unsupported or out-of-range quantities, reject invalid temporal input, preserve date-only precision, and keep fractional day/week behavior for hour-or-finer DateTime inputs.

### REV-030-003 - Native boundary and timezone lexical validation

- **Severity**: MEDIUM
- **Status**: VERIFIED
- **Category**: VALIDATION
- **Evidence**: Native `HighBoundary`/`LowBoundary` accepted malformed temporal bodies, `cqlTimezoneOffset` accepted invalid/non-digit offsets, `DateTimeValue::parse` accepted `+09`, and non-finite numeric text produced invalid boundary strings.
- **Resolution**: Added full temporal lexical validation, strict `Z` or `+/-HH:MM` offset parsing, offset range checks, and finite numeric classification in native C++.

### REV-030-004 - Native C++ public Quantity conversion surfaces

- **Severity**: MEDIUM
- **Status**: VERIFIED
- **Category**: API_CONTRACT
- **Evidence**: C++-only/browser execution registered only `ToQuantity(VARCHAR)`, so `ToQuantity(5)` and `ToQuantity(0.1)` raised binder errors while Python supported them.
- **Resolution**: Registered native numeric and Boolean `ToQuantity` overloads, matching the public Python surface.

### REV-030-005 - Python Quantity/scalar arithmetic coercion

- **Severity**: HIGH
- **Status**: VERIFIED
- **Category**: BACKEND_PARITY
- **Evidence**: Quantity/scalar `*` and `/` used plain `CAST` for dynamic scalar operands, accepting `Observation.valueString = "5"` and throwing on invalid text.
- **Resolution**: Dynamic FHIR `value[x]` scalar operands now route through `fhirpath_number`; other dynamic operands use `TRY_CAST`; concrete nonnumeric literals lower to NULL.

### REV-030-006 - Python integer overflow and Power semantics

- **Severity**: HIGH
- **Status**: VERIFIED
- **Category**: SPEC_SEMANTICS
- **Evidence**: Static integer overflow relied on DuckDB `TRY(raw arithmetic)` and could return promoted out-of-range integers. `Power()` and `^` lowered to bare `POW`, producing `NaN` for invalid domains and failing arithmetic typing in conformance value-literal expressions.
- **Resolution**: Statically detected integer overflow emits NULL. `Power()` and `^` lower through `mathPower` and an outer `TRY_CAST(... AS DOUBLE)`, preserving NULL invalid-domain behavior and arithmetic compatibility.

### REV-030-007 - Python boundary helper resource-exhaustion and offset validation

- **Severity**: HIGH
- **Status**: VERIFIED
- **Category**: VALIDATION / RESOURCE_EXHAUSTION
- **Evidence**: `_decimal_boundary_text()` could expand unbounded exponent strings such as `1e100000000`, and boundary helper timezone validation accepted colonless offsets.
- **Resolution**: Python boundary helpers reject non-finite values, cap exponent expansion, and require `Z` or `+/-HH:MM` offsets. `Now()` normalizes DuckDB `CURRENT_TIMESTAMP` strings from `-HH` to `-HH:00` before strict parsing.

## Verification

- CQL native extension build: passed.
- Bundled CQL extension refreshed from the rebuilt native binary.
- Native C++ CQL unittest: `638` assertions passed.
- Focused CQL parity/browser/public-surface pytest: `26 passed`.
- Official CQL conformance: `1706/1706` passed.
- Full master conformance: ViewDefinition `134/134`, FHIRPath R4 `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.
- Full `python3 -m pytest fhir4ds -q`: `7172 passed`, `5 skipped`, `9 warnings`.

No open review-30 findings remain.
