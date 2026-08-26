# UDF Registry: C++ vs Python Function Dispatch

> **Last updated:** 2026-04-21  
> **DuckDB version:** 1.5.2  
> **C++ extension:** `extensions/cql/` → `fhir4ds/cql/duckdb/extensions/cql.duckdb_extension`

## Overview

When the C++ CQL extension is available, fhir4ds uses a **hybrid dispatch model**:

1. C++ extension loads first, registering high-performance native functions
2. Python UDFs register via `_SafeConnection` proxy, which silently skips
   any function name that conflicts with an already-registered C++ function
3. SQL macros always register (they supplement both C++ and Python UDFs)

When C++ is unavailable, all functions fall back to pure Python UDFs + macros.

```
┌────────────────────────────────────────────────────────┐
│               DuckDB Function Catalog                  │
├────────────────────────────────────────────────────────┤
│  C++ Extension (85 functions)                          │
│  ├── Age (9)  ├── Quantity (19)  ├── Math (10)         │
│  ├── DateTime (17)  ├── Logical (6)  ├── Ratio (5)     │
│  ├── Clinical (4)  ├── Aggregate (7)  ├── Other (8)    │
│                                                        │
│  Python UDFs (~65 unique, not in C++)                  │
│  ├── Interval algebra (31)  ├── DateTime extended (17) │
│  ├── String (12)  ├── Variable (2)  ├── Other (3)      │
│                                                        │
│  SQL Macros (~100+)                                    │
│  ├── Math (15)  ├── String (20)  ├── DateTime (13)     │
│  ├── List (11)  ├── Logical (10)  ├── Conversion (8)   │
│  └── Aggregate (10)  └── Audit (5)                     │
└────────────────────────────────────────────────────────┘
```

## Registration Flow

```
core.py:register()
  ├── register_cql(con)
  │   ├── _fhirpath_register(con)          # FHIRPath C++ or Python
  │   ├── _try_load_bundled_cpp_extension() # Load CQL C++ extension
  │   ├── _SafeConnection(con)             # Wrap connection for conflict handling
  │   ├── registerXxxUdfs(safe_con)        # 13 Python UDF groups
  │   │   └── Each create_function():
  │   │       ├── If C++ has same name → skip silently
  │   │       └── Otherwise → register Python UDF
  │   └── register_all_macros(con)         # SQL macros (always register)
  └── return {"fhirpath_cpp": bool, "cql_cpp": bool}
```

---

## C++ Functions (85 total)

These functions are implemented in native C++ and registered by the DuckDB extension.
They **cannot be overridden** by Python once loaded.

### Age (`age.hpp/cpp`) — 9 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `AgeInYears` | VARCHAR | BIGINT | From FHIR Patient birthDate |
| `AgeInMonths` | VARCHAR | BIGINT | |
| `AgeInDays` | VARCHAR | BIGINT | |
| `AgeInHours` | VARCHAR | BIGINT | |
| `AgeInMinutes` | VARCHAR | BIGINT | |
| `AgeInSeconds` | VARCHAR | BIGINT | |
| `AgeInYearsAt` | VARCHAR, VARCHAR | BIGINT | At specific date |
| `AgeInMonthsAt` | VARCHAR, VARCHAR | BIGINT | |
| `AgeInDaysAt` | VARCHAR, VARCHAR | BIGINT | |

### DateTime (`datetime.hpp/cpp`) — 17 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `dateTimeNow` | *(none)* | VARCHAR | Current timestamp |
| `dateTimeToday` | *(none)* | VARCHAR | Current date |
| `dateTimeTimeOfDay` | *(none)* | VARCHAR | Current time |
| `dateTimeSameAs` | VARCHAR×3 | BOOLEAN | Precision-aware equality |
| `dateTimeSameOrBefore` | VARCHAR×3 | BOOLEAN | Precision-aware comparison |
| `dateTimeSameOrAfter` | VARCHAR×3 | BOOLEAN | Precision-aware comparison |
| `dateComponent` | VARCHAR×2 | BIGINT | Extract year/month/day/etc. |
| `YearsBetween` | VARCHAR×2 | BIGINT | Duration calculations |
| `MonthsBetween` | VARCHAR×2 | BIGINT | |
| `WeeksBetween` | VARCHAR×2 | BIGINT | |
| `DaysBetween` | VARCHAR×2 | BIGINT | |
| `HoursBetween` | VARCHAR×2 | BIGINT | |
| `MinutesBetween` | VARCHAR×2 | BIGINT | |
| `SecondsBetween` | VARCHAR×2 | BIGINT | |
| `millisecondsBetween` | VARCHAR×2 | BIGINT | |
| `CQLPrecision` | VARCHAR | BIGINT | Infer precision level |
| `cqlTimezoneOffset` | VARCHAR | DOUBLE | Extract timezone offset |

### Quantity (`quantity.hpp/cpp`) — 19 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `parseQuantity` / `parse_quantity` | VARCHAR | VARCHAR | Parse FHIR Quantity JSON |
| `quantityValue` / `quantity_value` | VARCHAR | DOUBLE | Extract numeric value |
| `quantityUnit` / `quantity_unit` | VARCHAR | VARCHAR | Extract unit string |
| `quantityCompare` / `quantity_compare` | VARCHAR×3 | BOOLEAN | UCUM-aware comparison |
| `quantityAdd` / `quantity_add` | VARCHAR×2 | VARCHAR | UCUM-aware arithmetic |
| `quantitySubtract` / `quantity_subtract` | VARCHAR×2 | VARCHAR | |
| `quantityConvert` / `quantity_convert` | VARCHAR×2 | VARCHAR | UCUM unit conversion |
| `quantityNegate` | VARCHAR | VARCHAR | Negate value |
| `quantityAbs` | VARCHAR | VARCHAR | Absolute value |
| `quantityModulo` | VARCHAR×2 | VARCHAR | Modulo |
| `quantityTruncatedDivide` | VARCHAR×2 | VARCHAR | Integer division |
| `ToQuantity` | VARCHAR | VARCHAR | String/number → Quantity |
| `ToConcept` | VARCHAR | VARCHAR | Code → Concept |

### Math (`math.hpp/cpp`) — 10 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `mathAbs` | VARCHAR | VARCHAR | CQL Abs (string in/out) |
| `mathCeiling` | VARCHAR | VARCHAR | |
| `mathFloor` | VARCHAR | VARCHAR | |
| `mathExp` | VARCHAR | VARCHAR | e^x |
| `mathLn` | VARCHAR | VARCHAR | Natural log (NULL for ≤0) |
| `mathLog` | VARCHAR×2 | VARCHAR | Log base N |
| `mathPower` | VARCHAR×2 | VARCHAR | x^y |
| `mathRound` | VARCHAR×2 | VARCHAR | **CQL half-up** (not banker's) |
| `mathSqrt` | VARCHAR | VARCHAR | |
| `mathTruncate` | VARCHAR | VARCHAR | |

### Logical (`logical.hpp/cpp`) — 6 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `logicalAllTrue` | VARCHAR | BOOLEAN | Three-valued logic |
| `logicalAnyTrue` | VARCHAR | BOOLEAN | |
| `logicalAllFalse` | VARCHAR | BOOLEAN | |
| `logicalAnyFalse` | VARCHAR | BOOLEAN | |
| `logicalImplies` | VARCHAR×2 | BOOLEAN | |
| `logicalCoalesce` | VARCHAR | VARCHAR | First non-null |

### Clinical (`clinical.hpp/cpp`) — 4 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `Latest` | LIST(VARCHAR), VARCHAR | VARCHAR | Most recent by period |
| `Earliest` | LIST(VARCHAR), VARCHAR | VARCHAR | Earliest by period |
| `claim_principal_diagnosis` | VARCHAR×2 | VARCHAR | |
| `claim_principal_procedure` | VARCHAR×2 | VARCHAR | |

### Ratio (`ratio.hpp/cpp`) — 5 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `ratioNumeratorValue` | VARCHAR | DOUBLE | |
| `ratioDenominatorValue` | VARCHAR | DOUBLE | |
| `ratioValue` | VARCHAR | DOUBLE | num/denom |
| `ratioNumeratorUnit` | VARCHAR | VARCHAR | |
| `ratioDenominatorUnit` | VARCHAR | VARCHAR | |

### Aggregate (`aggregate.hpp/cpp`) — 4 functions

| Function | Params | Return | Notes |
|----------|--------|--------|-------|
| `statisticalMedian` | LIST(DOUBLE) | DOUBLE | |
| `statisticalMode` | LIST(DOUBLE) | DOUBLE | |
| `statisticalStdDev` | LIST(DOUBLE) | DOUBLE | Sample std dev |
| `statisticalVariance` | LIST(DOUBLE) | DOUBLE | Sample variance |

### List / Valueset / Other — 8 functions

| Function | Params | Return | Module |
|----------|--------|--------|--------|
| `SingletonFrom` | LIST(VARCHAR) | VARCHAR | aggregate |
| `ElementAt` | LIST(VARCHAR), BIGINT | VARCHAR | aggregate |
| `jsonConcat` | VARCHAR×2 | LIST(VARCHAR) | aggregate |
| `extractCodes` | VARCHAR×2 | LIST(VARCHAR) | valueset |
| `extractFirstCode` | VARCHAR×2 | VARCHAR | valueset |
| `extractFirstCodeSystem` | VARCHAR×2 | VARCHAR | valueset |
| `extractFirstCodeValue` | VARCHAR×2 | VARCHAR | valueset |
| `resolveProfileUrl` | VARCHAR | VARCHAR | valueset |
| `in_valueset` | VARCHAR×3 | BOOLEAN | valueset |
| `pointFrom` | VARCHAR | VARCHAR | interval |

---

## Python-Only Functions (~65 unique)

These functions have no C++ implementation and are always served by Python UDFs.

### Interval Algebra (`interval.py`) — 31 functions

*Deferred from C++ due to: Time bounds, successor-aware meets, exclusive boundary
overlaps, predecessor/successor bounds in except, collapse adjacency.*

| Function | Category |
|----------|----------|
| `intervalStart`, `intervalEnd`, `intervalWidth` | Accessors |
| `intervalContains`, `intervalProperlyContains` | Containment |
| `intervalOverlaps`, `intervalOverlapsBefore`, `intervalOverlapsAfter` | Overlap |
| `intervalBefore`, `intervalAfter` | Ordering |
| `intervalOnOrAfter`, `intervalOnOrBefore` | Ordering |
| `intervalMeets`, `intervalMeetsBefore`, `intervalMeetsAfter` | Adjacency |
| `intervalIncludes`, `intervalIncludedIn` | Inclusion |
| `intervalProperlyIncludes`, `intervalProperlyIncludedIn` | Inclusion |
| `intervalStartsSame`, `intervalEndsSame` | Endpoint comparison |
| `intervalFromBounds` | Constructor |
| `intervalIntersect`, `intervalUnion`, `intervalExcept` | Set operations |
| `collapse_intervals` | Collapse |
| `expand`, `expand1`, `expand_points`, `expand_points1` | Expansion |

### Extended DateTime (`datetime.py`) — 17 unique functions

*Not in C++ because they require complex CQL semantics (precision-aware uncertain
comparisons, duration-between with CQL rules, etc.)*

| Function | Notes |
|----------|-------|
| `differenceInYears/Months/Days/Weeks/Hours/Minutes/Seconds/Milliseconds` | CQL difference semantics |
| `cqlDateTimeAdd`, `cqlDateTimeSubtract` | Precision-preserving add/sub |
| `cqlBefore`, `cqlAfter`, `cqlSameOrBefore`, `cqlSameOrAfter` | CQL comparison with null propagation |
| `cqlDurationBetween` | Multi-precision duration |
| `cqlNormalizeTZ` | Timezone normalization |
| `cqlUncertainAdd/Subtract/Multiply/Compare` | Uncertainty arithmetic |
| `dateAddQuantity`, `dateSubtractQuantity` | Quantity-based date math |
| `quantityToInterval` | Quantity → uncertainty interval |

### Boundary (`boundary functions via clinical.py + interval.py`) — 4 functions

| Function | Notes |
|----------|-------|
| `HighBoundary` | Max value at precision (Time bug in C++) |
| `LowBoundary` | Min value at precision |
| `predecessorOf` | Previous value (quantity support needed) |
| `successorOf` | Next value |

### String (`string.py`) — 12 functions

*No C++ implementation exists.*

| Function |
|----------|
| `stringConcatenate`, `stringContains`, `stringEndsWith`, `stringLength` |
| `stringLower`, `stringMatches`, `stringPositionOf`, `stringReplace` |
| `stringSplit`, `stringStartsWith`, `stringSubstring`, `stringUpper` |

### Quantity Extensions (`quantity.py`) — 2 functions

| Function | Notes |
|----------|-------|
| `quantityMultiply` | Unit multiplication (e.g., cm × cm → cm²) |
| `quantityDivide` | Unit division (e.g., g/cm³ ÷ g/cm³ → 1) |

### Variable/State (`variable.py`) — 2 functions

*Structurally require Python (mutable closure state).*

| Function | Notes |
|----------|-------|
| `_getvariable_impl` | CQL variable retrieval |
| `_setvariable_impl` | CQL variable assignment |

---

## Conformance Results (2026-06-16)

| Mode | CQL | DQM | ViewDef | FHIRPath | Overall |
|------|-----|-----|---------|----------|---------|
| **C++ + Python** | 1704/1706 (99.9%) | 42/46 (91.3%) | 134/134 (100%) | 934/935 (99.9%) | 2814/2821 (99.8%) |
| **Python only** | 1704/1706 (99.9%) | 42/46 (91.3%) | 134/134 (100%) | 934/935 (99.9%) | 2814/2821 (99.8%) |

**Parity: ✅ Exact match** — no regressions from C++ extension.

---

## Known C++ Deferrals (Future Work)

The following function categories were implemented in C++ but deferred to Python
due to behavioral bugs. They are candidates for future C++ optimization:

| Category | Issue | Impact |
|----------|-------|--------|
| Interval algebra (26 functions) | Time bounds, successor-aware meets, exclusive boundary overlaps | ~83 conformance tests |
| DateTime differences (8 functions) | Time input handling, edge-case calculations | ~26 conformance tests |
| Boundary functions (4) | Time precision, quantity predecessor/successor | ~8 conformance tests |
| Quantity multiply/divide (2) | UCUM unit arithmetic (cm×cm→cm²) | ~2 conformance tests |

See `extensions/cql/src/cql_extension.cpp` comments for details on each deferral.
