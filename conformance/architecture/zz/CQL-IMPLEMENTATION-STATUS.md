# CQL Implementation Status

**Last Updated:** 2026-02-21

This document provides a comprehensive analysis of the CQL R1.5 specification coverage across the duckdb-fhirpath project, current implementation state, and identified gaps.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [CQL R1.5 Specification Summary](#cql-r15-specification-summary)
3. [Component Inventory](#component-inventory)
4. [Feature Coverage Matrix](#feature-coverage-matrix)
5. [Gap Analysis](#gap-analysis)
6. [Recommendations](#recommendations)

---

## Architecture Overview

### Translation Pipeline

```
CQL Source → Parser → AST → SQLTranslator → DuckDB SQL
                                      ↓
                    ┌─────────────────┼─────────────────┐
                    ↓                 ↓                 ↓
              FHIRPath UDFs     CQL UDFs/Macros    Native SQL
              (property access) (age, temporal)    (union, without)
```

### Three-Tier Execution Model

| Tier | Type | Overhead | Description |
|------|------|----------|-------------|
| **Tier 1** | Native SQL Macros | Zero Python overhead | Direct mappings to DuckDB built-in functions |
| **Tier 2** | SQL Expressions | Minimal overhead | SQL CASE expressions and computed logic |
| **Tier 3** | Vectorized Arrow UDFs | Batch processing | Python UDFs with Arrow for complex operations |

### Package Responsibilities

| Package | Responsibility |
|---------|---------------|
| `cql-py` | CQL parsing, AST, translation (v1 → FHIRPath, v2 → SQL) |
| `duckdb-cql-py` | CQL-specific UDFs and macros for DuckDB |
| `duckdb-fhirpath-py` | FHIRPath evaluation UDFs and macros |
| `fhirpath-py` | Core FHIRPath engine with 100+ function implementations |

---

## CQL R1.5 Specification Summary

### Data Types

#### Primitive Types (9)

| Type | Description | Example |
|------|-------------|---------|
| `Boolean` | Logical true/false | `true`, `false` |
| `Integer` | Whole numbers (-2^31 to 2^31-1) | `42`, `-7` |
| `Long` | Large whole numbers (-2^63 to 2^63-1) | `9223372036854775807` |
| `Decimal` | Real values (28 digits precision) | `3.14159` |
| `String` | Text values | `'Hello World'` |
| `Date` | Date values | `@2024-06-15` |
| `DateTime` | Date and time with timezone | `@2024-06-15T10:30:00.000-05:00` |
| `Time` | Time-of-day values | `@T10:30:00.000` |
| `Any` | Maximal supertype (type of null) | `null` |

#### Structured Types (7)

| Type | Elements |
|------|----------|
| `Code` | `code` (String), `display` (String), `system` (String), `version` (String) |
| `CodeSystem` | `id`, `version`, `name` - extends Vocabulary |
| `Concept` | `codes` (List<Code>), `display` (String) |
| `Quantity` | `value` (Decimal), `unit` (String) |
| `Ratio` | `numerator` (Quantity), `denominator` (Quantity) |
| `ValueSet` | `id`, `version`, `name`, `codesystems` |
| `Vocabulary` | `id`, `version`, `name` (abstract base) |

#### Parameterized Types (3)

| Type | Description |
|------|-------------|
| `List<T>` | Ordered collection of elements |
| `Interval<T>` | Range with low/high boundaries (open or closed) |
| `Tuple` | Named element structure |

### Operator Categories

#### Logical Operators (5)

| Operator | Signature | Description |
|----------|-----------|-------------|
| `and` | `(Boolean, Boolean) Boolean` | Conjunction |
| `or` | `(Boolean, Boolean) Boolean` | Disjunction |
| `xor` | `(Boolean, Boolean) Boolean` | Exclusive or |
| `not` | `(Boolean) Boolean` | Negation |
| `implies` | `(Boolean, Boolean) Boolean` | Logical implication |

#### Nullological Operators (4)

| Operator | Signature | Description |
|----------|-----------|-------------|
| `Coalesce` | `(T, T, ...) T` or `(List<T>) T` | First non-null |
| `is null` | `(Any) Boolean` | Null test |
| `is true` | `(Boolean) Boolean` | True test (false for null) |
| `is false` | `(Boolean) Boolean` | False test (false for null) |

#### Comparison Operators (10)

| Operator | Types | Description |
|----------|-------|-------------|
| `=` | All comparable | Value equality |
| `!=` / `<>` | All comparable | Not equal |
| `~` | All comparable | Equivalence (null-safe) |
| `!~` | All comparable | Not equivalent |
| `>` | Numeric, Date, String | Greater than |
| `>=` | Numeric, Date, String | Greater or equal |
| `<` | Numeric, Date, String | Less than |
| `<=` | Numeric, Date, String | Less or equal |
| `between` | Numeric, Date | Range check |

#### Arithmetic Operators (18)

| Operator | Description |
|----------|-------------|
| `+` | Addition |
| `-` | Subtraction |
| `*` | Multiplication |
| `/` | Division |
| `div` | Truncated division |
| `mod` | Modulo |
| `^` | Power |
| `-` (unary) | Negation |
| `Abs` | Absolute value |
| `Ceiling` | Round up |
| `Floor` | Round down |
| `Truncate` | Integer component |
| `Round` | Round to precision |
| `Exp` | e^x |
| `Ln` | Natural logarithm |
| `Log` | Logarithm with base |
| `predecessor of` | Previous value in ordering |
| `successor of` | Next value in ordering |

#### String Operators (14)

| Operator | Description |
|----------|-------------|
| `+` / `&` | Concatenation (+ is null-sensitive, & treats null as empty) |
| `Combine` | Join list elements |
| `EndsWith` | Suffix check |
| `StartsWith` | Prefix check |
| `Length` | Character count |
| `Lower` / `Upper` | Case conversion |
| `Matches` | Regex match |
| `ReplaceMatches` | Regex replace |
| `PositionOf` | First index of pattern |
| `LastPositionOf` | Last index of pattern |
| `Substring` | Extract substring |
| `Split` | Split into list |
| `SplitOnMatches` | Regex split |
| `[]` | Character at index |

#### DateTime Operators (30+)

**Construction:**
- `Date(year, month, day)`
- `DateTime(year, month, day, hour, minute, second, millisecond, timezoneOffset)`
- `Time(hour, minute, second, millisecond)`

**Current:**
- `Now()`, `Today()`, `TimeOfDay()`

**Component Extraction:**
- `year from`, `month from`, `day from`
- `hour from`, `minute from`, `second from`, `millisecond from`
- `timezoneoffset from`
- `date from`, `time from`

**Duration/Difference:**
- `years between`, `months between`, `weeks between`, `days between`
- `hours between`, `minutes between`, `seconds between`, `milliseconds between`
- `difference in _precision_ between` (boundaries crossed)
- `duration in _precision_ between` (whole periods)

**Comparison:**
- `before _precision_ of`, `after _precision_ of`
- `same _precision_ as`
- `same _precision_ or before`, `same _precision_ or after`

#### Interval Operators (25+)

| Operator | Description |
|----------|-------------|
| `start of` / `end of` | Boundary access |
| `width of` | Width calculation |
| `Size` | Number of points |
| `contains` | Point in interval |
| `in` / `during` | Point in interval (reversed) |
| `includes` / `included in` | Interval inclusion |
| `properly includes` / `properly included in` | Strict inclusion |
| `after` / `before` | Ordering |
| `meets` / `meets before` / `meets after` | Adjacent intervals |
| `overlaps` / `overlaps before` / `overlaps after` | Overlap detection |
| `starts` / `ends` | Boundary matching |
| `union` / `intersect` / `except` | Set operations |
| `collapse` / `expand` | List manipulation |

#### List Operators (20+)

| Operator | Description |
|----------|-------------|
| `contains` / `in` | Membership |
| `includes` / `included in` | Subset |
| `properly includes` / `properly included in` | Strict subset |
| `exists` | Non-null elements |
| `distinct` | Remove duplicates |
| `flatten` | Nested list flattening |
| `First` / `Last` | Endpoint access |
| `Length` | Element count |
| `IndexOf` | Element position |
| `[]` | Index access |
| `singleton from` | Single element extraction |
| `Skip` / `Take` / `Tail` | Subsetting |
| `union` / `intersect` / `except` | Set operations |

#### Aggregate Functions (13)

| Function | Types |
|----------|-------|
| `AllTrue` / `AnyTrue` | List<Boolean> |
| `Avg` | List<Decimal>, List<Quantity> |
| `Count` | List<T> |
| `GeometricMean` | List<Decimal> |
| `Max` / `Min` | List<Integer|Decimal|Quantity|Date|DateTime|Time|String> |
| `Median` | List<Decimal>, List<Quantity> |
| `Mode` | List<T> |
| `PopulationStdDev` / `PopulationVariance` | List<Decimal>, List<Quantity> |
| `Product` | List<Integer|Decimal|Quantity> |
| `StdDev` / `Variance` | List<Decimal>, List<Quantity> |
| `Sum` | List<Integer|Decimal|Quantity> |

#### Type Operators (20+)

| Operator | Description |
|----------|-------------|
| `is` | Type test |
| `as` | Safe cast |
| `cast as` | Cast (throws on failure) |
| `convert to` | Type conversion |
| `Children` | Child values |
| `Descendants` | Recursive children |

**Conversion Functions:**
- `ToBoolean`, `ToInteger`, `ToLong`, `ToDecimal`
- `ToQuantity`, `ToRatio`, `ToString`
- `ToDate`, `ToDateTime`, `ToTime`
- `ToConcept`, `ConvertQuantity`, `CanConvertQuantity`

**Conversion Test Functions:**
- `ConvertsToBoolean`, `ConvertsToInteger`, `ConvertsToLong`
- `ConvertsToDecimal`, `ConvertsToQuantity`, `ConvertsToRatio`
- `ConvertsToString`, `ConvertsToDate`, `ConvertsToDateTime`, `ConvertsToTime`

#### Clinical Operators (35+)

**Age Functions:**
- `AgeInYears()`, `AgeInMonths()`, `AgeInWeeks()`, `AgeInDays()`
- `AgeInHours()`, `AgeInMinutes()`, `AgeInSeconds()`

**AgeAt Functions:**
- `AgeInYearsAt(asOf)`, `AgeInMonthsAt(asOf)`, etc.

**CalculateAge Functions:**
- `CalculateAgeInYears(birthDate)`, `CalculateAgeInMonths(birthDate)`, etc.

**CalculateAgeAt Functions:**
- `CalculateAgeInYearsAt(birthDate, asOf)`, etc.

**Terminology Operators:**
- `in` (CodeSystem/ValueSet)
- `ExpandValueSet`
- Code/Concept equality and equivalence

---

## Component Inventory

### duckdb-cql-py Extension

#### UDFs (64 functions across 12 modules)

| Module | Functions |
|--------|-----------|
| **age.py** | `AgeInYears`, `AgeInMonths`, `AgeInDays`, `AgeInHours`, `AgeInMinutes`, `AgeInSeconds`, `AgeInYearsAt`, `AgeInMonthsAt`, `AgeInDaysAt` |
| **datetime.py** | `weeksBetween`, `millisecondsBetween`, `dateTimeNow`, `dateTimeToday`, `dateTimeTimeOfDay`, `differenceInYears`, `differenceInMonths`, `differenceInDays`, `dateComponent`, `dateTimeSameAs`, `dateTimeSameOrBefore`, `dateTimeSameOrAfter` |
| **interval.py** | `intervalStart`, `intervalEnd`, `intervalWidth`, `intervalContains`, `intervalProperlyContains`, `intervalOverlaps`, `intervalBefore`, `intervalAfter`, `intervalMeets`, `intervalIncludes`, `intervalIncludedIn`, `intervalProperlyIncludes`, `intervalProperlyIncludedIn`, `intervalOverlapsBefore`, `intervalOverlapsAfter`, `intervalMeetsBefore`, `intervalMeetsAfter`, `intervalStartsSame`, `intervalEndsSame` |
| **string.py** | `stringLength`, `stringLower`, `stringUpper`, `stringSubstring`, `stringConcatenate`, `stringSplit`, `stringPositionOf`, `stringStartsWith`, `stringEndsWith`, `stringContains`, `stringMatches`, `stringReplace` |
| **math.py** | `mathAbs`, `mathRound`, `mathFloor`, `mathCeiling`, `mathSqrt`, `mathExp`, `mathLn`, `mathLog`, `mathPower`, `mathTruncate` |
| **logical.py** | `logicalCoalesce`, `logicalImplies`, `logicalAllTrue`, `logicalAnyTrue`, `logicalAllFalse`, `logicalAnyFalse` |
| **aggregate.py** | `statisticalMedian`, `statisticalMode`, `statisticalStdDev`, `statisticalVariance` |
| **quantity.py** | `parseQuantity`, `quantityValue`, `quantityUnit`, `quantityCompare`, `quantityAdd`, `quantitySubtract`, `quantityConvert` |
| **ratio.py** | `ratioNumeratorValue`, `ratioDenominatorValue`, `ratioValue`, `ratioNumeratorUnit`, `ratioDenominatorUnit` |
| **valueset.py** | `extractCodes`, `extractFirstCode`, `extractFirstCodeSystem`, `extractFirstCodeValue`, `createValuesetMembershipUdf` |
| **list.py** | `SingletonFrom`, `ElementAt` |
| **clinical.py** | `Latest`, `Earliest` |

#### Macros (63 functions across 7 modules)

| Module | Functions |
|--------|-----------|
| **math.py** | `Abs`, `Ceiling`, `Floor`, `Round`, `Sqrt`, `Exp`, `Ln`, `Log`, `Power`, `Truncate`, `Sign`, `Mod`, `Div` |
| **string.py** | `Length`, `Upper`, `Lower`, `Concat`, `Substring`, `SubstringLen`, `IndexOf`, `StartsWith`, `EndsWith`, `Contains`, `Replace`, `Split`, `Trim`, `LTrim`, `RTrim`, `Reverse`, `Left`, `Right` |
| **datetime.py** | `Now`, `Today`, `TimeOfDay`, `Year`, `Month`, `Day`, `Hour`, `Minute`, `Second`, `MakeDate`, `MakeTime`, `MakeDateTime`, `YearsBetween`, `MonthsBetween`, `DaysBetween`, `HoursBetween`, `MinutesBetween`, `SecondsBetween` |
| **aggregate.py** | `Count`, `Sum`, `Min`, `Max`, `Avg`, `Median`, `Mode`, `StdDev`, `StdDevPop`, `Variance`, `VarPop`, `AllTrue`, `AnyTrue`, `AllFalse`, `AnyFalse` |
| **logical.py** | `And`, `Or`, `Not`, `Coalesce`, `Xor`, `Implies`, `IsNull`, `IsNotNull`, `IfNull` |
| **conversion.py** | `ToString`, `ToInteger`, `ToDecimal`, `ToBoolean`, `ToDate`, `ToDateTime`, `ToTime` |
| **list.py** | `First`, `Last`, `Skip`, `Take`, `Distinct` |

### duckdb-fhirpath-py Extension

#### UDFs (6 functions)

| Function | Return Type | Description |
|----------|-------------|-------------|
| `fhirpath(resource, expression)` | `LIST<VARCHAR>` | Full FHIRPath evaluation |
| `fhirpath_is_valid(expression)` | `BOOLEAN` | Syntax validation |
| `fhirpath_text(resource, expression)` | `VARCHAR` | First value as text |
| `fhirpath_bool(resource, expression)` | `BOOLEAN` | First value as boolean |
| `fhirpath_number(resource, expression)` | `DOUBLE` | First value as number |
| `fhirpath_json(resource, expression)` | `VARCHAR` | Result as JSON |

#### Macros (37 functions across 5 modules)

| Module | Functions |
|--------|-----------|
| **math.py** | `Abs`, `Ceiling`, `Floor`, `Round`, `Sqrt`, `Exp`, `Ln`, `Log`, `Power`, `Truncate` |
| **string.py** | `Length`, `Upper`, `Lower`, `Concat`, `Substring`, `IndexOf`, `StartsWith`, `EndsWith`, `Contains`, `Replace`, `Trim`, `LTrim`, `RTrim` |
| **datetime.py** | `Year`, `Month`, `Day`, `Hour`, `Minute`, `Second`, `Now`, `Today`, `TimeOfDay` |
| **logical.py** | `And`, `Or`, `Not`, `Xor`, `Implies`, `Coalesce` |
| **conversion.py** | `ToString`, `ToInteger`, `ToDecimal`, `ToBoolean`, `ToDate`, `ToDateTime` |

### fhirpath-py Engine

The core FHIRPath engine implements 100+ functions organized into categories:

| Category | Functions |
|----------|-----------|
| **Existence** | `empty`, `not`, `exists`, `all`, `allTrue`, `anyTrue`, `allFalse`, `anyFalse`, `subsetOf`, `supersetOf`, `isDistinct`, `distinct`, `hasValue`, `getValue`, `count` |
| **Filtering** | `where`, `select`, `repeat`, `extension`, `single`, `first`, `last`, `ofType`, `tail`, `take`, `skip` |
| **Subsetting** | `intersect`, `union`, `exclude`, `combine` |
| **Strings** | `indexOf`, `substring`, `startsWith`, `endsWith`, `contains`, `upper`, `lower`, `replace`, `matches`, `replaceMatches`, `length`, `toChars`, `join`, `split`, `trim`, `encode`, `decode`, `escape`, `unescape`, `matchesFull` |
| **Math** | `abs`, `ceiling`, `exp`, `floor`, `ln`, `log`, `power`, `round`, `sqrt`, `truncate`, `+`, `-`, `*`, `/`, `mod`, `div`, `&` |
| **DateTime** | `now`, `today`, `timeOfDay`, `lowBoundary`, `highBoundary`, `precision` |
| **Types** | `type`, `is`, `as` |
| **Conversion** | `toInteger`, `toBoolean`, `toDecimal`, `toString`, `toDate`, `toDateTime`, `toTime`, `toQuantity` |
| **Aggregate** | `avg`, `sum`, `min`, `max`, `aggregate` |
| **Logic** | `or`, `and`, `xor`, `implies` |
| **Equality** | `=`, `!=`, `~`, `!~`, `<`, `>`, `<=`, `>=` |
| **Collections** | `sort`, `comparable`, `contains`, `in` |
| **Navigation** | `children`, `descendants`, `resolve` |
| **Misc** | `iif`, `trace`, `conformsTo`, `convertsTo*` |

### cql-py Translator V2

#### Expression Types Handled (20+)

| AST Node | Implementation |
|----------|----------------|
| `Literal` | Boolean, string, numeric literals |
| `DateTimeLiteral` | @2024-01-15T12:30:00 format |
| `TimeLiteral` | @T12:30:00 format |
| `Quantity` | Uses `parse_quantity` UDF |
| `Identifier` | Symbol table lookup |
| `QualifiedIdentifier` | Library/valueset references |
| `Property` | `fhirpath_text`/`fhirpath_bool` UDFs |
| `FunctionRef` | Function dispatch |
| `BinaryExpression` | All operators |
| `UnaryExpression` | NOT, IS NULL, exists |
| `Interval` | SQLInterval struct |
| `ListExpression` | SQLArray |
| `ConditionalExpression` | CASE WHEN |
| `CaseExpression` | Full CASE support |
| `TupleExpression` | struct_pack |
| `InstanceExpression` | Interval/Quantity construction |
| `MethodInvocation` | Fluent methods |
| `AliasRef` | Alias references |
| `IndexerExpression` | 0-to-1 index adjustment |
| `ParameterPlaceholder` | Function inlining |

#### Pattern Modules

| Module | Purpose |
|--------|---------|
| `retrieve.py` | FHIR resource retrieval |
| `aggregation.py` | First/Last/Singleton/Exists/Count |
| `joins.py` | With/Without clauses |
| `quantity.py` | Quantity operations |
| `temporal.py` | Temporal operators |
| `interval.py` | Interval operations |

---

## Feature Coverage Matrix

### Primitive Types

| Type | Parser | Translator V2 | UDF/Macro Support |
|------|--------|---------------|-------------------|
| Boolean | ✅ | ✅ | ✅ Native SQL |
| Integer | ✅ | ✅ | ✅ Native SQL |
| Long | ✅ | ✅ | ✅ Native SQL (BIGINT) |
| Decimal | ✅ | ✅ | ✅ Native SQL (DOUBLE) |
| String | ✅ | ✅ | ✅ Native SQL |
| Date | ✅ | ✅ | ✅ Native SQL |
| DateTime | ✅ | ✅ | ✅ Native SQL |
| Time | ✅ | ✅ | ✅ Native SQL |
| Any | ✅ | ✅ | N/A |

### Structured Types

| Type | Parser | Translator V2 | UDF Support |
|------|--------|---------------|-------------|
| Code | ✅ | ✅ | ✅ Terminology UDFs |
| CodeSystem | ✅ | ✅ | ✅ Terminology UDFs |
| Concept | ✅ | ✅ | ✅ Terminology UDFs |
| Quantity | ✅ | ✅ | ✅ Full quantity UDFs |
| Ratio | ✅ | ⚠️ Partial | ✅ Ratio UDFs |
| ValueSet | ✅ | ✅ | ✅ Valueset UDFs |
| Tuple | ✅ | ✅ | ✅ struct_pack |

### Operators by Category

#### Logical Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `and` | ✅ | Native SQL AND |
| `or` | ✅ | Native SQL OR |
| `xor` | ✅ | (a OR b) AND NOT (a AND b) |
| `not` | ✅ | Native SQL NOT |
| `implies` | ✅ | NOT a OR b |

#### Comparison Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `=` | ✅ | Native SQL |
| `!=` / `<>` | ✅ | Native SQL |
| `~` | ✅ | CASE with null handling |
| `!~` | ✅ | NOT (equivalence) |
| `>` | ✅ | Native SQL |
| `>=` | ✅ | Native SQL |
| `<` | ✅ | Native SQL |
| `<=` | ✅ | Native SQL |
| `between` | ✅ | x >= low AND x <= high |

#### Arithmetic Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `+` | ✅ | Native SQL |
| `-` | ✅ | Native SQL |
| `*` | ✅ | Native SQL |
| `/` | ✅ | Native SQL |
| `div` | ✅ | FLOOR(x / y) |
| `mod` | ✅ | MOD(x, y) |
| `^` | ✅ | POW(x, y) |
| `Abs` | ✅ | ABS() |
| `Ceiling` | ✅ | CEIL() |
| `Floor` | ✅ | FLOOR() |
| `Round` | ✅ | ROUND() |
| `Truncate` | ✅ | TRUNC() |
| `Ln` | ✅ | LN() |
| `Log` | ✅ | LOG() |
| `Exp` | ✅ | EXP() |
| `Sqrt` | ✅ | SQRT() |
| `Power` | ✅ | POW() |
| `predecessor of` | ❌ | NOT IMPLEMENTED |
| `successor of` | ❌ | NOT IMPLEMENTED |

#### String Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `Length` | ✅ | LENGTH() |
| `Upper` / `Lower` | ✅ | UPPER() / LOWER() |
| `Concatenate` / `+` / `&` | ✅ | \|\| operator |
| `Substring` | ✅ | SUBSTRING() |
| `StartsWith` | ✅ | LIKE 'prefix%' |
| `EndsWith` | ✅ | LIKE '%suffix' |
| `Contains` | ✅ | STRPOS() > 0 |
| `Matches` | ✅ | regexp_matches() |
| `Replace` | ✅ | REPLACE() |
| `Split` | ✅ | STR_SPLIT() |
| `PositionOf` | ✅ | STRPOS() - 1 |
| `Trim` | ✅ | TRIM() |
| `ReplaceMatches` | ⚠️ | Available via FHIRPath |
| `LastPositionOf` | ❌ | NOT IMPLEMENTED |
| `SplitOnMatches` | ❌ | NOT IMPLEMENTED |

#### DateTime Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `Now()` | ✅ | CURRENT_TIMESTAMP |
| `Today()` | ✅ | CURRENT_DATE |
| `TimeOfDay()` | ✅ | CURRENT_TIME |
| `DateTime()` | ✅ | make_timestamp() |
| `Date()` | ✅ | make_date() |
| `Time()` | ✅ | make_time() |
| `year from` | ✅ | YEAR() macro |
| `month from` | ✅ | MONTH() macro |
| `day from` | ✅ | DAY() macro |
| `hour from` | ✅ | HOUR() macro |
| `minute from` | ✅ | MINUTE() macro |
| `second from` | ✅ | SECOND() macro |
| `years between` | ✅ | YearsBetween() macro |
| `months between` | ✅ | MonthsBetween() macro |
| `weeks between` | ⚠️ | weeksBetween UDF exists |
| `days between` | ✅ | DaysBetween() macro |
| `hours between` | ✅ | HoursBetween() macro |
| `minutes between` | ✅ | MinutesBetween() macro |
| `seconds between` | ✅ | SecondsBetween() macro |
| `milliseconds between` | ⚠️ | millisecondsBetween UDF exists |
| `same day as` | ✅ | DATE() comparison |
| `on or before` | ✅ | dateTimeSameOrBefore UDF |
| `on or after` | ✅ | dateTimeSameOrAfter UDF |
| `difference in` | ⚠️ | differenceIn* UDFs exist |
| `millisecond from` | ❌ | NOT IMPLEMENTED |
| `timezoneoffset from` | ❌ | NOT IMPLEMENTED |

#### Interval Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `start of` | ✅ | intervalStart UDF |
| `end of` | ✅ | intervalEnd UDF |
| `contains` | ✅ | intervalContains UDF |
| `in` / `during` | ✅ | intervalContains UDF |
| `overlaps` | ✅ | intervalOverlaps UDF |
| `before` | ✅ | intervalBefore UDF |
| `after` | ✅ | intervalAfter UDF |
| `meets` | ✅ | intervalMeets UDF |
| `includes` | ✅ | intervalIncludes UDF |
| `included in` | ✅ | intervalIncludedIn UDF |
| `properly includes` | ✅ | intervalProperlyIncludes UDF |
| `properly included in` | ✅ | intervalProperlyIncludedIn UDF |
| `overlaps before` | ✅ | intervalOverlapsBefore UDF |
| `overlaps after` | ✅ | intervalOverlapsAfter UDF |
| `starts` | ✅ | intervalStartsSame UDF |
| `ends` | ✅ | intervalEndsSame UDF |
| `width of` | ⚠️ | intervalWidth UDF exists |
| `union` | ⚠️ | In pattern module |
| `intersect` | ⚠️ | In pattern module |
| `except` | ⚠️ | In pattern module |
| `collapse` | ❌ | NOT IMPLEMENTED |
| `expand` | ❌ | NOT IMPLEMENTED |

#### List Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `First` | ✅ | list_extract(arr, 1) |
| `Last` | ✅ | arr[-1] |
| `Skip` | ✅ | list_slice() |
| `Take` | ✅ | list_slice() |
| `Distinct` | ✅ | array_distinct() |
| `Where` | ✅ | list_filter() |
| `Select` | ✅ | list_transform() |
| `Exists` | ✅ | array_length() > 0 |
| `Count` | ✅ | array_length() |
| `SingletonFrom` | ⚠️ | list_extract / UDF exists |
| `Flatten` | ✅ | flatten() |
| `IndexOf` | ⚠️ | Macro exists |
| `Tail` | ⚠️ | FHIRPath tail() available |
| `union` | ✅ | UNION ALL |
| `intersect` | ✅ | list intersection |
| `contains` / `in` | ✅ | array_contains() |
| `includes` | ⚠️ | FHIRPath available |

#### Aggregate Functions

| Function | Translator V2 | Uses |
|----------|---------------|------|
| `Count` | ✅ | COUNT() |
| `Sum` | ✅ | SUM() |
| `Avg` | ✅ | AVG() |
| `Min` | ✅ | MIN() |
| `Max` | ✅ | MAX() |
| `Median` | ✅ | MEDIAN() |
| `Mode` | ✅ | MODE() |
| `StdDev` | ✅ | STDDEV() |
| `Variance` | ✅ | VARIANCE() |
| `AllTrue` | ✅ | AllTrue macro |
| `AnyTrue` | ✅ | AnyTrue macro |
| `AllFalse` | ✅ | AllFalse macro |
| `AnyFalse` | ✅ | AnyFalse macro |
| `GeometricMean` | ❌ | NOT IMPLEMENTED |
| `Product` | ❌ | NOT IMPLEMENTED |
| `PopulationStdDev` | ⚠️ | StdDevPop macro |
| `PopulationVariance` | ⚠️ | VarPop macro |

#### Type Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `is` | ✅ | Type check |
| `as` | ✅ | CAST() |
| `ToString` | ✅ | CAST(x AS VARCHAR) |
| `ToInteger` | ✅ | CAST(x AS INTEGER) |
| `ToDecimal` | ✅ | CAST(x AS DOUBLE) |
| `ToBoolean` | ✅ | CAST(x AS BOOLEAN) |
| `ToDate` | ✅ | CAST(x AS DATE) |
| `ToDateTime` | ✅ | CAST(x AS TIMESTAMP) |
| `ToTime` | ✅ | CAST(x AS TIME) |
| `ToQuantity` | ✅ | parseQuantity UDF |
| `ToConcept` | ✅ | Terminology module |
| `ToCode` | ✅ | Terminology module |
| `ConvertQuantity` | ✅ | quantityConvert UDF |
| `Children` | ⚠️ | Via FHIRPath |
| `Descendants` | ⚠️ | Via FHIRPath repeat() |
| `ConvertsTo*` | ❌ | NOT IMPLEMENTED |

#### Clinical Operators

| Operator | Translator V2 | Uses |
|----------|---------------|------|
| `AgeInYears()` | ✅ | date_diff or UDF |
| `AgeInMonths()` | ✅ | date_diff or UDF |
| `AgeInDays()` | ✅ | date_diff or UDF |
| `AgeInHours()` | ✅ | date_diff or UDF |
| `AgeInMinutes()` | ✅ | date_diff or UDF |
| `AgeInSeconds()` | ✅ | date_diff or UDF |
| `AgeInYearsAt()` | ⚠️ | UDF exists, partial wiring |
| `AgeInMonthsAt()` | ⚠️ | UDF exists, partial wiring |
| `AgeInDaysAt()` | ⚠️ | UDF exists, partial wiring |
| `AgeInWeeks()` | ❌ | NOT IMPLEMENTED |
| `CalculateAge*` | ❌ | NOT IMPLEMENTED |
| `Latest` | ⚠️ | UDF exists, not wired |
| `Earliest` | ⚠️ | UDF exists, not wired |

### Query Constructs

| Construct | Translator V2 | SQL Pattern |
|-----------|---------------|-------------|
| Basic Retrieve | ✅ | SELECT FROM resources WHERE resource_type = X |
| Retrieve with ValueSet | ✅ | in_valueset UDF |
| Retrieve with Code | ✅ | fhirpath_bool with code matching |
| Where clause | ✅ | WHERE condition |
| Let clause | ✅ | CTEs |
| Return clause | ✅ | SELECT expressions |
| Sort clause | ✅ | ORDER BY |
| With clause | ✅ | EXISTS subquery |
| Without clause | ✅ | NOT EXISTS subquery |
| Multi-source query | ✅ | CROSS JOIN |
| First/Last with sort | ✅ | ORDER BY ... LIMIT 1 |
| Singleton from | ✅ | Subquery with LIMIT 1 |
| Union | ✅ | UNION ALL |

---

## Gap Analysis

### Summary Statistics

| Metric | Value |
|--------|-------|
| **CQL Spec Features** | ~200+ operators/functions |
| **Available via UDFs/Macros** | ~270 functions |
| **Translator V2 Coverage** | ~95% |
| **True Missing Features** | ~5 |

### Test Results (2026-02-21)

| Test Suite | Passed | Skipped | Total |
|------------|--------|---------|-------|
| **Full Test Suite** | 4,152 | 76 | 4,228 |
| **CMS Measure Integration** | 98 | 9 | 107 |
| **CMS124 (Cervical Cancer)** | ✅ Full translation | | 12 definitions |
| **CMS139 (Fall Risk)** | ✅ Full translation | | 9 definitions |
| **CMS144 (Heart Failure)** | ✅ Full translation | | 23 definitions |
| **CMS165 (Blood Pressure)** | ✅ Full translation | | 19 definitions |

### CRITICAL Gaps - ✅ RESOLVED

| Gap | Status | Implementation |
|-----|--------|----------------|
| `DurationBetween` AST handler | ✅ Fixed | `_translate_duration_between()` calls YearsBetween/MonthsBetween/etc |
| `DifferenceBetween` AST handler | ✅ Fixed | `_translate_difference_between()` calls differenceIn* UDFs |
| `DateComponent` AST handler | ✅ Fixed | `_translate_date_component()` calls Year/Month/Day macros |
| `ExistsExpression` AST handler | ✅ Fixed | `_translate_exists_expression()` generates array_length > 0 |
| `AggregateExpression` AST handler | ✅ Fixed | `_translate_aggregate_expression()` handles Sum/Count/etc |

### HIGH Priority Gaps - ✅ RESOLVED

| Gap | Status | Implementation |
|-----|--------|----------------|
| `SkipExpression` AST handler | ✅ Fixed | `_translate_skip_expression()` uses list_slice |
| `TakeExpression` AST handler | ✅ Fixed | `_translate_take_expression()` uses list_slice |
| `FirstExpression` AST handler | ✅ Fixed | `_translate_first_expression()` uses list_extract |
| `LastExpression` AST handler | ✅ Fixed | `_translate_last_expression()` uses list_extract |
| `AnyExpression` AST handler | ✅ Fixed | `_translate_any_expression()` uses list_any |
| `AllExpression` AST handler | ✅ Fixed | `_translate_all_expression()` uses list_all |
| `Query` expression handler | ✅ Fixed | `_translate_query()` handles retrieve/where/return/sort |
| `Retrieve` expression handler | ✅ Fixed | `_translate_retrieve()` generates SELECT from resource table |

### Interval Operators - ✅ RESOLVED

| Operator | Status | Implementation |
|----------|--------|----------------|
| `overlaps` | ✅ Fixed | Calls `intervalOverlaps` UDF |
| `during` | ✅ Fixed | Calls `intervalContains` UDF |
| `includes` | ✅ Fixed | Calls `intervalContains` UDF |
| `before` | ✅ Fixed | Calls `intervalBefore` UDF |
| `after` | ✅ Fixed | Calls `intervalAfter` UDF |
| `meets` | ✅ Fixed | Calls `intervalMeets` UDF |
| `starts` | ✅ Fixed | Calls `intervalStarts` UDF |
| `ends` | ✅ Fixed | Calls `intervalEnds` UDF |

### Wiring Gaps - ✅ RESOLVED

| UDF | Status | Implementation |
|-----|--------|----------------|
| `AgeInYearsAt` | ✅ Wired | `_translate_age_at_function()` calls UDF |
| `AgeInMonthsAt` | ✅ Wired | `_translate_age_at_function()` calls UDF |
| `AgeInDaysAt` | ✅ Wired | `_translate_age_at_function()` calls UDF |
| `Latest` | ✅ Wired | Function translator dispatches to UDF |
| `Earliest` | ✅ Wired | Function translator dispatches to UDF |
| `weeksBetween` | ✅ Wired | DurationBetween maps to UDF |
| `millisecondsBetween` | ✅ Wired | DurationBetween maps to UDF |
| `differenceIn*` | ✅ Wired | DifferenceBetween maps to UDFs |

### MEDIUM Priority Gaps - ✅ RESOLVED

| Gap | Status | Implementation |
|-----|--------|----------------|
| `predecessor of` | ✅ Fixed | `_translate_predecessor()` implemented |
| `successor of` | ✅ Fixed | `_translate_successor()` implemented |
| `GeometricMean` | ✅ Fixed | Uses EXP(AVG(LOG(x))) pattern |
| `Product` | ✅ Fixed | Uses EXP(SUM(LOG(x))) pattern |
| `millisecond from` | ✅ Fixed | Added to DateComponent handler |

### REMAINING Gaps (Low Priority)

| Gap | Impact | Notes |
|-----|--------|-------|
| `LastPositionOf` | String search | Can delegate to FHIRPath |
| `timezoneoffset from` | Timezone handling | Rarely used in measures |
| `collapse` | Interval list merge | Complex interval operation |
| `expand` | Interval expansion | Complex interval operation |
| `ConvertsTo*` functions | Type tests | Can delegate to FHIRPath |
| Multi-source queries | Cross joins | Partial support, needs CROSS JOIN |

---

## Recommendations

### Immediate Actions (Sprint 1)

1. **Add Missing AST Handlers in expressions.py:**
   - `DurationBetween` → call `YearsBetween`/`MonthsBetween` macros
   - `DateComponent` → call `Year`/`Month`/`Day` macros
   - `ExistsExpression` → generate `array_length > 0`
   - `AggregateExpression` → dispatch to aggregate functions

2. **Wire Existing UDFs:**
   - Connect `AgeInYearsAt` UDF in function translator
   - Connect `Latest`/`Earliest` UDFs in function translator

### Short-term Actions (Sprint 2)

3. **Add Query Operator Handlers:**
   - `SkipExpression`, `TakeExpression`
   - `FirstExpression`, `LastExpression`
   - `AnyExpression`, `AllExpression`

4. **Complete Interval Operations:**
   - Wire `intervalWidth`, `collapse`, `expand`

### Medium-term Actions (Sprint 3)

5. **Statistical Completeness:**
   - Add `GeometricMean` UDF
   - Add `Product` UDF

6. **String Completeness:**
   - Add `LastPositionOf` to string UDFs
   - Add `SplitOnMatches` via FHIRPath

### Long-term Actions

7. **Full CQL R1.5 Compliance:**
   - Run official CQL test suite
   - Address failing tests
   - Document compliance percentage

---

## Appendix: File Locations

| Component | Path |
|-----------|------|
| **CQL Parser** | `cql-py/src/cql_py/parser/` |
| **Translator V2** | `cql-py/src/cql_py/translator_v2/` |
| **CQL UDFs** | `duckdb-cql-py/src/duckdb_cql_py/udf/` |
| **CQL Macros** | `duckdb-cql-py/src/duckdb_cql_py/macros/` |
| **FHIRPath UDFs** | `duckdb-fhirpath-py/src/duckdb_fhirpath_py/udf.py` |
| **FHIRPath Functions** | `duckdb-fhirpath-py/src/duckdb_fhirpath_py/functions/` |
| **FHIRPath Engine** | `fhirpath-py/src/fhirpath_py/engine/invocations/` |
| **Test Files** | `cql-py/tests/` |

---

## References

- **CQL R1.5 Specification:** https://cql.hl7.org/
- **CQL Reference (Appendix B):** https://cql.hl7.org/09-b-cqlreference.html
- **FHIRPath Specification:** http://hl7.org/fhirpath/
- **QICore Measures:** https://build.fhir.org/ig/cqframework/dqm-content-qicore-2025/
- **Project Plan:** `docs/PLAN-CQL-TO-SQL-TRANSLATOR.md`
