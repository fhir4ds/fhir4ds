# CQL DuckDB Extension (C++)

Native C++ DuckDB extension implementing Clinical Quality Language (CQL) operations as scalar UDFs. Provides age calculations, datetime operations, interval algebra, clinical functions, quantity/ratio arithmetic, valueset membership, and aggregate statistics.

## Build

Requires: Visual Studio 2022 (or compatible C++ compiler), CMake 3.5+

```bash
# 1. Ensure submodules are present (duckdb @ v1.5.2, extension-ci-tools)
git submodule update --init --recursive

# 2. Configure
cmake -DDUCKDB_EXTENSION_CONFIGS="$(pwd)/extension_config.cmake" \
      -DCMAKE_BUILD_TYPE=Release -S ./duckdb/ -B build/release

# 3. Build
cmake --build build/release --config Release -j 8

# 4. Test (628 assertions)
./build/release/test/Release/unittest.exe "*cql*"
```

On Windows with VS 2022, use the full cmake path:
```
"C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
```

## DuckDB Version Compatibility

Pinned to **DuckDB v1.5.2**. Key constraints:

- **C++11 only** — DuckDB compiles with C++11. This extension uses `cql::Optional<T>` (in `src/cql/optional.hpp`) instead of `std::optional`. No `std::variant`, `std::string_view`, structured bindings, or other C++17+ features.
- **yyjson namespace** — yyjson types are in `namespace duckdb_yyjson`. All .cpp files that use yyjson must have `using namespace duckdb_yyjson;`. Do NOT forward-declare `yyjson_doc`/`yyjson_val` in global scope.
- **No `ExtensionUtil`** — Removed in v1.5.0. Use `ExtensionLoader` and `loader.RegisterFunction()`.
- **`ListVector::GetData()` returns a pointer** — Use `auto list_entries = ...` not `auto &list_entries = ...`.

## Architecture

```
src/
  cql_extension.cpp          — Extension entry, UDF registrations (~80+ functions)
  cql/
    optional.hpp             — C++11 Optional<T> (replaces std::optional)
    datetime.hpp/cpp         — DateTimeValue: parse, compare, Julian day, arithmetic
    age.hpp/cpp              — AgeCalculator: years/months/days/hours/minutes/seconds
    interval.hpp/cpp         — Interval: parse, contains, overlaps, before/after, meets, width
    clinical.hpp/cpp         — Latest/Earliest resource selection, claim_principal_*
    valueset.hpp/cpp         — extractCodes, extractFirstCode/System/Value, resolveProfileUrl
    aggregate.hpp/cpp        — statisticalMedian, Mode, StdDev, Variance
    ratio.hpp/cpp            — ratioValue, ratioNumerator/Denominator Value/Unit, RatioToString
    quantity.hpp/cpp         — quantityValue/Unit, parseQuantity, compare/add/subtract/convert
  include/
    cql_extension.hpp        — Extension class declaration
```

### Module Responsibilities

- **datetime**: Core date/time value type. Parses ISO 8601 strings, computes Julian days, supports date arithmetic with quantities. All other modules depend on this.
- **age**: Extracts `birthDate` from FHIR Patient JSON, computes age at a reference date in various units.
- **interval**: CQL interval algebra. Parses both CQL format (`low`/`high`/`lowClosed`/`highClosed`) and FHIR Period format (`start`/`end`). Supports point-in-interval, interval-interval operations, and `collapse_intervals`.
- **clinical**: `Latest`/`Earliest` select resources by a date field. `claim_principal_diagnosis`/`claim_principal_procedure` extract from FHIR Claim resources.
- **valueset**: Code extraction from FHIR CodeableConcept fields. `in_valueset` membership test (stub — returns false, intended for external cache population). `resolveProfileUrl` derives base resource types from StructureDefinition URLs with a small alias layer for opaque profile slugs.
- **aggregate**: Statistical functions operating on `DOUBLE[]` lists.
- **ratio**: Extract and compute from FHIR Ratio structures (numerator/denominator value, unit, ratio) and format internal Ratio JSON as CQL round-trippable `<quantity>:<quantity>` text.
- **quantity**: FHIR Quantity arithmetic with unit conversion (weight, length, time, volume units). `quantityCompare`, `quantityAdd`, `quantitySubtract`, `quantityConvert`.

## Registered UDFs (~80+)

### Age Functions
`AgeInYears`, `AgeInYearsAt`, `AgeInMonths`, `AgeInMonthsAt`, `AgeInDays`, `AgeInDaysAt`, `AgeInHours`, `AgeInHoursAt`, `AgeInMinutes`, `AgeInMinutesAt`, `AgeInSeconds`, `AgeInSecondsAt`

### DateTime Functions
`differenceInYears`, `differenceInMonths`, `differenceInDays`, `differenceInHours`, `differenceInMinutes`, `differenceInSeconds`, `weeksBetween`, `dateTimeNow`, `dateTimeToday`, `dateTimeSameAs`, `dateTimeSameOrBefore`, `dateTimeSameOrAfter`, `dateTimeAfter`, `dateTimeBefore`, `dateTimeOnOrBefore`, `dateTimeOnOrAfter`, `dateComponent`, `dateTimeTimeOfDay`, `dateAddQuantity`, `dateSubtractQuantity`

### Interval Functions
`intervalContains`, `intervalStart`, `intervalEnd`, `intervalWidth`, `intervalOverlaps`, `intervalBefore`, `intervalAfter`, `intervalIncludes`, `intervalIncludedIn`, `intervalFromBounds`, `intervalEquals`, `intervalEquivalent`, `intervalMeets`, `intervalMeetsBefore`, `intervalMeetsAfter`, `intervalProperlyIncludes`, `intervalOverlapsBefore`, `intervalOverlapsAfter`, `intervalStartsSame`, `intervalEndsSame`, `collapse_intervals`

### Clinical Functions
`Latest`, `Earliest`, `claim_principal_diagnosis`, `claim_principal_procedure`

### Aggregate Functions
`statisticalMedian`, `statisticalMode`, `statisticalVariance`, `statisticalStdDev`

### Valueset Functions
`extractCodes`, `extractFirstCode`, `extractFirstCodeSystem`, `extractFirstCodeValue`, `resolveProfileUrl`, `in_valueset`

### Ratio Functions
`ratioNumeratorValue`, `ratioDenominatorValue`, `ratioValue`, `ratioNumeratorUnit`, `ratioDenominatorUnit`, `RatioToString`

### Quantity Functions
`quantityValue`, `quantityUnit`, `parseQuantity`, `quantityCompare`, `quantityAdd`, `quantitySubtract`, `quantityConvert`

### List Functions
`SingletonFrom`, `ElementAt`, `jsonConcat`

### Browser/WASM Registration Invariant

DuckDB-WASM cannot call Python fallback UDFs. Any CQL function emitted into
browser SQL must be registered by the compiled C++ extension or supplied as a
pure SQL macro. Avoid leaving browser-required registrations behind
`__EMSCRIPTEN__` without an equivalent native C++-only validation path; native
Python fallback can otherwise hide browser-only regressions.

All CamelCase functions also have snake_case aliases (e.g., `age_in_years`, `interval_contains`, `quantity_value`).

## Key Implementation Details

### cql::Optional<T>
C++11 replacement for `std::optional<T>`. Provides `has_value()`, `operator bool()`, `operator*()`, `operator->()`, `value()`. Factory functions: `NullOpt<T>()`, `MakeOptional(value)`. Used throughout all CQL modules.

### DateTimeValue
Stores year/month/day/hour/minute/second as `int32_t` fields with an `Optional` wrapper per field for partial dates. Supports ISO 8601 parsing, Julian day conversion, and comparison operators. Date arithmetic uses quantity JSON (`{"value":N,"unit":"d/mo/a"}`).

### Unit Conversion (Quantity)
Supports conversion between compatible units: weight (kg/g/mg/mcg/ng/lb/oz), length (m/cm/mm/km/in/ft), time (s/min/h/d/wk/mo/a), volume (L/mL/dL). Uses conversion-to-base-unit approach.

### Interval Parsing
Accepts both CQL format (`{"low":"...","high":"...","lowClosed":true,"highClosed":true}`) and FHIR Period format (`{"start":"...","end":"..."}`). Plain date strings are auto-wrapped as point intervals.

`intervalStart` and `intervalEnd` are semantic CQL public helpers. They must
return effective boundaries rather than raw JSON fields: open low bounds use
successor and open high bounds use predecessor. Day-precision DateTime marker
values such as `2024-01-31T` step by one day and keep the trailing `T`; fully
timestamped DateTime values step by one millisecond. Keep native C++,
native-loaded Python registration, forced Python fallback, and
no-Python/browser-style direct helper tests aligned for this surface.

Interval equality and equivalence use semantic `Start`/`End` boundaries, not raw
JSON fields or open/closed flag identity. Keep `Interval(1, 6] = Interval[2, 6]`
true across translated SQL, Python fallback registration, native-loaded
registration, and no-Python/browser-style C++ direct helpers. Precision-aware
interval helpers must return SQL NULL when partial Date/DateTime precision makes
the relationship unknown, and `intervalStartsSame`/`intervalEndsSame` return
NULL when the required boundary is absent.

## Test File

`test/sql/cql.test` — 746 assertions covering all UDF categories, NULL handling, edge cases (empty lists, zero denominators, unknown profiles, cross-unit arithmetic, profile URL resolution).

---

## Audit Findings (2026-03-31)

See `docs/architecture/AUDIT_REPORT.md` §8 for full details.

### Critical
1. **Thread safety** — `g_valueset_cache` (`cql_extension.cpp:1125`) is a global mutable map without synchronization.
2. **`AgeInYearsAt` clamps negatives to 0** (`cql_extension.cpp:173`) — silently rewrites data.
3. **`statistical_mode()` truncates to 3 decimals** (`aggregate.cpp:30`) — fundamentally broken for precision.

### Design Debt
- 2,315-line monolithic `cql_extension.cpp` — all 80+ UDFs in one file.
- `in_valueset` is a stub returning false (`valueset.cpp:103-110`).
- Duplicate UCUM table diverges from duckdb-fhirpath-cpp.
- `SameOrBefore`/`SameOrAfter` only handle 3 of 7 precision levels.

### Test Gaps
- No C++ unit tests. Only 312 SQL assertions.
- No tests for leap year edge cases, interval algebra, or quantity precision.

### Remediation Status: COMPLETE (2026-04-02)
- Mutex-protected valueset cache (g_valueset_cache_mutex)
- Negative age calculations return NULL instead of clamping to 0
- statistical_mode() uses std::map for full double precision
- All catch(...) → catch(const std::exception&)
- Magic numbers extracted to named constants (MS_PER_HOUR, MS_PER_DAY, DAYS_PER_YEAR, etc.)
- General StructureDefinition-based `resolveProfileUrl` resolver replacing the 10-entry hardcoded map
- Build: ✅ | Tests: 628 SQL assertions pass

### Known Fragile Areas (Found by QA - 2026-05-01)
- **CQL Aggregate Functions**: **FIXED 2026-05-20 / CQL-20 SKEPTIC**:
  CQL aggregate functions are list functions at the public SQL boundary.
  Do not route direct `AllTrue(list)`, `AnyTrue(list)`, `Median(list)`,
  `Mode(list)`, `StdDev(list)`, `Variance(list)`,
  `PopulationStdDev(list)`, or `PopulationVariance(list)` through DuckDB row
  aggregates. Use list aggregation or CQL logical helpers so null-source and
  null-element behavior matches the spec across forced Python fallback,
  native-loaded registration, and no-Python/browser-style C++ plus pure SQL
  macros. Python `statisticalMode` tie handling must remain aligned with the
  C++ `statisticalMode` public UDF. Quantity aggregate translation must keep
  Quantity JSON shape and perform compatible unit conversion before Sum, Avg,
  Min, Max, Median, Mode, Product, StdDev, Variance, and population statistic
  calculations; do not aggregate raw `$.value` fields without converting units.
  CQL-20 HISTORIAN found two remaining translated-list boundaries:
  query-shaped list sources such as `AllTrue((from {null as Boolean} B return B))`
  are not CTE-backed and must not receive patient_id correlation, while boolean
  query-source aggregates still need CQL defaults when all rows are null
  (`AllTrue` true, `AnyTrue` false). Translated list `Mode` must also use the
  CQL list-mode helper so tied most-frequent values return NULL, matching the
  public `statisticalMode` helper and no-Python/browser macro surface, instead
  of DuckDB's tie-picking `mode` aggregate.
  CQL-20 EXPLORER found two final aggregate boundaries: query-shaped `Min` and
  `Max` over spec-supported Date, DateTime, Time, and String lists must not be
  forced through `TRY_CAST(... AS DOUBLE)`, and direct public `Median(list)`,
  `Mode(list)`, `StdDev(list)`, `Variance(list)`, `PopulationStdDev(list)`,
  and `PopulationVariance(list)` must remain CQL list functions rather than
  DuckDB row aggregate aliases. Translated query-form statistical aggregates
  that need row aggregation should call DuckDB `system.*` aggregate names
  explicitly to avoid colliding with the direct CQL list macro names.
- **CQL List Operators Part 1**: **FIXED 2026-05-19 / CQL-18 SKEPTIC**:
  Fresh probe `.temp/qa/cql18_skeptic_probe.py` found CQL list operators
  diverged from spec semantics when DuckDB built-ins handled nulls, duplicate
  set members, and Quantity JSON strings. `Contains`, `In`, `Includes`,
  `Included In`, `IndexOf`, list equality, `Distinct`, `Except`, and
  `Intersect` must use CQL element equality rather than raw SQL/DuckDB list
  equality. Null list elements compare equal for list equality and set
  operators, Quantity values compare through `quantityCompare(..., '==')`,
  mixed non-numeric scalar element types compare false without DuckDB implicit
  conversion errors, and official singleton-null boundaries still return SQL
  NULL for
  `includes null`, `null included in list`, and `IndexOf(list, null)`. Keep
  forced Python fallback, native-loaded registration, and
  no-Python/browser-style C++ plus pure SQL macro parity tests together.
  CQL-18 HISTORIAN also found named list definitions can bypass the helper
  surface if list metadata is missing. Scalar list definitions must be
  `PATIENT_SCALAR` with `List<T>` metadata, project `value`, and list-typed
  identifiers must route through CQL list helpers before SQL subquery,
  `EXCEPT`/`INTERSECT`, or interval branches. Retrieve/query collections stay
  row-producing. Keep named-list population SQL parity tests across forced
  Python fallback, native-loaded registration, and no-Python/browser-style C++
  registration. CQL-18 EXPLORER additionally found mixed numeric list element
  helpers and literal-list equivalence must compare exact CQL numeric values,
  not `DOUBLE`-rounded values; adjacent large Long/Decimal values above 2^53
  must remain distinct across direct helpers and translated CQL.
- **CQL List Operators Part 2**: **FIXED 2026-05-19 / CQL-19 SKEPTIC**:
  `Skip(list, null)` returns the original list and `Skip(list, negative)`
  returns an empty list across forced Python fallback, native-loaded
  registration, and no-Python/browser-style C++; query-form skip must route
  through the public `Skip` macro rather than raw `LIST_SLICE`. Translated list
  `properly includes` / `properly included in` must use `CQLListContainsEq` and
  `CQLListHasAllEq`, not DuckDB `list_contains` / `list_has_all`, so Quantity
  equivalents such as `1 'g'` and `1000 'mg'` compare equal. Proper-inclusion
  null-container cases such as `null properly includes {2}` and
  `{'s','u','n'} properly included in null` return SQL NULL; helper macros
  should avoid `UNNEST(NULL)` binder failures by unnesting an empty-list
  coalesce internally. List `union` treats null list operands as empty lists,
  including `null union null` producing an empty list. Direct C++
  `SingletonFrom` raises for multi-item lists to match the spec and Python
  fallback. CQL-19 HISTORIAN additionally found translated runtime list chains
  must preserve the same boundaries: query-form `take` routes through the CQL
  `Take` macro so null or negative counts return `{}`, `Length(Skip(...))`,
  `Length(Take(...))`, and `Length(Tail(null as List<T>))` return `0`, and
  translated `singleton from` over
  runtime-produced multi-item lists raises instead of returning NULL while
  valid singleton extraction remains type-preserving. CQL-19 EXPLORER found
  that temporal list membership/equality cannot collapse CQL Date/Time
  uncertainty to `false`: `{ @T15:59:59.999 }` compared with `@T15:59:59`
  must propagate SQL NULL through `contains`, `in`, `=`, `!=`, `properly
  includes`, and `properly included in` when both AST sides are temporal.
  Translator dispatch uses temporal-specific list helper macros only when the
  CQL AST proves temporal types, preserving ordinary string-list semantics.
- **CQL Interval Operators Part 3**: **FIXED 2026-05-19 / CQL-17 EXPLORER**:
  Fresh probe `.temp/qa/cql17_explorer_probe.py` found final interval part 3
  parity gaps across forced Python fallback, native-loaded registration, and
  no-Python/browser-style C++. `intervalUnion` must serialize effective
  Start/End boundaries for finite open endpoints so composed `intervalStart`,
  `intervalEnd`, `intervalContains`, and equality do not include excluded
  points. Decimal interval helpers must preserve CQL scale-8
  successor/predecessor semantics for open boundaries: `intervalStart`,
  `intervalEnd`, `pointFrom`, `intervalWidth`, and `interval_size` all need
  exact decimal-step parity. Quantity interval width/size must convert
  compatible high-bound units into the low-bound unit before subtracting.
  Translated `point in (interval union interval)` must treat `intervalUnion` as
  interval-valued and route to `intervalContains`, not SQL `IN`.
- **CQL Interval Operators Part 3**: **FIXED 2026-05-19 / CQL-17 HISTORIAN**:
  Fresh probe `.temp/qa/cql17_historian_probe.py` found no-Python/browser-style
  C++ `intervalStartsSame` / `intervalEndsSame` parity gaps: these helpers must
  use effective `Start`/`End` boundaries and enforce full starts/ends
  containment, not only raw boundary equality. Fixed in `interval.cpp` and
  validated against forced Python fallback, native-loaded registration,
  no-Python/browser-style C++, native sqllogictest, interval pytest cluster,
  and official conformance. Deep research also documented a
  prose-vs-official-conformance conflict for interval-point `properly includes`;
  preserve strict boundary behavior because `TimeProperContainsFalse` and
  `TimeProperInFalse` in the official CQL XML expect endpoint points to return
  false.
- **CQL Interval Operators Part 3**: **FIXED 2026-05-19 / CQL-17 SKEPTIC**:
  Open-bound interval helpers and precision interval predicates need parity
  hardening across forced Python fallback, native-loaded registration, and
  no-Python/browser-style C++. Fresh probe `.temp/qa/cql17_skeptic_probe.py`
  found and fixed `pointFrom` and no-Python C++ `intervalWidth` divergences for
  half-open integer intervals. Translated interval `same <precision> as`
  compares both start and end boundaries, `same or after/before <precision> of`
  compares the correct Start/End side, and `starts <precision> of` plus
  `properly includes/included in <precision> of` preserve SQL NULL for
  partial-date uncertainty instead of collapsing to `false`.
- **CQL Interval Operators Part 2**: **FIXED 2026-05-19 / CQL-16 EXPLORER**:
  Partial Date/DateTime interval `on or after` / `on or before` without
  explicit precision must return SQL NULL when the Start/End relationship is
  uncertain. Python fallback, native-loaded registration, and no-Python C++
  must preserve public Quantity interval bounds as nested `{"value","unit"}`
  objects, and incompatible-Quantity `overlaps` returns SQL NULL rather than
  Python exceptions or C++ false. Fresh probe: `.temp/qa/cql16_explorer_probe.py`.
- **CQL Logical Operators**: **VERIFIED 2026-05-17 / CQL-04 HISTORIAN**: `And`, `Or`, `Xor`, `Implies`, and `Not` must preserve CQL three-valued logic across direct SQL macros/UDFs, translated scalar expressions, temporal precision chains, and measure-facing query `let`/`where`/`return` population SQL. Keep native-loaded and forced Python fallback DuckDB registrations parity-tested for both direct function calls and translated execution.
- **CQL Temporal/Complex Type Boundaries**: **FIXED 2026-05-17 / CQL-03 EXPLORER**: Translated CQL `ToDate`/`ToDateTime` and `convert ... to Date/DateTime` route through the same spec-aware DuckDB macro/UDF surface as direct SQL calls. Do not reintroduce local SQLRaw/TRY_CAST validation that rejects valid partial precision (`2014`, `2014-01`) or preserves invalid calendar strings (`2024-02-30`). Ratio UDFs guard malformed internal JSON numeric values and return NULL consistently across native-loaded and forced Python fallback registration. Regression coverage lives in `fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py`.
- **CQL Primitive Conversion Boundaries**: **FIXED 2026-05-17 / CQL-01 SKEPTIC+EXPLORER**: Public CQL DuckDB connections must agree between native-loaded registration and forced Python fallback for primitive conversions. `ToInteger`/`ConvertsToInteger` and `ToLong`/`ConvertsToLong` accept Boolean and exact integer strings only; decimal-looking strings such as `1.0` and `1.5` return null/false instead of rounding or raising. `ToDecimal`, `ToBoolean`, and `convert ... to <primitive>` must use spec-aware macros/UDFs rather than generic DuckDB `TRY_CAST`, and invalid conversions return NULL/false without throwing. Keep `test_primitive_parity.py`, conversion parity tests, and `test/sql/cql.test` aligned when changing registration or conversion helpers.
- **CQL Primitive `is`/`as` Assertions**: **FIXED 2026-05-17 / CQL-01 HISTORIAN+EXPLORER**: Primitive `as` is a runtime type assertion, not conversion. Mismatched assertions (`5 as String`, `'5' as Integer`, `true as Integer`, `5L as Integer`) must return NULL while matching primitive types and `as Any` preserve the input. Dynamic FHIR/measure values can arrive as `VARCHAR`, so guarded `TRY_CAST` is required for typed numeric/boolean SQL results. Direct FHIR choice values must use FHIRPath `type().name` instead of SQL text shape, and materialized primitive definitions must preserve/infer `definition_meta.cql_type` for later `is`/`as` checks. Keep translator tests, DQM measure probes, and native-loaded/forced-fallback DuckDB execution parity together.
- **CQL Clinical Type Boundaries**: **FIXED 2026-05-17 / CQL-02 SKEPTIC+HISTORIAN**: Translator-generated Code selectors and named code references must use JSON-shaped CQL Code values rather than legacy `system|code` strings. `ToConcept(Code)`, clinical `is`, and clinical `as` rely on that shape. `ValueSet` and `CodeSystem` references stay structured in value/type contexts (`id`, `name`, optional `version`), and materialized definitions must preserve clinical `definition_meta.cql_type`. `Code` and `Concept` are distinct and are not `Vocabulary`; only `ValueSet` and `CodeSystem` satisfy `Vocabulary`. Clinical `as` mismatches return NULL only when the source clinical type is statically known; dynamic FHIR values such as `Observation.value as Concept` must fall through to runtime matching so valid CodeableConcept comparisons are not erased. Before calling `in_valueset`, unwrap structured ValueSet JSON to the canonical URL, including function-inlined parameters and fluent builders such as `hasPrincipalDiagnosisOf`/`hasPrincipalProcedureOf`. Keep native-loaded and forced Python fallback DuckDB parity tests plus DQM measure probes together for clinical type changes.
- **CQL Structural Type Operators**: **FIXED 2026-05-17 / CQL-05 SKEPTIC+HISTORIAN+EXPLORER**: `is`, `as`, and `convert` must validate unknown type targets, handle `List<T>`, `Interval<T>`, `Choice<T...>`, and `Tuple { ... }` specifiers, and preserve exact static identity for List, Interval, Ratio, Date, DateTime, Time, and Tuple aliases. `as Quantity` must keep Quantity-shaped SQL so `quantity_compare` remains unit-aware; scalar numeric fallback is only for optimized CTE values and must not override incompatible JSON Quantity units. Preserve `CQLMessage` through structural `as Interval<T>`, keep dynamic FHIR `as Concept`/`as Code` runtime matching, and allow SQL CASE sources from choice `as` casts to feed FHIRPath property navigation. `Children()`/`Descendants()` need typed primitive transport, including temporal and Long values, when exposed through `VARCHAR[]` so downstream `is`/`as` and `List<T>` checks do not coerce strings or erase identity. `convert <Quantity> to String` should share the `QuantityToString` path used by `ToString(<Quantity>)`; `convert List<Code> to Concept` and `convert Concept to List<Code>` must remain registered UDF surfaces. Forced Python fallback tests must manually register Python FHIRPath UDFs and assert `fhirpath_predicate` is absent. FHIR choice-field `value.is/as(Type)` parity belongs in both native-loaded and forced fallback coverage. `as Concept` over FHIR resource properties must preserve resource/path behavior for `in_valueset` and `coding_matches`, not blindly replace the resource with a direct JSON value.
- **CQL Conversion Check Boundaries**: **FIXED 2026-05-17 / CQL-06 SKEPTIC; HISTORIAN follow-up found decimal representability gap**: `ConvertsTo*` helpers must distinguish CQL string formats from numeric overloads instead of stringifying all inputs. Boolean strings are only `true/t/yes/y/1` and `false/f/no/n/0`; decimal and quantity strings require at least one digit before an optional decimal point and do not allow exponent notation or leading/trailing whitespace. Decimal string conversion must also enforce implementation representability and CQL scale-8 behavior so `ConvertsToDecimal(x)` does not return true when `ToDecimal(x)` returns NULL or rounds extra fractional digits. Date/DateTime checks reject numeric values that merely stringify to partial dates, while native DateTime values remain acceptable for `ToDate`/`ConvertsToDate`. Python fallback and native-loaded public registration parity is covered in conversion-check/core tests, and direct native C++ `ToQuantity` uses the same quantity grammar.
- **CQL Quantity Conversion Units**: **FIXED 2026-05-17 / CQL-07 SKEPTIC**: `ToQuantity` and `ToRatio` string parsing must reject invalid unit designators instead of packaging arbitrary text into Quantity JSON. The CQL string quantity format requires a valid case-sensitive UCUM unit or CQL calendar duration keyword; `ConvertsToQuantity` and `ConvertsToRatio` must return false when the corresponding conversion would return NULL. Keep Python and direct native C++ parsers aligned because public native-loaded registration can shadow direct C++ behavior.
- **CQL Ratio String Conversion**: **FIXED 2026-05-17 / CQL-07 HISTORIAN**: `ToString(Ratio)` and `convert Ratio to String` in translated CQL must call `RatioToString` and emit CQL round-trippable `<quantity>:<quantity>` text, not the internal Ratio JSON object. Keep `RatioToString` registered in both Python fallback and native C++ DuckDB paths, and keep direct parity tests aligned.
- **CQL Conversion Static Aliases and Concepts**: **FIXED 2026-05-17 / CQL-07 EXPLORER**: Conversion functions and `convert ... to ...` over literal/static definition aliases must inline the static source expression instead of generating `_pt.patient_id` CTE lookups. `convert List<Code> to Concept` must pass a `VARCHAR[]` list of Code JSON values to `ToConceptFromList`, including direct `Code { ... }` instance literals. Native C++ and Python fallback `ToConcept` must flatten JSON arrays of Code objects and reject primitive JSON consistently.
- **CQL Nullological Operators**: **FIXED 2026-05-17 / CQL-08 EXPLORER**: Infix `is true`/`is false` and direct `IsTrue()`/`IsFalse()` must use Boolean-only CQL semantics without inheriting SQL truthiness for numeric/string literals. Dynamic FHIR Boolean paths are physically transported through `fhirpath_bool` before the helper predicate so Patient/Resource Boolean fields still evaluate correctly in population SQL. `Coalesce` scalar overloads are limited to 2 through 5 arguments; zero, one-scalar, and more-than-five scalar calls fail translation, while the single-list overload remains valid.
- **CQL Comparison Operators**: **FIXED 2026-05-17 / CQL-09 HISTORIAN**: Date/DateTime imprecision in public comparison helpers must stay strict and return NULL when precision is uncertain; interval boundary helpers explicitly opt into Date-to-DateTime endpoint promotion for DQM day-window behavior. Decimal literal equivalence follows least-precise-operand rounding, and Quantity equivalence uses `quantityCompare(..., '~')` with calendar-vs-definite duration semantics aligned in Python fallback and native C++.
- **CQL Arithmetic Operators Part 2**: **FIXED 2026-05-18 / CQL-11 SKEPTIC+HISTORIAN+EXPLORER**: Direct arithmetic helper calls are part of the public surface, not just translator internals. Keep native-loaded, forced Python fallback, and C++-only/browser-style macro/UDF registrations parity-tested for `mathRound`, `Power`, quantity modulo/truncated divide, predecessor/successor, direct macro `Div`, and max/min temporal constants. CQL `Round` ties round toward positive infinity, including negative ties. `Power` must NULL for NaN/infinite/unrepresentable results. Compatible-unit Quantity `mod` and truncated `div` convert RHS into LHS units before truncation and preserve the LHS unit. Direct SQL predecessor/successor helpers return NULL at representational boundaries for row resilience, but translated static temporal boundary underflow/overflow remains invalid for official CQL conformance. Maximum/minimum DateTime literals use the official `Z` suffix; Time literals retain `T` and millisecond precision. Dynamic FHIR `value[x]` operands in numeric-only Part 2 operations (`div`, `Power`/`^`, `Round`, `Truncate`) must use `fhirpath_number`, never `fhirpath_text` plus SQL coercion. Apply static representational boundary folding for unary negate and Decimal predecessor/successor at min/max, validate direct C++ Time helper inputs such as `T25:00`, and ignore DateTime timezone offset digits when computing `Precision`. Predecessor/successor over partial Date/DateTime/Time values steps by the lowest specified precision and preserves lexical precision. Mixed scalar/Quantity `mod` and `div` convert scalar operands to unit `1` Quantity JSON before UDF dispatch; do not emit `parse_quantity(<number>)`.
- **CQL String Operators**: **FIXED 2026-05-18 / CQL-12 SKEPTIC+HISTORIAN**: String operators must preserve CQL null/boundary semantics across translated SQL, native-loaded DuckDB registration, forced Python fallback, and no-Python/browser-style macro surfaces. `Combine`/`CombineSep` over an empty non-null filtered list return NULL. `Substring` returns NULL for null/negative/at-or-past-end starts and null/negative lengths. `StartsWith` and `EndsWith` are exact string predicates; translated CQL must call those macros, not SQL `LIKE`, because `%` and `_` are literal characters. String bracket indexing must route through `Indexer`, not list extraction, so at-end/out-of-range string indexes return NULL. CQL regex operators use single-line mode: `Matches` and `SplitOnMatches` pass regex option `s`, and `ReplaceMatches` uses `gs` while preserving CQL `$1` capture references and escaped literal dollars. Deprecated Python string UDFs return NULL for null search operands and invalid substring/regex/replace boundaries rather than raising.
- **CQL Date/Time Operators Part 2**: **FIXED 2026-05-18 / CQL-14 HISTORIAN**: One-argument `Time(hour)` is a component constructor and must return hour-precision CQL time text such as `T12`; keep it distinct from lowercase `time from <DateTime>` extraction. No-Python/browser-style C++ `dateSubtractQuantity` must match native-loaded and forced Python fallback for valid fractional week subtraction from day-precision Date values: `@2024-01-15 - 1.5 weeks` truncates to one week and returns `2024-01-08`. Regression coverage lives in `test_datetime_part2_parity.py` and `test_wasm_cpp_surface.py`.
- **CQL Date/Time Operators Part 2**: **FIXED 2026-05-18 / CQL-14 EXPLORER**: Public date quantity helpers return SQL NULL for malformed Quantity JSON, missing/null/string/Boolean/non-finite `value`, unsupported units, and huge values. Python fallback `dateAddQuantity`/`dateSubtractQuantity` must stay aligned with no-Python/browser-style C++ and must not coerce numeric strings or treat a missing `value` as zero. Valid arithmetic overflow remains a translated CQL invalid-expression path for official conformance.
- **CQL Interval Operators Part 1**: **FIXED 2026-05-18 / CQL-15 SKEPTIC+HISTORIAN+EXPLORER**: `intervalStart`/`intervalEnd` expose CQL effective boundaries for open endpoints, and interval equality/equivalence compares those semantic boundaries instead of raw JSON or authored open/closed flags. Translated interval `=`, `!=`, `~`, and `!~` must call interval-aware helpers. Precision-aware interval predicates over partial Date/DateTime values return NULL when the relationship is unknown, not false/true, and `intervalStartsSame`/`intervalEndsSame` return NULL when the compared boundary is missing. Quantity interval bounds and points must retain Quantity shape and use unit-aware comparison, so `Interval[1 'g', 2 'g'] contains 1500 'mg'` is true across Python fallback, native-loaded, and no-Python C++ surfaces. Interval-producing set-operation UDFs (`intervalExcept`, `intervalIntersect`, `intervalUnion`) remain interval expressions for nested downstream operators such as `(A except B) contains point`; translator dispatch must not fall back to generic DuckDB `system.contains`. Keep forced Python fallback, native-loaded registration, and no-Python/browser-style direct C++ helper coverage together.
- **CQL Interval Operators Part 2**: **FIXED 2026-05-19 / CQL-16 SKEPTIC**: `intervalIntersect` must choose finite bounds when intersecting one-sided closed-null unbounded intervals; `Interval[null as Integer, 5] intersect Interval[3, 7]` and `Interval[3, null as Integer] intersect Interval[1, 5]` both yield `[3, 5]`. Open null bounds are different: official CQL conformance expects `Interval[1, 10] intersect Interval[5, null)` to preserve the unknown open high as `Interval[5, null)`. C++ `intervalMeets*`, `intervalOnOrAfter`, and `intervalOnOrBefore` must use effective Start/End boundaries rather than authored raw open/closed endpoints. Partial Date/DateTime/Time boundaries meet at authored precision, so `Interval[@T03, @T04] meets Interval[@T05, @T06]` is true across forced Python fallback, native-loaded registration, and no-Python/browser-style C++.
- **CQL Interval Operators Part 2**: **FIXED 2026-05-19 / CQL-16 HISTORIAN**: Public no-Python/browser-style C++ `intervalEquivalent` must handle SQL NULL arguments explicitly: both NULL operands return true, exactly one NULL operand returns false. Interval JSON bound parsing treats year-only strings such as `2014` as temporal in interval-bound and precision-aware point contexts so partial Date/DateTime uncertainty returns NULL instead of false. Do not apply a runtime `CQLPrecision` guard across every translated resource interval bound for `overlaps <precision> of`; it regresses DQM. The translator keeps the DQM-proven day-window decomposition for dynamic/resource intervals and folds only static partial temporal interval literals such as `Interval[@2014, @2014] overlaps day of ...` to SQL NULL.
- **CQL Numeric Lexer Boundaries**: **FIXED 2026-05-17 / CQL-01 EXPLORER**: No-whitespace junk after numeric literals is invalid. Reject `1LL`, `1.0L`, and `1day` in the lexer; whitespace-separated tokens remain query grammar responsibility.
- **Duration Operations**: `MonthsBetween` and `WeeksBetween` miscalculate durations due to boundary vs absolute math. **FIXED v0.0.4**: MonthsBetween now uses age_in_months (complete months), WeeksBetween uses epoch_millis (time-aware complete weeks).
- **Precision Retrieval**: `CQLPrecision` yields string lengths instead of CQL standard precision enums. **FIXED v0.0.4**: Changed return type from BIGINT to VARCHAR, now returns precision names ("Year", "Month", "Day", "Hour", "Minute", "Second", "Millisecond").

### NOT A BUG Registry
*Behaviors that look like bugs but are spec-compliant or intentional design decisions.*

- **Interval-point `properly includes` endpoints**: Preserve strict boundary
  behavior for the active official CQL conformance target. Although current CQL
  Reference prose can be read as endpoint-inclusive when the interval is not a
  unit interval, the bundled official XML cases `TimeProperContainsFalse` and
  `TimeProperInFalse` expect boundary points to return `false`; changing this
  regresses conformance from 1706/1706.
