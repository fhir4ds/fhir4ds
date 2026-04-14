# CQL DuckDB Extension (C++)

Native C++ DuckDB extension implementing Clinical Quality Language (CQL) operations as scalar UDFs. Provides age calculations, datetime operations, interval algebra, clinical functions, quantity/ratio arithmetic, valueset membership, and aggregate statistics.

## Build

Requires: Visual Studio 2022 (or compatible C++ compiler), CMake 3.5+

```bash
# 1. Ensure submodules are present (duckdb @ v1.5.0, extension-ci-tools)
git submodule update --init --recursive

# 2. Configure
cmake -DDUCKDB_EXTENSION_CONFIGS="$(pwd)/extension_config.cmake" \
      -DCMAKE_BUILD_TYPE=Release -S ./duckdb/ -B build/release

# 3. Build
cmake --build build/release --config Release -j 8

# 4. Test (312 assertions)
./build/release/test/Release/unittest.exe "*cql*"
```

On Windows with VS 2022, use the full cmake path:
```
"C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
```

## DuckDB Version Compatibility

Pinned to **DuckDB v1.5.0**. Key constraints:

- **C++11 only** — DuckDB compiles with C++11. This extension uses `cql::Optional<T>` (in `src/cql/optional.hpp`) instead of `std::optional`. No `std::variant`, `std::string_view`, structured bindings, or other C++17+ features.
- **yyjson namespace** — yyjson types are in `namespace duckdb_yyjson`. All .cpp files that use yyjson must have `using namespace duckdb_yyjson;`. Do NOT forward-declare `yyjson_doc`/`yyjson_val` in global scope.
- **No `ExtensionUtil`** — Removed in v1.5.0 (triggers static_assert). Use `ExtensionLoader` and `loader.RegisterFunction()`.
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
    ratio.hpp/cpp            — ratioValue, ratioNumerator/Denominator Value/Unit
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
- **ratio**: Extract and compute from FHIR Ratio structures (numerator/denominator value, unit, ratio).
- **quantity**: FHIR Quantity arithmetic with unit conversion (weight, length, time, volume units). `quantityCompare`, `quantityAdd`, `quantitySubtract`, `quantityConvert`.

## Registered UDFs (~80+)

### Age Functions
`AgeInYears`, `AgeInYearsAt`, `AgeInMonths`, `AgeInMonthsAt`, `AgeInDays`, `AgeInDaysAt`, `AgeInHours`, `AgeInHoursAt`, `AgeInMinutes`, `AgeInMinutesAt`, `AgeInSeconds`, `AgeInSecondsAt`

### DateTime Functions
`differenceInYears`, `differenceInMonths`, `differenceInDays`, `differenceInHours`, `differenceInMinutes`, `differenceInSeconds`, `weeksBetween`, `dateTimeNow`, `dateTimeToday`, `dateTimeSameAs`, `dateTimeSameOrBefore`, `dateTimeSameOrAfter`, `dateTimeAfter`, `dateTimeBefore`, `dateTimeOnOrBefore`, `dateTimeOnOrAfter`, `dateComponent`, `dateTimeTimeOfDay`, `dateAddQuantity`, `dateSubtractQuantity`

### Interval Functions
`intervalContains`, `intervalStart`, `intervalEnd`, `intervalWidth`, `intervalOverlaps`, `intervalBefore`, `intervalAfter`, `intervalIncludes`, `intervalIncludedIn`, `intervalFromBounds`, `intervalMeets`, `intervalMeetsBefore`, `intervalMeetsAfter`, `intervalProperlyIncludes`, `intervalOverlapsBefore`, `intervalOverlapsAfter`, `intervalStartsSame`, `intervalEndsSame`, `collapse_intervals`

### Clinical Functions
`Latest`, `Earliest`, `claim_principal_diagnosis`, `claim_principal_procedure`

### Aggregate Functions
`statisticalMedian`, `statisticalMode`, `statisticalVariance`, `statisticalStdDev`

### Valueset Functions
`extractCodes`, `extractFirstCode`, `extractFirstCodeSystem`, `extractFirstCodeValue`, `resolveProfileUrl`, `in_valueset`

### Ratio Functions
`ratioNumeratorValue`, `ratioDenominatorValue`, `ratioValue`, `ratioNumeratorUnit`, `ratioDenominatorUnit`

### Quantity Functions
`quantityValue`, `quantityUnit`, `parseQuantity`, `quantityCompare`, `quantityAdd`, `quantitySubtract`, `quantityConvert`

### List Functions
`SingletonFrom`, `ElementAt`, `jsonConcat`

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

## Test File

`test/sql/cql.test` — 318 assertions covering all UDF categories, NULL handling, edge cases (empty lists, zero denominators, unknown profiles, cross-unit arithmetic, profile URL resolution).

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
- Build: ✅ | Tests: 318 SQL assertions pass
