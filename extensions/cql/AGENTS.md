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

### CQL-14 Time Constructor Null Precision
CQL-14 HISTORIAN fixed translated `Time(...)` constructors so trailing null
components are unspecified precision, not invalid input. Per the current CQL
Reference, `Time(12, null)` preserves hour precision as `T12`,
`Time(12, 30, null)` preserves minute precision as `T12:30`, and
`Time(12, 30, 0, null)` preserves second precision as `T12:30:00`. Gaps where
a finer component is specified below a null component, such as
`Time(12, null, 0)`, still return SQL NULL. Keep translated CQL execution
aligned across forced Python fallback and native-loaded DuckDB registrations.

### CQL-15 Interval Collapse/Expand Per Boundaries
CQL-15 EXPLORER fixed interval Part 1 fragility around empty and
`per`-qualified interval lists. `collapse` over an empty interval list returns
`[]`, while a null list returns SQL NULL, and forced Python, native-loaded, and
no-Python C++ surfaces must agree. `collapse ... per` and `expand ... per`
must preserve the authored Quantity and enforce point-type compatibility:
numeric intervals only accept default-unit Quantity (`'1'` or no unit), while
temporal intervals require temporal units and Quantity intervals require
compatible Quantity units. Compatible translated `collapse ... per` routes
through `expand(list, per)` before `collapse_intervals(...)` so the authored
partition size participates in collapse; incompatible static `per` lowers to
SQL NULL. Do not silently drop `per` in translation or ignore incompatible
units such as `per 1 'cm'` on numeric intervals. Keep
`.temp/qa/cql15_explorer_probe.py`, `test_interval_part1_parity.py`,
native C++ rebuild/copy, and full conformance aligned when changing this path.
Malformed non-null public `expand`/`expand_points` `per` arguments are not the
same as omitted or SQL NULL `per`: invalid Quantity JSON, missing/non-numeric
`value`, or Boolean/string values must return SQL NULL across forced Python,
native-loaded, and no-Python/browser-style C++ surfaces.

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
- **CQL Errors and Messaging**: **FIXED 2026-05-31 / CQL-22 SKEPTIC/HISTORIAN**:
  `Message(source, condition, code, severity, message)` lowers to the public
  `CQLMessage` helper whenever the translator cannot fold it to source. Keep
  that helper available in SQL-only/browser-style runtimes as a pure SQL macro,
  not only as a Python supplement UDF, because DuckDB-WASM cannot call Python.
  The helper must return source unchanged for false or null conditions and for
  non-Error severities, and raise only for true-condition Error severity. Keep
  parity coverage in `fhir4ds/cql/duckdb/tests/integration/test_message_parity.py`
  for Python fallback, native-loaded, and no-Python execution. Declared scalar
  parameter defaults compile to typed SQL defaults; runtime parameter override
  coverage belongs on `translate_library_to_population_sql(..., parameters=...)`,
  not legacy `setvariable()` expectations for `translate_cql()`. Statically
  known invalid signature operands must fail at translation: the condition
  argument is Boolean, and code/severity/message arguments are String. Do not
  let SQL transport types or DuckDB coercion make `Message('src', 1, ...)`,
  `Message('src', 'true', ...)`, `Message('src', true, 400, ...)`, or
  non-String severity/message values appear valid.
- **CQL Clinical Operators**: **FIXED 2026-05-31 / CQL-21 SKEPTIC**:
  Browser/no-Python runtimes cannot call Python supplement UDFs, so every
  clinical age precision emitted by translation or exposed publicly must be
  registered in the compiled C++ extension. Keep `AgeInHoursAt`,
  `AgeInMinutesAt`, and `AgeInSecondsAt` registered alongside the corresponding
  `CalculateAgeIn*At` functions; Python fallback and native-loaded paths can
  hide missing compiled registrations. Preserve no-Python coverage in
  `fhir4ds/cql/duckdb/tests/integration/test_clinical_operator_parity.py`
  whenever adding or renaming clinical operator surfaces.
  CQL-21 HISTORIAN found the adjacent list-terminology and ValueSet expansion
  boundary. The CQL `in(List<Code|string|Concept>, CodeSystem|ValueSet)`
  overloads are clinical membership operators, not generic list containment;
  static lists must be flattened through Code/Concept entries or string codes
  before lowering to CodeSystem URL checks or `in_valueset` calls. The public
  `ExpandValueSet(ValueSet)` surface must also be available in SQL-only
  runtimes as a pure SQL macro backed by `valueset_codes`, because browser/
  no-Python execution cannot rely on Python UDF registration. Keep forced
  Python fallback, native-loaded, and no-Python parity coverage together.
  CQL-21 EXPLORER found the versioned ValueSet variant: structured CQL
  ValueSet literals include optional `version`, and `ExpandValueSet` must
  resolve `id|version` just like ValueSet membership does. Test versioned
  expansion with only the versioned `valueset_codes.valueset_url` loaded so
  accidental base-URL lookup cannot pass.
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
  Fresh CQL-20 SKEPTIC rerun found two additional aggregate type/formula
  boundaries. Translated aggregate functions must reject statically invalid
  list element types instead of relying on DuckDB casts, especially Boolean
  aggregates over non-Boolean lists and numeric/statistical aggregates over
  string lists. Direct public `Median`, `StdDev`, `Variance`,
  `PopulationStdDev`, `PopulationVariance`, `Product`, and `GeometricMean`
  must also reject string-list coercion. `GeometricMean` is defined as
  `Power(Product(X), 1 / Count(X))`; do not implement it solely as
  `exp(avg(ln(x)))` without zero/all-null guards, and fold query-produced rows
  to a list before calling the public helper.
  Fresh CQL-20 HISTORIAN rerun found another static-validation boundary:
  aggregate validators must classify simple nested list, tuple, interval, typed
  instance, constructor, `as` assertion, and known conversion/function-return
  elements before SQL generation. Otherwise invalid calls such as
  `AllTrue({{1, 2}})`, `Avg({ToString(5)})`, `Avg({DateTime(2012, 1, 1)})`, or
  `Min({Tuple { a: 1 }})` can fall through to DuckDB list functions or casts
  instead of failing at the CQL translator boundary.
  Fresh CQL-20 EXPLORER rerun found two query-produced aggregate boundaries:
  CQL list macros can shadow DuckDB row aggregates, so translated query-form
  `Product(...)` must call `system.product` rather than bare `PRODUCT`, and
  static aggregate validation must infer simple query-produced element types
  from list sources and aliases. Otherwise invalid queries such as
  `AllTrue((from { 1, 2 } I return I))`, `Avg((from { '1', '2' } S return S))`,
  or `Min((from { Tuple { a: 1 } } T return T))` can inherit DuckDB Boolean,
  numeric, or JSON behavior instead of failing at translation.
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
  Fresh CQL-18 SKEPTIC rerun on 2026-05-31 found two remaining transported-list
  boundaries. `CQLListElementEquivalent` must recognize Code/Concept JSON and
  apply CQL clinical equivalence, so `List<Code>` / `List<Concept>` aliases and
  direct helper calls ignore Code display/version for `~` while equality and
  set operations remain display-sensitive CQL equality. The translator must
  also treat `singleton from` over a nested list as list-typed, otherwise `~`
  over the transported list falls through to raw SQL `=`. Do not classify a
  `ListExpression` containing Quantity elements as a scalar Quantity; Quantity
  list equality routes through list helpers, while `singleton from { 1 'g' }`
  remains a scalar Quantity.
  CQL-18 HISTORIAN found two remaining public helper semantics gaps. Code and
  Concept list equality must use clinical tuple equality by element name, not
  raw JSON serialization, so JSON key order is irrelevant but display/version
  presence and value still matter. Quantity list equality/containment must not
  coalesce incompatible-dimension `quantityCompare(..., '==')` nulls to false;
  unknown element equality remains unknown for `contains`, `includes`, and
  ordered list equality when no definitive false/true result exists.
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
  must remain distinct across direct helpers and translated CQL. Fresh CQL-18
  EXPLORER rerun on 2026-05-31 found `IndexOf` must preserve unknown element
  equality too: incompatible Quantity dimensions and clinical Code equality
  with missing optional components return SQL NULL, not `-1`, when no true
  match exists. Query-produced list sources passed to translated `IndexOf`
  must be folded to a DuckDB list before invoking `CQLIndexOf`; do not pass
  row subqueries directly into list macros.
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
  Fresh CQL-19 SKEPTIC rerun on 2026-05-31 found two public-surface/count
  discipline gaps. Direct `Length(NULL::List<T>)` must return `0` while
  `Length(NULL::String)` remains SQL NULL; the shared `Length` macro must
  branch on typed list nulls without changing string semantics. `Skip` and
  `Take` counts are CQL `Integer` arguments: direct public macros must reject
  Decimal/String counts instead of inheriting DuckDB slice coercion, and
  translated `Skip(...)`/`Take(...)` plus query-form `skip`/`take` must reject
  statically known non-Integer counts before SQL generation. Keep these checks
  in `test_list_part2_parity.py` across forced Python fallback, native-loaded,
  and no-Python/browser-style C++ macro registrations.
  Fresh CQL-19 HISTORIAN rerun on 2026-05-31 found transported Interval list
  elements were the remaining semantic equality gap. `CQLListElementEqual` and
  `CQLListElementEquivalent` must detect interval-shaped JSON and delegate to
  `intervalEquals` / `intervalEquivalent`; otherwise `{ Interval(1, 6] }` and
  `{ Interval[2, 6] }` compare unequal, `properly includes` misses semantic
  interval members, and list `union` keeps duplicate interval values. Keep
  interval-valued list equality/equivalence, proper inclusion, and union
  deduplication covered in `test_list_part2_parity.py` across forced Python
  fallback, native-loaded registration, and no-Python/browser-style C++.
  Fresh CQL-19 EXPLORER rerun on 2026-05-31 found scalar query-produced lists
  were still reaching Part 2 list operators as single-row scalar subqueries.
  Literal-list queries such as `(from {1, 2, 3} X return X)` must be folded
  into a DuckDB list before `Last`, `Length`, `Tail`, `Skip`, `Take`, list
  union, proper inclusion, and `singleton from` consume them; otherwise DuckDB
  binder errors or scalar-subquery truncation replace CQL list semantics. Keep
  this folding limited to scalar list queries and list-valued aliases; do not
  collapse retrieve/resource-backed query rows, because DQM population SQL
  depends on patient-correlated row shape. The EXPLORER regression probe and
  `test_cql_list_part2_query_produced_lists_remain_lists` cover forced Python,
  native-loaded, and no-Python/browser-style registrations.
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
  Fresh CQL-17 HISTORIAN rerun on 2026-05-31 fixed typed null Start/End
  extrema. `start of Interval[null as Integer, 5]` and direct
  `intervalStart(intervalFromBounds('__null__', '5', true, true))` must return
  the CQL Integer minimum, not the internal `__null__` sentinel or a DateTime
  minimum. The symmetric `end of` case returns the point-type maximum. Date
  and Time intervals use Date/Time extrema, and open null boundaries remain
  SQL NULL. Keep forced Python fallback, native-loaded Python shadowing, and
  no-Python/browser C++ parity coverage together.
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
  Fresh CQL-17 SKEPTIC rerun on 2026-05-31 found one additional null-container
  guardrail: `Interval[1, 5] properly included in (null as Interval<Integer>)`
  is SQL NULL per the current CQL Reference, not an unbounded interval. Keep
  this distinct from `Interval[1, 5] properly included in Interval[null as
  Integer, null as Integer]`, which remains true because the interval exists
  with unbounded typed-null endpoints. The direct public helper,
  translated CQL, native-loaded Python shadowing, forced Python fallback, and
  no-Python/browser-style C++ surface must stay aligned.
- **CQL Interval Operators Part 2**: **FIXED 2026-05-19 / CQL-16 EXPLORER**:
  Partial Date/DateTime interval `on or after` / `on or before` without
  explicit precision must return SQL NULL when the Start/End relationship is
  uncertain. Python fallback, native-loaded registration, and no-Python C++
  must preserve public Quantity interval bounds as nested `{"value","unit"}`
  objects, and incompatible-Quantity `overlaps` returns SQL NULL rather than
  Python exceptions or C++ false. Fresh probe: `.temp/qa/cql16_explorer_probe.py`.
- **CQL Logical Operators**: **VERIFIED 2026-05-17 / CQL-04 HISTORIAN**: `And`, `Or`, `Xor`, `Implies`, and `Not` must preserve CQL three-valued logic across direct SQL macros/UDFs, translated scalar expressions, temporal precision chains, and measure-facing query `let`/`where`/`return` population SQL. Keep native-loaded and forced Python fallback DuckDB registrations parity-tested for both direct function calls and translated execution.
  CQL-04 SKEPTIC fresh rerun tightened two Boolean-only boundaries:
  public direct logical macros must not inherit DuckDB numeric/string
  truthiness, and legacy `logicalImplies` Boolean-text handling must reject
  malformed text such as `'yes'` as SQL NULL in Python fallback,
  native-loaded, and no-Python/browser-style C++ surfaces. Translator static
  logical validation must also classify clinical/static operands such as
  `Code { ... }`, `Quantity`, `Interval`, `Tuple`, and typed parameters before
  SQL generation so non-Boolean operands raise `TranslationError` instead of
  emitting raw SQL `AND`/`OR` over structured values. CQL-04 HISTORIAN fresh
  rerun also verified that `as Any` / `as System.Any` preserves the source
  type for logical validation, and that Patient-context `singleton from`
  query count/value subqueries carry `_pt.patient_id` correlation before
  population SQL evaluates query `let`/`where`/`return` logic. Regression
  coverage lives in `test_logical_parity.py`, `test_wasm_cpp_surface.py`, and
  `extensions/cql/test/sql/cql.test`.
- **CQL Temporal/Complex Type Boundaries**: **FIXED 2026-05-17 / CQL-03 EXPLORER**: Translated CQL `ToDate`/`ToDateTime` and `convert ... to Date/DateTime` route through the same spec-aware DuckDB macro/UDF surface as direct SQL calls. Do not reintroduce local SQLRaw/TRY_CAST validation that rejects valid partial precision (`2014`, `2014-01`) or preserves invalid calendar strings (`2024-02-30`). Ratio UDFs guard malformed internal JSON numeric values and return NULL consistently across native-loaded and forced Python fallback registration. Regression coverage lives in `fhir4ds/cql/duckdb/tests/integration/test_temporal_complex_parity.py`.
  CQL-03 SKEPTIC fresh rerun added two public-helper guardrails: DateTime/Time
  conversion helpers reject offsets past `+/-14:00` such as `+14:01`, and
  JSON-shaped Quantity/Ratio internals require JSON-numeric Decimal `value`
  fields rather than numeric strings. Native Ratio value/unit helpers must
  validate numerator/denominator as full Quantity components before returning
  partial values or units. Keep Python fallback, native-loaded registration,
  no-Python C++ SQL assertions, and temporal-complex parity tests aligned.
  CQL-03 HISTORIAN fresh rerun tightened translated DateTime constructor
  lowering: the `timezoneOffset` component is Decimal hours, so literal values
  must format as valid ISO `(+|-)hh:mm` with minute carry (`13.999` ->
  `+14:00`), reject values outside `+/-14:00`, and reject non-Decimal literals
  such as `true` or `'1'` instead of coercing or dropping the offset.
  CQL-03 EXPLORER fresh rerun added constructor expression guardrails:
  statically known Boolean/String Date/DateTime/Time component expressions must
  raise translation errors, while runtime non-Integer components or non-numeric
  DateTime timezone offsets return SQL NULL instead of using DuckDB implicit
  Boolean/String casts. Keep native-loaded and forced Python fallback coverage
  together in `test_temporal_complex_parity.py`.
- **CQL Primitive Conversion Boundaries**: **FIXED 2026-05-17 / CQL-01 SKEPTIC+EXPLORER**: Public CQL DuckDB connections must agree between native-loaded registration and forced Python fallback for primitive conversions. `ToInteger`/`ConvertsToInteger` and `ToLong`/`ConvertsToLong` accept Boolean and exact integer strings only; decimal-looking strings such as `1.0` and `1.5` return null/false instead of rounding or raising. `ToDecimal`, `ToBoolean`, and `convert ... to <primitive>` must use spec-aware macros/UDFs rather than generic DuckDB `TRY_CAST`, and invalid conversions return NULL/false without throwing. Keep `test_primitive_parity.py`, conversion parity tests, and `test/sql/cql.test` aligned when changing registration or conversion helpers.
- **CQL Primitive `is`/`as` Assertions**: **FIXED 2026-05-17 / CQL-01 HISTORIAN+EXPLORER**: Primitive `as` is a runtime type assertion, not conversion. Mismatched assertions (`5 as String`, `'5' as Integer`, `true as Integer`, `5L as Integer`) must return NULL while matching primitive types and `as Any` preserve the input. Dynamic FHIR/measure values can arrive as `VARCHAR`, so guarded `TRY_CAST` is required for typed numeric/boolean SQL results. Direct FHIR choice values must use FHIRPath `type().name` instead of SQL text shape, and materialized primitive definitions must preserve/infer `definition_meta.cql_type` for later `is`/`as` checks. Keep translator tests, DQM measure probes, and native-loaded/forced-fallback DuckDB execution parity together.
- **CQL Clinical Type Boundaries**: **FIXED 2026-05-17 / CQL-02 SKEPTIC+HISTORIAN**: Translator-generated Code selectors and named code references must use JSON-shaped CQL Code values rather than legacy `system|code` strings. `ToConcept(Code)`, clinical `is`, and clinical `as` rely on that shape. `ValueSet` and `CodeSystem` references stay structured in value/type contexts (`id`, `name`, optional `version`), and materialized definitions must preserve clinical `definition_meta.cql_type`. `Code` and `Concept` are distinct and are not `Vocabulary`; only `ValueSet` and `CodeSystem` satisfy `Vocabulary`. Clinical `as` mismatches return NULL only when the source clinical type is statically known; dynamic FHIR values such as `Observation.value as Concept` must fall through to runtime matching so valid CodeableConcept comparisons are not erased. Before calling `in_valueset`, unwrap structured ValueSet JSON to the canonical URL, including function-inlined parameters and fluent builders such as `hasPrincipalDiagnosisOf`/`hasPrincipalProcedureOf`. Keep native-loaded and forced Python fallback DuckDB parity tests plus DQM measure probes together for clinical type changes.
  CQL-02 fresh rerun SKEPTIC tightened this surface further: clinical parameter
  `cql_type` metadata must feed static `is`/`as`; `ToConcept(Code)` propagates
  `Code.display` to `Concept.display`; `ToConcept` rejects non-Code JSON and
  supports `List<Code>` through list-aware registration; and static null
  terminology membership lowers to false before ValueSet/CodeSystem dispatch.
  CQL-02 HISTORIAN rerun added ValueSet `codesystems { ... }` support: the
  parser accepts non-empty CodeSystem override lists, and structured
  `System.ValueSet` JSON preserves those overrides as `codesystems` entries
  with referenced CodeSystem id/name/version.
- **CQL Structural Type Operators**: **FIXED 2026-05-17 / CQL-05 SKEPTIC+HISTORIAN+EXPLORER**: `is`, `as`, and `convert` must validate unknown type targets, handle `List<T>`, `Interval<T>`, `Choice<T...>`, and `Tuple { ... }` specifiers, and preserve exact static identity for List, Interval, Ratio, Date, DateTime, Time, and Tuple aliases. `as Quantity` must keep Quantity-shaped SQL so `quantity_compare` remains unit-aware; scalar numeric fallback is only for optimized CTE values and must not override incompatible JSON Quantity units. Preserve `CQLMessage` through structural `as Interval<T>`, keep dynamic FHIR `as Concept`/`as Code` runtime matching, and allow SQL CASE sources from choice `as` casts to feed FHIRPath property navigation. `Children()`/`Descendants()` need typed primitive transport, including temporal and Long values, when exposed through `VARCHAR[]` so downstream `is`/`as` and `List<T>` checks do not coerce strings or erase identity. `convert <Quantity> to String` should share the `QuantityToString` path used by `ToString(<Quantity>)`; `convert List<Code> to Concept` and `convert Concept to List<Code>` must remain registered UDF surfaces. Forced Python fallback tests must manually register Python FHIRPath UDFs and assert `fhirpath_predicate` is absent. FHIR choice-field `value.is/as(Type)` parity belongs in both native-loaded and forced fallback coverage. `as Concept` over FHIR resource properties must preserve resource/path behavior for `in_valueset` and `coding_matches`, not blindly replace the resource with a direct JSON value.
  Fresh CQL-05 SKEPTIC rerun (2026-05-30) tightened the structural boundary further: `convert ... to Any` preserves source runtime type metadata for later assertions, nested `convert ToQuantity(...) to String` must still call `QuantityToString`, typed-null composite `is` checks return false instead of SQL NULL, and `QuantityToString` formats JSON integer quantities with the CQL-required decimal point (`5.0 'mg'`).
  Fresh CQL-05 EXPLORER rerun (2026-05-30) added two more invariants: structural traversal translation must recursively preserve typed transport markers for nested tuple/list Date, DateTime, Time, and Long values before `cqlChildren`/`cqlDescendants` flatten them, and function inlining must preserve `BinaryExpression.strict=True` so `cast` inside function bodies does not degrade to nullable `as`.
- **CQL Conversion Check Boundaries**: **FIXED 2026-05-17 / CQL-06 SKEPTIC; HISTORIAN follow-up found decimal representability gap**: `ConvertsTo*` helpers must distinguish CQL string formats from numeric overloads instead of stringifying all inputs. Boolean strings are only `true/t/yes/y/1` and `false/f/no/n/0`; decimal and quantity strings require at least one digit before an optional decimal point and do not allow exponent notation or leading/trailing whitespace. Decimal string conversion must also enforce implementation representability and CQL scale-8 behavior so `ConvertsToDecimal(x)` does not return true when `ToDecimal(x)` returns NULL or rounds extra fractional digits. Date/DateTime checks reject numeric values that merely stringify to partial dates, while native DateTime values remain acceptable for `ToDate`/`ConvertsToDate`. Python fallback and native-loaded public registration parity is covered in conversion-check/core tests, and direct native C++ `ToQuantity` uses the same quantity grammar.
  Fresh CQL-06 SKEPTIC rerun (2026-05-30) fixed private conversion macro helper
  registration: `ToDate`, `ToDateTime`, and `ToTime` private helper setup may
  tolerate duplicate-registration catalog conflicts, but unexpected failures
  must raise visibly instead of creating macros that point at missing helpers.
  Fresh CQL-06 HISTORIAN rerun (2026-05-30) tightened Quantity/Ratio conversion
  checks: public `ToQuantity` and `ConvertsToQuantity` reject Quantity strings
  outside the implementation `DECIMAL(38, 8)` range/scale, `ConvertQuantity`
  validates JSON Quantity input before unit conversion, and
  `ConvertsToQuantity` accepts valid Ratio JSON because `ToQuantity(Ratio)` is
  supported. Keep this strictness at public conversion boundaries, not in
  generic `parse_quantity_json`; translated measure arithmetic can generate
  Quantity JSON with more than 8 fractional digits before later comparison, and
  over-tightening that parser regresses CMS832 DQM accuracy.
  Fresh CQL-06 EXPLORER rerun (2026-05-30) found that String conversion checks
  were too broad: `ConvertsToString` and generic translated `ToString` must
  reject structural List/Tuple/JSON values instead of falling through to
  DuckDB `CAST(... AS VARCHAR)`. Quantity and Ratio string conversion remain
  routed through `QuantityToString` and `RatioToString`.
- **CQL Conversion Function Boundaries**: **FIXED 2026-05-30 / CQL-07 SKEPTIC**:
  translated `ToString`, `ConvertsToString`, and `convert ... to String` must
  reject statically known unsupported CQL values even when their SQL transport
  is `VARCHAR` JSON. Interval and clinical Concept values are not CQL String
  conversion overloads; lower them to NULL/false instead of serializing
  implementation JSON. Keep `test_conversion_function_parity.py` and fresh
  CQL-07 probes aligned when changing String conversion routing.
  CQL-07 EXPLORER found that Quantity-producing definition aliases are the
  opposite special case: aliases produced by `ToQuantity(...)`, including
  through inlined user-defined functions, must keep `Quantity` metadata and
  scalar `value` columns so `ToString(Q)` and `convert Q to String` use
  `QuantityToString` rather than generic `ToString` over internal JSON.
- **CQL Quantity Conversion Units**: **FIXED 2026-05-17 / CQL-07 SKEPTIC**: `ToQuantity` and `ToRatio` string parsing must reject invalid unit designators instead of packaging arbitrary text into Quantity JSON. The CQL string quantity format requires a valid case-sensitive UCUM unit or CQL calendar duration keyword; `ConvertsToQuantity` and `ConvertsToRatio` must return false when the corresponding conversion would return NULL. Keep Python and direct native C++ parsers aligned because public native-loaded registration can shadow direct C++ behavior.
- **CQL Ratio String Conversion**: **FIXED 2026-05-17 / CQL-07 HISTORIAN**: `ToString(Ratio)` and `convert Ratio to String` in translated CQL must call `RatioToString` and emit CQL round-trippable `<quantity>:<quantity>` text, not the internal Ratio JSON object. Keep `RatioToString` registered in both Python fallback and native C++ DuckDB paths, and keep direct parity tests aligned.
- **CQL Conversion Static Aliases and Concepts**: **FIXED 2026-05-17 / CQL-07 EXPLORER**: Conversion functions and `convert ... to ...` over literal/static definition aliases must inline the static source expression instead of generating `_pt.patient_id` CTE lookups. `convert List<Code> to Concept` must pass a `VARCHAR[]` list of Code JSON values to `ToConceptFromList`, including direct `Code { ... }` instance literals. Native C++ and Python fallback `ToConcept` must flatten JSON arrays of Code objects and reject primitive JSON consistently.
- **CQL Nullological Operators**: **FIXED 2026-05-17 / CQL-08 EXPLORER**: Infix `is true`/`is false` and direct `IsTrue()`/`IsFalse()` must use Boolean-only CQL semantics without inheriting SQL truthiness for numeric/string literals. Dynamic FHIR Boolean paths are physically transported through `fhirpath_bool` before the helper predicate so Patient/Resource Boolean fields still evaluate correctly in population SQL. `Coalesce` scalar overloads are limited to 2 through 5 arguments; zero, one-scalar, and more-than-five scalar calls fail translation, while the single-list overload remains valid.
  CQL-08 SKEPTIC rerun tightened the same boundary: public direct DuckDB
  `Coalesce` must also reject one-scalar and more-than-five scalar calls, and
  translated `Coalesce(List<T>)` must accept query-produced lists and
  query-list aliases, returning the first non-null row rather than treating the
  single query argument as an invalid scalar overload or missing CTE.
  CQL-08 HISTORIAN rerun verified no additional defects across the official
  XML cases, direct DuckDB helper surface, static typed Quantity/Code/Concept
  values, query-produced Boolean/DateTime lists, and dynamic `Patient.active`
  true/false/missing population SQL in native-loaded and forced Python
  fallback registrations. Keep the scalar-vs-list `Coalesce` distinction
  explicit: a rendered SQL `COALESCE(NULL, NULL, NULL, NULL, NULL, 'x')`
  generated from one CQL list argument is still the list overload, not an
  invalid six-scalar call.
  CQL-08 EXPLORER rerun found three final composition boundaries. Public
  direct `Coalesce` must preserve Boolean `T` for scalar and list overloads;
  when DuckDB transports those values as VARIANT, `IsTrue`/`IsFalse` may accept
  VARIANT JSON `true`/`false` but must continue rejecting string and numeric
  truthiness. Translated Quantity-producing `Coalesce`, including query-list
  forms, must keep Quantity type evidence so comparisons use
  `quantity_compare`. Dynamic FHIR Boolean defaults such as
  `Coalesce(Patient.active, false)` must route the FHIR path through
  `fhirpath_bool`, not numeric or text coercion. When a whole Quantity
  expression is followed by `.value`, the result is Decimal; do not propagate
  Quantity type through `Quantity.value` or DQM formulas such as CMS832 eGFR
  can build mixed `list_value(VARCHAR, INTEGER)` expressions.
- **CQL Comparison Operators**: **FIXED 2026-05-17 / CQL-09 HISTORIAN**: Date/DateTime imprecision in public comparison helpers must stay strict and return NULL when precision is uncertain; interval boundary helpers explicitly opt into Date-to-DateTime endpoint promotion for DQM day-window behavior. Decimal literal equivalence follows least-precise-operand rounding, and Quantity equivalence uses `quantityCompare(..., '~')` with calendar-vs-definite duration semantics aligned in Python fallback and native C++.
  CQL-09 SKEPTIC rerun fixed three fragile comparison boundaries: `between`
  now applies an explicit null-argument guard before SQL `AND`,
  interval-valued `between` lowers to included-in an inclusive interval, and
  Ratio equality/equivalence uses Ratio/Quantity semantics through
  `ratioCompare` rather than raw JSON/string equality.
  CQL-09 HISTORIAN fresh rerun added the ordered-comparison guardrail:
  `<`, `<=`, `>`, and `>=` are only defined for Integer, Long, Decimal,
  Quantity, Date, DateTime, Time, and String. Statically known Ratio, List,
  Tuple, Interval, Code/Concept, ValueSet, and CodeSystem operands must return
  SQL NULL at the translator boundary instead of falling through to DuckDB
  text/list/struct ordering. `between` inherits this behavior through its
  lowered `>=` and `<=` checks.
  CQL-09 EXPLORER fresh rerun found that tuple equality must recursively use
  semantic CQL element equality, not raw SQL equality, so Quantity and Ratio
  tuple fields still route through `quantityCompare`/`ratioCompare`. Static
  tuple fields introduced by list/query aliases and `singleton from` list
  values must preserve their Quantity/Ratio type evidence for comparison
  lowering; tuple-list aliases expose the tuple JSON value itself, not an
  `.resource` field.
- **CQL Arithmetic Operators Part 1**: **FIXED 2026-05-31 / CQL-10 SKEPTIC**:
  Python fallback Quantity arithmetic must not coerce malformed JSON `value`
  members through `float()`. String and Boolean Quantity values are invalid
  numeric evidence and must become SQL NULL across direct helpers
  (`quantityValue`, `quantityAdd`, `quantityDivide`, `quantityAbs`) and
  translated dynamic FHIR expressions such as `(O.value as Quantity) + 1 'mg'`
  or `(O.value as Quantity) / 2`. Keep this parity-tested with native-loaded
  registration because the C++ parser already rejects non-numeric JSON values.
  CQL-10 HISTORIAN found two public arithmetic boundary gaps: omitted
  `HighBoundary`/`LowBoundary` precision must use the spec default instead of
  emitting/binding a missing one-argument helper, and `Log` is only the
  two-argument base-log operator. Do not map one-argument `Log(x)` to `Ln(x)`;
  natural log must stay on the `Ln` surface, while direct `Log(x, base)` must
  work in forced Python, native-loaded, and no-Python/browser-style runtimes.
  The fix uses private Python boundary UDFs behind default-argument macros and
  C++ one-argument boundary overloads; keep both paths covered when changing
  boundary registration.
  CQL-10 EXPLORER found that translated numeric `HighBoundary`/`LowBoundary`
  must normalize the public helper output through `VARCHAR` before final
  numeric `TRY_CAST`, because the Python default-precision macro returns a
  DuckDB `UNION(VARCHAR, DOUBLE)` transport. Direct helper output can look
  numeric while `TRY_CAST(HighBoundary(decimal) AS DOUBLE)` returns NULL.
- **CQL Arithmetic Operators Part 2**: **FIXED 2026-05-18 / CQL-11 SKEPTIC+HISTORIAN+EXPLORER**: Direct arithmetic helper calls are part of the public surface, not just translator internals. Keep native-loaded, forced Python fallback, and C++-only/browser-style macro/UDF registrations parity-tested for `mathRound`, `Power`, quantity modulo/truncated divide, predecessor/successor, direct macro `Div`, and max/min temporal constants. Current CQL Reference `Round` examples require negative half ties to round away from zero (`Round(-0.5) = -1`), and null precision is precision `0`; keep SQL macros, Python fallback, native C++, no-Python tests, and the local arithmetic conformance XML aligned to that normative text. `Power` must NULL for NaN/infinite/unrepresentable results. Compatible-unit Quantity `mod` and truncated `div` convert RHS into LHS units before truncation and preserve the LHS unit. Direct SQL predecessor/successor helpers return NULL at representational boundaries for row resilience, but translated static temporal boundary underflow/overflow remains invalid for official CQL conformance. Maximum/minimum DateTime literals use the official `Z` suffix; Time literals retain `T` and millisecond precision. Dynamic FHIR `value[x]` operands in numeric-only Part 2 operations (`div`, `Power`/`^`, `Round`, `Truncate`) must use `fhirpath_number`, never `fhirpath_text` plus SQL coercion. Apply static representational boundary folding for unary negate and Decimal predecessor/successor at min/max, validate direct C++ Time helper inputs such as `T25:00`, and ignore DateTime timezone offset digits when computing `Precision`. Predecessor/successor over partial Date/DateTime/Time values steps by the lowest specified precision and preserves lexical precision. Mixed scalar/Quantity `mod` and `div` convert scalar operands to unit `1` Quantity JSON before UDF dispatch; do not emit `parse_quantity(<number>)`. Fresh CQL-11 SKEPTIC rerun found another predecessor/successor boundary: integer-authored Quantity values step by 1, decimal-authored Quantity values step by `1e-8`, and malformed Quantity JSON such as numeric strings must return SQL NULL. CQL-11 EXPLORER added three final guardrails: `maximum Quantity` and `minimum Quantity` return exact DECIMAL-backed Quantity JSON with unit/code `1`, unsupported maximum/minimum types raise translation errors instead of lowering to SQL NULL, and literal-list query sources plus single-Quantity `singleton from` lists must preserve raw Quantity JSON spelling so `from { 1 'cm' } Q return predecessor of Q` and `predecessor of singleton from { 1 'cm' }` keep integer-authored step semantics. Public C++-only `predecessorOf/successorOf(VARCHAR)` treats numeric text as Decimal; typed Integer/Long use the BIGINT overloads.
- **CQL String Operators**: **FIXED 2026-05-18 / CQL-12 SKEPTIC+HISTORIAN**: String operators must preserve CQL null/boundary semantics across translated SQL, native-loaded DuckDB registration, forced Python fallback, and no-Python/browser-style macro surfaces. `Combine`/`CombineSep` over an empty non-null filtered list return NULL. `Substring` returns NULL for null/negative/at-or-past-end starts and null/negative lengths. `StartsWith` and `EndsWith` are exact string predicates; translated CQL must call those macros, not SQL `LIKE`, because `%` and `_` are literal characters. String bracket indexing must route through `Indexer`, not list extraction, so at-end/out-of-range string indexes return NULL. CQL regex operators use single-line mode: `Matches` and `SplitOnMatches` pass regex option `s`, and `ReplaceMatches` uses `gs` while preserving CQL `$1` capture references and escaped literal dollars. Deprecated Python string UDFs return NULL for null search operands and invalid substring/regex/replace boundaries rather than raising.
  Fresh CQL-12 SKEPTIC rerun on 2026-05-31 added a type-discipline guardrail:
  string-only operators must not inherit DuckDB's numeric-to-string coercion.
  Direct public `Concatenate`/`Concat` and `Combine`/`CombineSep` macros raise
  for non-String operands or non-`List<String>` sources, and translated static
  CQL such as `Concatenate(1, 'x')`, `1 & 'x'`, `'a' + 2`, or `Combine({1,2})`
  raises `TranslationError` instead of generating SQL that returns `'1x'`,
  `'a2'`, or `'12'`. Check direct macro type guards before null-return
  branches so typed SQL nulls such as `CAST(NULL AS INTEGER)` and
  `CAST(NULL AS INTEGER[])` cannot bypass CQL signature validation.
  Fresh CQL-12 HISTORIAN rerun on 2026-05-31 added the direct public
  `Substring(string, start, length)` overload to the macro surface. Keep
  two-argument `Substring`, three-argument `Substring`, and compatibility
  `SubstringLen` covered on forced Python fallback, native-loaded, and
  no-Python/browser-style registrations; explicit null or negative length must
  return SQL NULL, while omitted length means "to end of string".
  Fresh CQL-12 EXPLORER rerun on 2026-05-31 added two composition guardrails:
  `Combine` over query-produced `List<String>` values must aggregate the query
  rows into a DuckDB list before calling `Combine`/`CombineSep`, and CQL strings
  embedded into generated FHIRPath predicates (notably `ext(element, url)`)
  must use FHIRPath backslash escaping, not SQL quote doubling. A URL containing
  an escaped quote must remain one string literal inside `extension.where(...)`
  and must not turn into executable predicate text.
- **CQL Date/Time Operators Part 1**: **FIXED 2026-05-31 / CQL-13 SKEPTIC**:
  Duration uncertainty and difference uncertainty are intentionally different.
  `difference` counts boundary crossings and may use the full high boundary of
  an imprecise end value, but `duration` counts whole calendar periods and must
  cap the uncertain end at the requested precision. The current CQL Reference
  example `months between @2012-01-02 and @2012` is `Interval[0, 10]`, while
  `difference in months ...` remains `Interval[0, 11]`. Keep
  `cqlDurationBetween` aligned across forced Python fallback, native-loaded,
  and no-Python/browser-style C++ surfaces; regression coverage lives in
  `test_datetime_part1_parity.py`, `test_wasm_cpp_surface.py`, and the fresh
  `.temp/qa/cql13_skeptic_probe.py`.
  Fresh CQL-13 HISTORIAN probing fixed another public-surface guard:
  `cqlDurationBetween` / `cqlDifferenceBetween` helpers must reject unsupported
  precision/unit strings such as `bogus` instead of falling through to day-based
  defaults. Keep invalid-unit NULL behavior aligned across forced Python
  fallback, native-loaded, and no-Python/browser-style C++ surfaces.
  Fresh CQL-13 EXPLORER probing fixed translated component extraction for
  timezone-suffixed DateTime/Time values with no millisecond precision:
  `millisecond from @2024-01-01T10:00:00+05:00` must return SQL NULL rather
  than slicing the offset text and raising a cast error. Numeric component
  extraction should route through the validated `dateComponent` helper instead
  of ad hoc substring positions.
- **CQL Date/Time Operators Part 2**: **FIXED 2026-05-18 / CQL-14 HISTORIAN**: One-argument `Time(hour)` is a component constructor and must return hour-precision CQL time text such as `T12`; keep it distinct from lowercase `time from <DateTime>` extraction. No-Python/browser-style C++ `dateSubtractQuantity` must match native-loaded and forced Python fallback for valid fractional week subtraction from day-precision Date values: `@2024-01-15 - 1.5 weeks` truncates to one week and returns `2024-01-08`. Regression coverage lives in `test_datetime_part2_parity.py` and `test_wasm_cpp_surface.py`.
- **CQL Date/Time Operators Part 2**: **FIXED 2026-05-18 / CQL-14 EXPLORER**: Public date quantity helpers return SQL NULL for malformed Quantity JSON, missing/null/string/Boolean/non-finite `value`, unsupported units, and huge values. Python fallback `dateAddQuantity`/`dateSubtractQuantity` must stay aligned with no-Python/browser-style C++ and must not coerce numeric strings or treat a missing `value` as zero. Valid arithmetic overflow remains a translated CQL invalid-expression path for official conformance.
- **CQL Date/Time Operators Part 2**: **VERIFIED 2026-05-31 / CQL-14 SKEPTIC**: Fresh current-clock and precision probes found no new remediation needed. Keep `Now() = Now()`, `Today() = Today()`, `TimeOfDay() = TimeOfDay()`, time-only `same` comparisons, invalid `week` precision NULLs, timezone-normalized same-second checks, `Time(12, null as Integer, 0, 0)` NULL behavior, and `DateTime(2014) - 25 months = @2012T` covered across forced Python, native-loaded, and no-Python/browser-style C++ runtime surfaces.
- **CQL Date/Time Operators Part 2**: **FIXED 2026-05-31 / CQL-14 EXPLORER**: Precision comparisons over DateTime timezone offsets normalize only at hour/minute/second/millisecond precision. Year/month/day precision compares local DateTime components, so `@2024-01-01T00:30+01:00 same day as @2024-01-01T00:30Z` is true. Time-only values such as `T00:30+01:00` must not be normalized through DateTime epoch math; compare Time components directly and keep forced Python fallback, native-loaded, and no-Python/browser-style C++ parity coverage in `test_datetime_part2_parity.py` and `test_wasm_cpp_surface.py`.
- **CQL Interval Operators Part 1**: **FIXED 2026-05-18 / CQL-15 SKEPTIC+HISTORIAN+EXPLORER**: `intervalStart`/`intervalEnd` expose CQL effective boundaries for open endpoints, and interval equality/equivalence compares those semantic boundaries instead of raw JSON or authored open/closed flags. Translated interval `=`, `!=`, `~`, and `!~` must call interval-aware helpers. Precision-aware interval predicates over partial Date/DateTime values return NULL when the relationship is unknown, not false/true, and `intervalStartsSame`/`intervalEndsSame` return NULL when the compared boundary is missing. Quantity interval bounds and points must retain Quantity shape and use unit-aware comparison, so `Interval[1 'g', 2 'g'] contains 1500 'mg'` is true across Python fallback, native-loaded, and no-Python C++ surfaces. Interval-producing set-operation UDFs (`intervalExcept`, `intervalIntersect`, `intervalUnion`) remain interval expressions for nested downstream operators such as `(A except B) contains point`; translator dispatch must not fall back to generic DuckDB `system.contains`. Keep forced Python fallback, native-loaded registration, and no-Python/browser-style direct C++ helper coverage together.
  Fresh CQL-15 SKEPTIC rerun on 2026-05-31 added three guardrails. `expand`
  over Quantity intervals must parse Quantity-valued `per` arguments such as
  `1 'g'`, preserve Quantity JSON in expanded intervals/points, and convert
  compatible units rather than reducing output to numeric-only intervals.
  Quantity open-bound `end of` and `intervalExcept` split boundaries must use
  CQL predecessor/successor semantics without rounding away the `1e-8` Decimal
  step. Direct `intervalContains(Interval<Quantity>, scalar)` returns SQL NULL;
  translated CQL is responsible for passing FHIR `valueQuantity` JSON, not
  bare `valueQuantity.value`, into `Interval<Quantity>` membership.
  Fresh CQL-17 EXPLORER follow-up closed review-35: supplied malformed
  `expand`/`expand_points` `per` Quantity JSON must return SQL NULL, while
  omitted or SQL NULL `per` remains the only default-step path.
  Fresh CQL-15 HISTORIAN rerun on 2026-05-31 added the null-container rule:
  `contains` returns false when the interval/list container is null, while a
  null point remains SQL NULL; `in` returns false when the interval/list
  argument is null. Keep `null contains 5`, `5 in (null as Interval<Integer>)`,
  Fresh CQL-15 HISTORIAN fresh run on 2026-07-02 extended the same rule to
  the both-null case: `(null as Interval<T>) contains (null as T)` returns
  False (first-arg-null short-circuits before second-arg-null). Three
  layers required alignment: the translator `_translate_contains_op`
  null-check order, the Python `intervalContains` UDF first-arg-null
  short-circuit, and the C++ `IntervalContainsFunc` first-arg-null
  short-circuit. The plain `intervalContains` UDF surface was previously
  inconsistent with `intervalContainsPrecise` (which already returned
  False for null first arg); both surfaces are now aligned.
  The same fresh run also closed two CQL §19.3/§19.11 precision-handling
  gaps: `Interval<T> contains <precision> of <point>` and
  `<point> in <precision> of <interval>` previously dropped the precision
  wrapper for translated Date/DateTime/Time intervals and fell back to
  raw SQL `>=`/`<=` comparisons. Partial-precision Date bounds (e.g.,
  `@2024` year-only) collapsed to raw string comparisons returning False
  instead of NULL. The translator now dispatches to
  `intervalContainsPrecise` when the interval is a recognized interval
  expression. The raw-SQL fallback remains for dynamic FHIR Period values
  per CQL-16 EXPLORER.
  untyped `Interval[null, null] contains 5`, direct `intervalContains(NULL,
  '5')`, and `intervalContainsPrecise(NULL, point, precision)` covered across
  forced Python fallback, native-loaded registration, and no-Python/browser C++.
- **CQL Interval Operators Part 2**: **FIXED 2026-05-19 / CQL-16 SKEPTIC**: `intervalIntersect` must choose finite bounds when intersecting one-sided closed-null unbounded intervals; `Interval[null as Integer, 5] intersect Interval[3, 7]` and `Interval[3, null as Integer] intersect Interval[1, 5]` both yield `[3, 5]`. Open null bounds are different: official CQL conformance expects `Interval[1, 10] intersect Interval[5, null)` to preserve the unknown open high as `Interval[5, null)`. C++ `intervalMeets*`, `intervalOnOrAfter`, and `intervalOnOrBefore` must use effective Start/End boundaries rather than authored raw open/closed endpoints. Partial Date/DateTime/Time boundaries meet at authored precision, so `Interval[@T03, @T04] meets Interval[@T05, @T06]` is true across forced Python fallback, native-loaded registration, and no-Python/browser-style C++.
- **CQL Interval Operators Part 2**: **FIXED 2026-05-19 / CQL-16 HISTORIAN**: Public no-Python/browser-style C++ `intervalEquivalent` must handle SQL NULL arguments explicitly: both NULL operands return true, exactly one NULL operand returns false. Interval JSON bound parsing treats year-only strings such as `2014` as temporal in interval-bound and precision-aware point contexts so partial Date/DateTime uncertainty returns NULL instead of false. Do not apply a runtime `CQLPrecision` guard across every translated resource interval bound for `overlaps <precision> of`; it regresses DQM.
  Fresh accepted CQL-16 SKEPTIC rerun (2026-05-31) fixed two interval part 2
  regressions. `intervalIntersect` in forced Python/native-loaded paths uses
  effective open endpoints when deciding whether a half-open result is empty;
  `Interval[1, 5) intersect Interval[5, 7]` is NULL, not `[5, 5]`.
  `intervalOverlapsBefore` / `intervalOverlapsAfter` propagate an unknown
  `intervalOverlaps(...)` result instead of converting it to false, including
  partial Date/DateTime/Time bounds and incompatible Quantity units. Keep
  `.temp/qa/cql16_skeptic_probe.py` with translated CQL plus forced Python,
  native-loaded, and no-Python C++ checks. Do not rely on quarantined
  premature artifacts as evidence.
  Fresh accepted CQL-16 HISTORIAN rerun (2026-05-31) found no new defects.
  Keep the accepted historian probe pattern broad: official included-in
  precision examples, half-open empty `intersect`, Quantity intersect with
  unit conversion, hour/month precision `meets`, semantic interval
  equality/equivalence, point-vs-interval on-or-before/on-or-after overloads,
  partial temporal unknowns, and incompatible Quantity overlap unknowns across
  forced Python fallback, native-loaded registration, and no-Python C++.
  Fresh accepted CQL-16 EXPLORER rerun (2026-05-31) fixed translated dynamic
  FHIR point precision uncertainty without replacing the DQM-proven overlap
  decomposition. `Observation.effective` and similar FHIR choice values may be
  concrete Period values or scalar Date/DateTime strings at runtime; the
  decomposed `overlaps <precision> of` SQL must return NULL when a runtime
  bound has fewer digits than the requested precision. This keeps partial
  values such as `effectiveDateTime: "2014"` returning SQL NULL for
  day-precision overlap against June 2014 intervals while concrete Period
  values still evaluate true/false across forced Python fallback,
  native-loaded registration, no-Python C++, and DQM. The guard must use raw
  `SQLInterval` / `intervalFromBounds` low/high peers when available so active
  unbounded intervals with a null high endpoint still evaluate normally.
- **CQL Numeric Lexer Boundaries**: **FIXED 2026-05-17 / CQL-01 EXPLORER**: No-whitespace junk after numeric literals is invalid. Reject `1LL`, `1.0L`, and `1day` in the lexer; whitespace-separated tokens remain query grammar responsibility.
- **Duration Operations**: `MonthsBetween` and `WeeksBetween` miscalculate durations due to boundary vs absolute math. **FIXED v0.0.4**: MonthsBetween now uses age_in_months (complete months), WeeksBetween uses epoch_millis (time-aware complete weeks).
- **Precision Retrieval**: `CQLPrecision` yields string lengths instead of CQL standard precision enums. **FIXED v0.0.4**: Changed return type from BIGINT to VARCHAR, now returns precision names ("Year", "Month", "Day", "Hour", "Minute", "Second", "Millisecond").
- **Exp/Ln Overflow Behavior**: `math_exp` threw `std::runtime_error` on `std::isinf(result)` (e.g. `Exp(1000)`, `Exp(710)`); `math_ln` threw on `val == 0` (e.g. `Ln(0)`, `Ln(-0)`). **FIXED 2026-07-01 / CQL-10 EXPLORER**: CQL v1.5.3 §16 normative mandates "operations that cause arithmetic overflow or underflow ... will result in null, rather than a run-time error." Both functions now return `NullOpt<std::string>()` on overflow/zero. Mirror fix in `fhir4ds/cql/duckdb/udf/math.py` (`mathExp`, `mathLn`) and `fhir4ds/cql/duckdb/macros/math.py` (`Exp`, `Ln` SQL macros). Conformance runner at `conformance/scripts/run_cql.py:396-407` updated to accept NULL as spec-compliant for `invalid="true"` cases. Native extension rebuilt (md5sum `70c6c3169154b7e05e7f907dd3f662d4`). Full conformance 2822/2822 unchanged.
- **CQL-13 EXPLORER DurationBetween year-target uncertainty collapse**: **FIXED 2026-07-01 / CQL-13 EXPLORER**: `DurationHighBoundaryValue` in `extensions/cql/src/cql_extension.cpp:3171-3228` had a chain of conditions `current_rank < PrecisionRank(Month) <= target_rank` etc. The first condition required `target_rank >= Month`, so year-target (`target_rank = Year = 0`) never had its operand's missing month/day maxed. Result: `years between @2012-06-01 and @2014` returned `'1'` instead of `Interval[1, 2]`. The official conformance test `years between DateTime(2005) and DateTime(2010) // Interval[4, 5]` masked the bug because it uses **symmetric** operand precisions (both year-prec) where the START operand's high boundary provides the variability. Fix: drop the upper-bound constraint on the first condition (`current_rank < Month` alone). Same fix mirrored in Python `fhir4ds/cql/duckdb/udf/datetime.py:249-296`. Native extension rebuilt (md5sum `b7e82f5dda90b201e2b611cdfc844d5e`).
- **CQL-13 EXPLORER cql_timezone_offset missing Z suffix**: **FIXED 2026-07-01 / CQL-13 EXPLORER**: `cql_timezone_offset` in `extensions/cql/src/cql/boundary.cpp:877` only searched for `+HH:MM` or `-HH:MM` suffixes by scanning backward for `+` or `-` characters. CQL §DateTime ISO-8601 representation includes `Z` as the UTC designator (equivalent to `+00:00`), so `timezoneoffset from @2024-05-15T10:30:45.500Z` returned NullOpt instead of `0.0`. Fix: early-return `Optional<double>(0.0)` when the value ends with `Z`. Same fix mirrored in Python `fhir4ds/cql/duckdb/udf/math.py:920-921`. Native extension rebuilt (same md5sum as above).
- **CQL-16 HISTORIAN Interval equality mixed-precision uncertainty**: **FIXED 2026-07-02 / CQL-16 HISTORIAN**: CQL 1.5.3 §Equal (interval) + §Equal (Date/DateTime/Time) require that mixed-precision temporal bounds make interval equality uncertain (null). `Interval[@2014, @2014] = Interval[@2014-01-01, @2014-12-31]` previously returned False (certain unequal) instead of None. Root cause: `Interval::operator==` used `BoundValue::compare` which calls `DateTimeValue::compare_at_precision(Millisecond)` always at max precision without honoring the operands' actual `precision` field. Fix: added `bound_equals_nullable(left, right)` free function in `extensions/cql/src/cql/interval.cpp:441-464` returning `Optional<bool>` (NullOpt for uncertain), mirroring the existing `compare_interval_order_nullable` pattern. Added `Interval::equals_nullable(other)` method in `interval.cpp:898-933` (declaration in `interval.hpp:78-80`). Updated `IntervalEqualsFunc` UDF (`cql_extension.cpp:1455-1468`) to set SQL NULL on NullOpt. Updated `IntervalEquivalentFunc` UDF (`cql_extension.cpp:1475-1502`) to return False on NullOpt (per Equivalent always-true-or-false rule). Same fix mirrored in Python `fhir4ds/cql/duckdb/udf/interval.py` (new helpers `_interval_bound_equals_nullable` and `_equivalent_nulls_ok`; rewritten `intervalEquals` and `intervalEquivalent`). Native extension rebuilt (md5sum `c7bdef8fa7ac48a90307e61fc6bfab61`). Full conformance 2822/2822 unchanged. Official CQL conformance suite (`CqlIntervalOperatorsTest.xml`) only tests same-precision Integer intervals for equality so doesn't exercise this case.

### NOT A BUG Registry
*Behaviors that look like bugs but are spec-compliant or intentional design decisions.*

- **Interval-point `properly includes` endpoints**: Preserve strict boundary
  behavior for the active official CQL conformance target. Although current CQL
  Reference prose can be read as endpoint-inclusive when the interval is not a
  unit interval, the bundled official XML cases `TimeProperContainsFalse` and
  `TimeProperInFalse` expect boundary points to return `false`; changing this
  regresses conformance from 1706/1706.
- **CQL `Coalesce` list lowering with more than five SQL arguments**:
  Translator SQL may render a single CQL list argument such as
  `Coalesce({null, null, null, null, null, 'x'})` as a pure SQL `COALESCE`
  with six SQL arguments. This is intentional because the CQL scalar arity cap
  applies to authored scalar arguments, while the single `List<T>` overload has
  no five-element maximum.

## CQL-14 EXPLORER Iteration 1 (Date/Time Operators Part 2) — 2026-07-02

- **CQL Date/Time Operators Part 2**: **FIXED 2026-07-02 / CQL-14 EXPLORER**:
  CQL 1.5.3 §Add / §Subtract normative text: "For precisions above seconds,
  any decimal portion of the time-valued quantity is ignored." The
  triggering condition is the **quantity unit** (year/month/week/day/
  hour/minute are above seconds; second/millisecond are at-or-below
  seconds), not the input precision. `ApplyQuantityAtInputPrecision` at
  `extensions/cql/src/cql_extension.cpp:4693` only truncated decimal
  portions when the quantity unit was FINER than the input precision
  (`unit_rank > input_rank`). When unit and input were at the same
  precision (1.5 days onto a day-precision Date, 1.5 hours onto a
  minute-precision Time), the raw float bled through into `AddMilliseconds`
  calls. Fix: added rank-based truncation guard at the top of
  `ApplyQuantityAtInputPrecision`:
  ```cpp
  int second_rank = PrecisionRank(cql::DateTimeValue::Precision::Second);
  if (unit_rank >= 0 && unit_rank < second_rank) {
      value = static_cast<double>(static_cast<int64_t>(value));
  }
  ```
  This runs BEFORE the conversion-divisor path. Native C++ extension
  rebuilt (md5sum `5c5647a1a1acaf5e884dcfd2199e5a31`) and copied to
  `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`. Same fix mirrored
  in Python `fhir4ds/cql/duckdb/udf/datetime.py:dateAddQuantity` (new
  `_ABOVE_SECONDS_UNITS` frozenset + truncation guard). Regression
  coverage in `test_datetime_part2_parity.py` (2 new tests, 32 cases).
  Two pre-existing assertions in `test_wasm_cpp_surface.py` that had
  encoded the buggy expected value (`0.5 day` Add/Subtract returning
  shifted dates) were corrected.

## Known Fragile Areas (CQL-14 EXPLORER additions)

- `extensions/cql/src/cql_extension.cpp:ApplyQuantityAtInputPrecision`
  lines 4697-4704 (above-seconds decimal truncation guard): MUST run
  BEFORE the conversion-divisor path. The truncation rule keys off the
  **quantity unit rank** (`unit_rank < second_rank`), not the input
  precision. If a future refactor moves this guard after the conversion-
  divisor branch or makes it input-precision-aware, the same-precision
  bug regresses. The Python mirror at
  `fhir4ds/cql/duckdb/udf/datetime.py:dateAddQuantity` line 1311 must
  stay in lockstep.
- Browser/no-Python C++ `dateAddQuantity` / `dateSubtractQuantity`
  surfaces route through `ApplyQuantityAtInputPrecision`, so this fix
  is automatically available in browser-style runtimes without separate
  Python registration. Verify with `test_wasm_cpp_surface.py` whenever
  changing this path.
