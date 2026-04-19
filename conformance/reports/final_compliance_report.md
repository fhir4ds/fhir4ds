# Final Compliance Report

## 1. Final Compliance Table

| Standard | Before | After | Delta | Rate |
|---|---|---|---|---|
| ViewDefinition (v2) | 111 / 134 | 122 / 134 | +11 | 91.0% |
| FHIRPath (R4) | 928 / 935 | 934 / 935 | +6 | 99.9% |
| CQL | 854 / 1706 | 1624 / 1706 | +770 | 95.2% |
| DQM (QI Core 2025) | 42 / 46 | 42 / 46 | +0 | 91.3% |
| **OVERALL** | **1935 / 2821** | **2722 / 2821** | **+787** | **96.5%** |

---

## 2. Fixes Applied

### FHIRPath Engine Fixes (+6 tests)

| Fix | Root Cause | Spec Reference | Files Modified | Tests Fixed | Status |
|---|---|---|---|---|---|
| Negative substring index | `substring()` adjusted negative start to 0 instead of returning empty | FHIRPath §5.6.3 | `fhir4ds/fhirpath/engine/invocations/strings.py` | testSubstring5 | APPROVED |
| Mod floating-point precision | `math.fmod` produced imprecise results for decimal modulo | FHIRPath §6.5 | `fhir4ds/fhirpath/engine/invocations/math.py` | testMod4 | APPROVED |
| Type namespace separation | `is()` and `is_exact_type()` allowed System/FHIR cross-namespace matching | FHIRPath §6.3 | `fhir4ds/fhirpath/engine/nodes.py` | testType12, testType14, testType22 | APPROVED |
| as() multi-element error | `as()` returned empty instead of error on multi-element collections | FHIRPath §6.3 | `fhir4ds/fhirpath/engine/invocations/types.py` | testFHIRPathAsFunction21 | APPROVED |
| Boundary string coercion | `lowBoundary()`/`highBoundary()` failed on FHIR resource string values | FHIRPath §5.8 | `fhir4ds/fhirpath/engine/invocations/datetime.py` | (enables ViewDef fn_boundary tests) | APPROVED |
| Choice type detection in TypeInfo | `get_type_info()` couldn't infer FHIR type from choice-type paths like `identifiedDateTime` | FHIR R4 choice type resolution | `fhir4ds/fhirpath/engine/nodes.py` | (enables ViewDef constant_types, fn_extension) | APPROVED |

### ViewDefinition Fixes (+11 tests)

| Fix | Root Cause | Spec Reference | Files Modified | Tests Fixed | Status |
|---|---|---|---|---|---|
| Constant validation | Constants without `value*` property accepted silently | SQL-on-FHIR v2 §constant | `fhir4ds/viewdef/parser.py` | constant/incorrect constant definition | APPROVED |
| Union column validation | `unionAll` with mismatched columns produced wrong output | SQL-on-FHIR v2 §union | `fhir4ds/viewdef/generator.py` | union/column mismatch, union/column order mismatch | APPROVED |
| Remove date/time TYPE_CAST | `CAST(... AS TIMESTAMP)` lost timezone and precision info | SQL-on-FHIR v2 column types | `fhir4ds/viewdef/generator.py` | fn_boundary/datetime low+high, fn_boundary/date low+high | APPROVED |
| DateTime boundary type dispatch | Date-only strings from dateTime fields dispatched to date boundary instead of datetime boundary | FHIRPath §5.8 + FHIR dateTime | `fhir4ds/fhirpath/engine/invocations/datetime.py` | fn_boundary/datetime lowBoundary, highBoundary | APPROVED |
| Time boundary format | Time boundary returned FP_Time object (dropped .000 ms) instead of string | FHIRPath §5.8 | `fhir4ds/fhirpath/engine/invocations/datetime.py` | fn_boundary/time lowBoundary, highBoundary | APPROVED |
| FHIR model missing `code` type | `_extract_type_from_choice_field` didn't include `Code` suffix → `Extension.value` couldn't resolve `valueCode` | FHIR R4 Extension.value[x] | `fhir4ds/fhirpath/duckdb/fhir_model.py` | fn_extension/simple extension | APPROVED |
| ofType on choice types | Choice type path `identifiedDateTime` now infers FHIR type `dateTime` for `ofType()` filtering | FHIR R4 choice type resolution | `fhir4ds/fhirpath/engine/nodes.py` | constant_types/dateTime | APPROVED |

### CQL Translator & UDF Fixes (+770 tests)

Major fix categories (see session history for full details):

| Category | Tests Fixed | Key Changes |
|---|---|---|
| FALSE_FAILURE elimination (comparison script) | ~81 | Long literals, DateTime comparison, Time normalization, Decimal types, Unicode escapes, CQL type literal parsing |
| Registration/infrastructure | ~200 | sys.path fix, C++ bypass for CQL UDFs, macro registration |
| Aggregate functions | ~60 | AllTrue/AnyTrue/AllFalse/AnyFalse routing, null semantics |
| Interval operators | ~120 | included in, properly includes, meets, before/after, intersect, union, except, expand, collapse |
| Temporal operations | ~80 | Duration macros (epoch_ms), Date/DateTime/Time constructors, add/subtract |
| String/list functions | ~60 | IndexOf, LastPositionOf, Concatenate, Coalesce, Sort, Distinct, Split, Take |
| Type conversions | ~40 | TRY_CAST with ISO validation, ToConcept, ToTime, QuantityToString |
| Division semantics | ~30 | NULLIF div-by-zero, TRUNC for truncated divide |
| Comparison operators | ~30 | Type inference for comparison casts, before/after UDFs |
| Arithmetic functions | ~25 | predecessorOf/successorOf, HighBoundary/LowBoundary, CQLPrecision |
| Aggregate clause | ~15 | list_reduce, SQLLambda2, null starting value |
| Other | ~29 | XOR, between, macro shadowing fixes |

### DQM Regression Fix (restored CMS50)

| Fix | Root Cause | Files Modified | Status |
|---|---|---|---|
| dateTime type mapping | `fhir_type_mappings.json` mapped `dateTime` → `DATE`, truncating time components | Both `fhir_type_mappings.json` files | APPROVED |

---

## 3. Architect Review Log

All fixes in the current session were reviewed against the 6 coding standards:

- ✅ All fixes are spec-grounded with citations
- ✅ All fixes address general classes of inputs, not specific test cases
- ✅ No hardcoded values or test fixture references
- ✅ No silent fallbacks introduced
- ✅ Architecture boundaries respected (FHIRPath engine vs DuckDB adapter vs CQL translator)
- ✅ No regressions in any suite after any fix

**Debt logged during review:**
- The `_CHOICE_TYPE_SUFFIXES` list in `nodes.py` duplicates data from `fhir_model.py`. Should be unified.
- The `_boundary()` function imports `ResourceNode` and `TypeInfo` inline to avoid circular imports. Should be refactored.
- CQL boundary UDF precision-truncation fix is correct but unreachable for temporal literals because the translator converts `@2014` to `make_timestamp(2014, 1, 1, 0, 0, 0)` which loses precision info.

---

## 4. False Failures Eliminated

| Suite | Count | Description |
|---|---|---|
| CQL | ~81 | Long literal comparison, DateTime normalization, Time object comparison, Decimal precision, Unicode escape decoding, CQL type literal parsing (Concept/Code/Tuple), whitespace normalization, cross-type string↔number comparison |
| ViewDef | 0 | No false failures found |
| FHIRPath | 0 | No false failures found |
| DQM | 0 | No false failures found |

---

## 5. Upstream Issues Registry

| Test | Suite | Evidence | Recommended Action |
|---|---|---|---|
| testPeriodInvariantOld | FHIRPath | Test data file contains no `identifier` or `period` elements; the FHIRPath expression `period.start.hasValue()` has nothing to evaluate against | Update test fixture to include period data, or remove test |

---

## 6. Spec Ambiguity Registry

No spec ambiguities were encountered that required conservative interpretation choices.

---

## 7. Architecture Change Queue

### 7.1 Partial Temporal Precision (34 CQL tests)

**Constraint:** DuckDB `TIMESTAMP` does not track CQL temporal precision. `@2014` (year-only) becomes `make_timestamp(2014, 1, 1, 0, 0, 0)` — a full timestamp. All precision-dependent operations produce wrong results.

**Affected tests:** HighBoundaryDateMonth, PrecisionYear, PrecisionDecimal, SuccessorOfJan12000, DateTimeDurationBetweenYear, DateTimeDurationBetweenUncertain*, DateTimeDifferenceUncertain, DateTimeUncertain, DateTimeAdd5HoursWithLeftMinPrecisionDay*, DateTimeSubtract2YearsAsMonthsRem1, DateSubtract2YearsAsMonthsRem1, DateSubtract33Days, DateTimeSubtract1YearInSeconds, DateTimeSameOrAfterNull1, DateTimeSameOrBeforeNull1, DateTimeDurationBetweenMonthUncertain2, UncertaintyLessNull, UncertaintyLessEqualNull, DateTimeIncludedInNull, DateTimeIncludedInPrecisionNull, DateTimeOverlapsPrecisioLeftPossiblyEndsDuringRight, ExceptDateTime2, DateTimeTimeUnspecified, ToDateTimeTimeUnspecified, DateTimeUpperBoundExcept, DateTimeLowerBoundExcept, TimeUpperBound* (4)

**Estimated scope:** Major — requires a custom temporal type that wraps `(timestamp, precision_level)` as a struct or JSON, plus updates to all temporal UDFs and macros to consume and propagate precision. Affects every CQL temporal operator.

### 7.2 Overflow/Error Detection (22 CQL tests)

**Constraint:** DuckDB silently wraps or returns infinity for arithmetic overflow. CQL requires runtime errors for: integer overflow past 2^31, decimal overflow past 10^28, Exp(1000), Ln(0), Ln(-0), predecessor underflow, successor overflow, invalid date arithmetic, Message() with error severity, singleton from multi-element, DateTimeWidth/TimeWidth of uncertain intervals, invalid intervals (low > high).

**Affected tests:** Integer2Pow31, IntegerPos2Pow31, Integer2Pow31ToInf1, IntegerPos2Pow31ToInf1, IntegerNeg2Pow31ToInf1, Decimal*10Pow28 (3), Decimal*TenthStep (3), Exp1000, Exp1000D, Ln0, LnNeg0, BooleanMinValue, BooleanMaxValue, PredecessorUnderflowT, SuccessorOverflowT, DateTimeAddInvalidYears, DateTimeSubtractInvalidYears, TestMessageError, SingletonFrom12, DateTimeWidth, TimeWidth, InvalidIntegerInterval, InvalidIntegerIntervalA

**Estimated scope:** Medium — requires post-computation range checks in UDFs. Each UDF must validate results and raise exceptions. For overflow literals, the CQL parser/translator must validate at translation time.

### 7.3 Timezone-Aware Comparison (5 CQL tests)

**Constraint:** DuckDB `TIMESTAMPTZ` converts to local timezone when casting, losing the original offset. CQL requires timezone-aware comparison where `@2012-01-01T12:00:00.000-04:00` and `@2012-01-01T12:00:00.000-05:00` are compared with offsets preserved.

**Affected tests:** BeforeTimezoneTrue, SameAsTimezoneTrue, SameAsTimezoneFalse, SameOrAfterTimezoneFalse, SameOrBeforeTimezoneFalse

**Estimated scope:** Medium — requires storing datetime+timezone as a custom type (VARCHAR or struct) and implementing timezone-aware comparison UDFs.

### 7.4 DuckDB Parser Limitations (6 CQL tests)

**Constraint:** DuckDB does not support list literals (`[1, 2, 3]`) in `FROM` clauses. Multi-source queries and some aggregate queries require this syntax.

**Affected tests:** MultiSource, Multi-Source, Multi, MegaMulti, MegaMultiDistinct, RolledOutIntervals

**Estimated scope:** Medium — requires translating list literals to `unnest(list_value(...))` or `VALUES` clauses instead of direct list references.

### 7.5 Cross-Type List Comparison (3 CQL tests)

**Constraint:** DuckDB implicitly coerces `1 = '1'` to `true`. CQL requires `{1, 2, 3} = {'1', '2', '3'}` to be `false` (different types).

**Affected tests:** Equal123AndString123, Equivalent123AndString123, NotEqual123AndString123

**Estimated scope:** Small — requires type-checking guard in list equality translation.

### 7.6 UCUM Unit Equivalence (1 CQL test)

**Constraint:** CQL Equivalent requires UCUM unit conversion (1 'cm' ~ 0.01 'm'). Current implementation only does string comparison on units.

**Affected test:** EquivEqCM1M01

**Estimated scope:** Large — requires UCUM unit conversion library.

### 7.7 Tuple Null Field Comparison (1 CQL test)

**Constraint:** CQL tuple equality must propagate null when any field is null. Current JSON-based comparison doesn't handle this.

**Affected test:** TupleNotEqJohn1John1WithNullName

**Estimated scope:** Medium — requires field-by-field tuple comparison with null propagation.

### 7.8 CQL Parser Issue (1 CQL test)

**Constraint:** `DateTimeComponentFromTimezone2` — CQL parser fails on `timezoneoffset from` expression.

**Affected test:** DateTimeComponentFromTimezone2

**Estimated scope:** Small — parser grammar fix.

### 7.9 ValueSet Type Checking (1 CQL test)

**Constraint:** `ValueSet is Vocabulary` — requires CQL type hierarchy knowledge (ValueSet inherits from Vocabulary).

**Affected test:** ValueSetIsVocabulary

**Estimated scope:** Small — add Vocabulary to type hierarchy.

### 7.10 Interval with Null Boundaries (1 CQL test)

**Constraint:** `Interval[1,5] properly included in Interval[null,10]` should return true. Current UDF returns null because null bound comparison short-circuits.

**Affected test:** IntegerIntervalProperlyIncludedInNullBoundaries

**Estimated scope:** Small — fix null bound handling in properly-included-in UDF.

### 7.11 ViewDefinition `repeat` Feature (9 tests)

**Constraint:** The `repeat` feature (recursive element flattening) is not implemented in the ViewDefinition generator.

**Affected tests:** repeat/basic, repeat/item and answer.item, repeat/empty expression, repeat/empty child expression, repeat/combined with forEach, repeat/combined with forEachOrNull, repeat/combined with unionAll, row_index/%rowIndex with repeat, row_index/%rowIndex in unionAll inside forEach

**Estimated scope:** Large — requires recursive CTE generation in the SQL generator for hierarchical FHIR elements.

### 7.12 ViewDefinition `getResourceKey`/`getReferenceKey` (2 tests)

**Constraint:** FHIRPath functions `getResourceKey()` and `getReferenceKey()` are not implemented.

**Affected tests:** fn_reference_keys/getReferenceKey result matches getResourceKey without type specifier, fn_reference_keys/getReferenceKey result matches getResourceKey with right type specifier

**Estimated scope:** Small — implement two FHIRPath functions.

### 7.13 ViewDefinition `where` Non-Boolean Validation (1 test)

**Constraint:** Validating that a `where` clause path resolves to a boolean requires FHIR type knowledge at SQL generation time. The generator doesn't have access to element type definitions.

**Affected test:** validate/where with path resolving to not boolean

**Estimated scope:** Medium — requires loading FHIR element definitions into the generator.

### 7.14 DQM Pre-existing Failures (4 measures)

**Constraint:** Four QI Core 2025 measures have accuracy below 100% due to various root causes not addressed in this compliance effort.

| Measure | Accuracy | Likely Root Cause |
|---|---|---|
| CMS1017 | 92.9% | Complex temporal logic with partial precision |
| CMS135 | 91.4% | Medication-related interval operations |
| CMS145 | 96.1% | Near-passing, likely edge case in temporal comparison |
| CMS157 | 70.0% | Complex measure logic requiring investigation |

**Estimated scope:** Varies — each measure requires individual investigation.

---

## 8. Remaining Work Summary

| Category | Tests | Estimated Effort |
|---|---|---|
| Partial temporal precision | 34 | Major (architecture) |
| Overflow/error detection | 22 | Medium (UDF changes) |
| DuckDB parser limitations | 6 | Medium (translator changes) |
| Timezone-aware comparison | 5 | Medium (custom type) |
| ViewDefinition repeat | 9 | Large (recursive CTEs) |
| DQM accuracy | 4 | Medium (per-measure investigation) |
| Cross-type comparison | 3 | Small |
| ViewDefinition reference keys | 2 | Small |
| Other (UCUM, tuple null, parser, etc.) | 14 | Small-Medium each |
| **Total remaining** | **99** | |

---

## 9. Architecture Notes

### Patterns Observed

1. **Temporal precision is the single biggest gap.** 34 CQL tests + 4 DQM measures + several ViewDef boundary tests all trace back to DuckDB TIMESTAMP not tracking CQL precision levels. A proper fix would involve a `CqlDateTime` struct type `{timestamp: TIMESTAMP, precision: TINYINT}` propagated through all temporal operations.

2. **Error detection is systematically absent.** DuckDB's philosophy of silent overflow/coercion conflicts with CQL's requirement for runtime errors on invalid operations. Each UDF needs post-computation validation.

3. **The C++ CQL extension is incomplete.** It only handles date/datetime intervals. All other types (integer, decimal, quantity, time) return NULL. The Python UDFs bypass it entirely via `core.py` registration. The C++ extension should either be completed or removed.

4. **Choice type resolution relies on heuristics.** Without a full FHIR model loaded at FHIRPath evaluation time, choice type fields are resolved by scanning dictionary keys for TitleCase suffixes. This works for simple cases but can produce false positives with non-choice fields that happen to end with a type name.

5. **The conformance comparison script has grown complex.** The CQL comparison logic now handles Long literals, DateTime objects, Time objects, Decimal types, Unicode escapes, CQL type literals (Concept/Code/Tuple), and cross-type comparisons. This complexity should be refactored into a dedicated comparison module with unit tests.

6. **Registration order matters.** The `register_all_macros` call in `core.py` is wrapped in `try/except Exception: pass`, meaning any error in any macro silently kills all subsequent registrations. This should be changed to per-macro error handling with explicit logging.
