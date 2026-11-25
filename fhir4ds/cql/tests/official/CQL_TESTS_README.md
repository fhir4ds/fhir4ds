# Official CQL Test Suite

This directory contains the official CQL (Clinical Quality Language) test suite cloned from [cqframework/cql-tests](https://github.com/cqframework/cql-tests).

## Provenance / Pin

- **Repository**: https://github.com/cqframework/cql-tests
- **Pinned commit**: `0a8f7d32809cd1b8f595b89e415bcfc855913b28`
- **Commit date**: 2026-11-21
- **Subject**: `Merge pull request #186 from bryantaustin13/truncate-integer-range-tests`
- **Previous pin**: `316c4939be3a513fa775d78a97c31c6eae018b7a` (2026-11-16)

How this directory is vendored: **as plain files committed to this repository**
(vendored snapshot). There is no submodule and no `.gitmodules` entry for it.

### Why vendored and not a submodule (FHIR4-45, 2026-11-24)

Until this card the `cql-tests` entry was a bare **gitlink** with no
`.gitmodules` entry. A gitlink with no module declaration cannot be
materialised: `git worktree add` and a fresh CI checkout both leave an EMPTY
directory, and `git submodule update --init` cannot help because git has no URL
to fetch. `run_cql.py` then printed "CQL tests directory not found", exited
**0**, and left the previously committed `conformance/reports/cql_report.json`
untouched — so `run_all.py`/CI read the previous run's numbers and reported
them as a pass. The gate could be green while testing nothing.

Precedent considered:

| corpus | wiring | why |
|---|---|---|
| `fhir4ds/viewdef/tests/spec_tests/` | **vendored** (22 JSON fixtures) | official third-party corpus for the ViewDefinition gate — the closest analogue of this directory |
| `tests/data/ecqm-content-qicore-2025/` | **vendored** (~43k files) | measure content for the DQM gate |
| `tests/data/dqm-content-qicore-2026/`, `tests/data/dqm-content-cms-2025/` | **submodules**, declared in `.gitmodules` | the only submodule-wired corpora; both have a module entry so `git submodule update` can materialise them |

Submodule was rejected because it would not have fixed the observed failure:

- `git worktree add` (this project's campaign workflow) does not materialise
  submodules either, so the empty-directory failure would persist.
- No CI workflow runs `git submodule update` for this path
  (`.github/workflows/conformance.yml` initialises only
  `tests/data/ecqm-content-qicore-2025`), so CI would still have been empty.

Vendoring makes the corpus present in every checkout by construction, which is
the property a gate needs. It is affordable: the snapshot is ~536 KB across
16 XML files. The upstream commit pin is recorded in
[`corpus_manifest.json`](corpus_manifest.json) and in this note.

Snapshot contents: `tests/cql/*.xml` (the corpus, verbatim),
`tests/testSchema.xsd`, `LICENSE`, `CHANGE_MANAGEMENT.md`, `README.md`.
Upstream's `.git` and `.github/` are deliberately not vendored.

### Gate integrity contract (FHIR4-45)

`conformance/scripts/run_cql.py` treats corpus problems as gate failures, and
`conformance/scripts/run_all.py` treats a suite that could not run as a master
failure. `corpus_manifest.json` is the single source of truth for the expected
size; update it in the same commit as any corpus refresh.

| condition | exit code | report | master runner |
|---|---|---|---|
| corpus directory **absent** (empty checkout / stale worktree) | **2** | stale report deleted, explicit `__corpus_integrity__` failure written | suite reported NOT RUN, gate exits **1** |
| corpus present but **empty** (no `*.xml`) | **2** | same | same |
| corpus **partial** (fewer XML files than the manifest pin) | **2** | same | same |
| corpus present, but **fewer test cases** collected than the pin | **2** | real per-file numbers kept **plus** a failing `corpus_test_count_shortfall` sentinel | gate exits **1** |
| a corpus XML file **cannot be parsed** | 0 if counts still match, else 2 | that file recorded as a failed test (never silently dropped) | per-case failure |
| corpus **larger** than the pin | 0 | runs every file present | loud `WARNING`: the pin note is stale |
| **normal** run | 0 | fresh report | normal summary |

Two further rules in `run_all.py`, because reading whatever report is on disk is
how a stale pass leaks into CI (AGENTS.md records the same pattern reporting a
stale `dqm_report.json` as 47/47):

1. A child's non-zero exit is never swallowed — the suite is reported as
   NOT RUN and contributes no numbers to the totals.
2. A child that exits **0 without rewriting its report** is a failure. Each
   report's `(mtime_ns, size)` is captured before the child runs and verified
   after; an unchanged fingerprint means the suite tested nothing. A report
   containing **0 tests** is a failure too.

A run where every suite executed and some individual *cells* fail still exits 0
with an `INCOMPLETE` banner: the pinned corpus carries a handful of cells whose
upstream fixture PRs are still open (see below), so a rate-based non-zero exit
would keep the gate permanently red and train readers to ignore it.

### Refreshing the pin

Both halves of the pin must move together — the vendored files and
`corpus_manifest.json` (commit, date, subject, counts):

```bash
git clone https://github.com/cqframework/cql-tests /tmp/cql-tests
cd /tmp/cql-tests && git checkout --detach <upstream-main-sha>
rsync -a --delete \
  --exclude '.git' --exclude '.github' \
  /tmp/cql-tests/ ~/src/fhir4ds/fhir4ds/cql/tests/official/cql-tests/
cd ~/src/fhir4ds
# update corpus_manifest.json (pin, pin_date, pin_subject, xml_file_count, test_count)
# and the counts table below, then:
./scripts/capped.sh 20 8 python3 conformance/scripts/run_cql.py
```

Do **not** hand-edit the vendored XML to silence a failure — the pin is
upstream's content, and the failures are the honest inventory.

### Upstream PRs NOT yet in this pin

Two open cqframework/cql-tests PRs correct fixtures whose oracles this pin
still carries; the engine already answers the corrected values, so these cells
fail until the PRs merge and the pin moves past them:

- **#183** (`Count duration uncertainties from the end of an imprecise start`)
  — `CqlDateTimeOperatorsTest.xml::DateTimeDurationBetweenUncertainInterval`
  (expects 17, spec/reference arithmetic gives 16) and
  `::TimeDurationBetweenHourDiffPrecision2` (expects 1, gives `[0, 1]`).
  See the AMUX-169 entry in `fhir4ds/cql/AGENTS.md`.
- **#184** (`Time ms-null`) — `CqlIntervalOperatorsTest.xml::TimeProperContainsNull`
  and `::TimeProperInNull` still pin `null` at `version="1.0"`; #184 caps those
  at `versionTo="1.5.2"` and adds the 1.5.3 `false` pins. See the AMUX-171
  entry in `fhir4ds/cql/AGENTS.md`.

Do **not** hand-edit the vendored XML to silence them — the pin is upstream's
content, and the failures are the honest inventory.

## Overview

Counted at the pinned commit (the CQL gate runs every `<test>` element; the
`versionTo`-superseded cells are counted too, as skips/superseded passes):

- **Total Test Cases**: 2,043
- **Test Files**: 16 XML files
- **Groups**: 210
- **Total Lines**: 11,082

## Test Categories

| Category | File | Test Cases | Groups | Lines |
|----------|------|------------|--------|-------|
| **Interval Operators** | CqlIntervalOperatorsTest.xml | 429 | 35 | 2,282 |
| **Date/Time Operators** | CqlDateTimeOperatorsTest.xml | 322 | 17 | 1,825 |
| **Comparison Operators** | CqlComparisonOperatorsTest.xml | 281 | 10 | 1,221 |
| **List Operators** | CqlListOperatorsTest.xml | 268 | 32 | 1,470 |
| **Arithmetic Functions** | CqlArithmeticFunctionsTest.xml | 261 | 23 | 1,231 |
| **String Operators** | CqlStringOperatorsTest.xml | 98 | 17 | 569 |
| **Aggregate Functions** | CqlAggregateFunctionsTest.xml | 84 | 15 | 473 |
| **Value Literals & Selectors** | ValueLiteralsAndSelectors.xml | 78 | 14 | 491 |
| **Type Operators** | CqlTypeOperatorsTest.xml | 59 | 14 | 362 |
| **Logical Operators** | CqlLogicalOperatorsTest.xml | 39 | 5 | 216 |
| **Types** | CqlTypesTest.xml | 36 | 11 | 283 |
| **Nullological Operators** | CqlNullologicalOperatorsTest.xml | 35 | 4 | 204 |
| **Query Tests** | CqlQueryTests.xml | 20 | 8 | 137 |
| **Conditional Operators** | CqlConditionalOperatorsTest.xml | 14 | 3 | 145 |
| **Aggregate Test** | CqlAggregateTest.xml | 12 | 1 | 127 |
| **Errors & Messaging** | CqlErrorsAndMessagingOperatorsTest.xml | 7 | 1 | 46 |

## Test Structure

### XML Format

Tests are expressed in an XML format defined by the [Test Schema](cql-tests/tests/testSchema.xsd):

```xml
<tests name="TestSuiteName" reference="https://cql.hl7.org/..." version="1.0">
    <capability code="capability-code"/>
    <group name="GroupName" version="1.0">
        <test name="TestName" version="1.0">
            <expression>1 + 1</expression>
            <output>2</output>
        </test>
    </group>
</tests>
```

### Test Elements

- **`<tests>`**: Root container for a test suite
  - `name`: Computer-friendly test suite name
  - `version`: CQL version where features were introduced
  - `reference`: Link to specification section

- **`<group>`**: Logical grouping of related tests
  - `name`: Unique group name within suite

- **`<test>`**: Individual test case
  - `name`: Test case identifier
  - `skipStaticCheck`: Skip type checking if true
  - `ordered`: Check result order for lists
  - `mode`: Evaluation mode (strict, lenient, element, cda, tx)

- **`<expression>`**: CQL expression to evaluate
  - `invalid`: Expected error type (false, syntax, semantic, execution, true)

- **`<output>`**: Expected result
  - `type`: Output type (boolean, code, date, dateTime, decimal, integer, Quantity, string, time)

- **`<capability>`**: Declares required implementation capability
  - `code`: Capability code from CQL Language Capability Codes
  - `value`: Optional qualifier

### Output Types

| Type | Description |
|------|-------------|
| `boolean` | True/false value |
| `code` | CQL code literal |
| `date` | Date value |
| `dateTime` | Date with time |
| `decimal` | Decimal number |
| `integer` | Integer number |
| `Quantity` | Quantity with unit |
| `string` | String value |
| `time` | Time value |

### Invalid Types (Error Expectations)

| Type | Description |
|------|-------------|
| `false` | Expression should evaluate successfully |
| `syntax` | Expected syntax error |
| `semantic` | Expected semantic error |
| `execution` | Expected execution error |
| `true` | Expected runtime error |

## Test Groups by Category

### 1. Arithmetic Functions (212 tests)
Operators: `Abs`, `Add`, `Ceiling`, `Divide`, `Floor`, `Exp`, `HighBoundary`, `Log`, `LowBoundary`, `Ln`, `MinValue`, `MaxValue`, `Modulo`, `Multiply`, `Negate`, `Precision`, `Predecessor`, `Power`, `Round`, `Subtract`, `Successor`, `Truncate`, `TruncatedDivide`

### 2. Comparison Operators (198 tests)
Operators: `Between`, `Equal`, `Greater`, `GreaterOrEqual`, `Less`, `LessOrEqual`, `Equivalent`, `NotEqual`

### 3. Date/Time Operators (318 tests)
Operators: `Add`, `After`, `Before`, `DateTime`, `DateTimeComponentFrom`, `Difference`, `Duration`, `Now`, `SameAs`, `SameOrAfter`, `SameOrBefore`, `Subtract`, `Time`, `TimeOfDay`, `Today`

### 4. Interval Operators (412 tests)
Operators: `After`, `Before`, `Collapse`, `Expand`, `Contains`, `End`, `Ends`, `Equal`, `Except`, `In`, `Includes`, `IncludedIn`, `Intersect`, `Equivalent`, `Meets`, `MeetsBefore`, `MeetsAfter`, `NotEqual`, `OnOrAfter`, `OnOrBefore`, `Overlaps`, `OverlapsBefore`, `OverlapsAfter`, `PointFrom`, `ProperContains`, `ProperIn`, `ProperlyIncludes`, `ProperlyIncludedIn`, `Start`, `Starts`

### 5. List Operators (212 tests)
Operators: `Sort`, `Contains`, `Descendents`, `Distinct`, `Equal`, `Except`, `Exists`, `Flatten`, `First`, `In`, `Includes`, `IncludedIn`, `Indexer`, `IndexOf`, `Intersect`, `Last`, `Length`, `Equivalent`, `NotEqual`, `ProperContains`, `ProperIn`, `ProperlyIncludes`, `ProperlyIncludedIn`, `SingletonFrom`, `Skip`, `Tail`, `Take`, `Union`

### 6. String Operators (81 tests)
Operators: `Combine`, `Concatenate`, `EndsWith`, `Indexer`, `LastPositionOf`, `Length`, `Lower`, `Matches`, `PositionOf`, `ReplaceMatches`, `Split`, `StartsWith`, `Substring`, `Upper`, `ToString`

### 7. Logical Operators (39 tests)
Operators: `And`, `Implies`, `Not`, `Or`, `Xor`

### 8. Nullological Operators (22 tests)
Operators: `Coalesce`, `IsNull`, `IsFalse`, `IsTrue`

### 9. Type Operators (35 tests)
Operators: `As`, `Convert`, `Is`, `ToBoolean`, `ToConcept`, `ToDateTime`, `ToDecimal`, `ToInteger`, `ToQuantity`, `ToString`, `ToTime`

### 10. Aggregate Functions (50 tests)
Operators: `AllTrue`, `AnyTrue`, `Avg`, `Product`, `Count`, `Max`, `Median`, `Min`, `Mode`, `PopulationStdDev`, `PopulationVariance`, `StdDev`, `Sum`, `Variance`

### 11. Conditional Operators (9 tests)
Operators: `If-Then-Else`, `Case` (standard, selected)

### 12. Value Literals & Selectors (66 tests)
Types: `Null`, `Boolean`, `Integer`, `Decimal`, `String`, `DateTime`, `Time`, `List`, `Interval`, `Tuple`, `Quantity`, `Code`, `Concept`, `Instance`

## Compliance Requirements

### Minimum Compliance (Core CQL)

To achieve minimum CQL compliance, an implementation must pass tests in:

1. **Value Literals & Selectors** - All basic type literals
2. **Arithmetic Functions** - Basic math operations
3. **Comparison Operators** - Equality and ordering
4. **Logical Operators** - Boolean logic
5. **Nullological Operators** - Null handling

### Standard Compliance

Additional categories required:

6. **String Operators** - String manipulation
7. **Conditional Operators** - If-then-else, case
8. **List Operators** - Collection operations
9. **Aggregate Functions** - Aggregations

### Full Compliance

All categories including:

10. **Date/Time Operators** - Temporal operations
11. **Interval Operators** - Interval math
12. **Type Operators** - Type conversions
13. **Query Tests** - CQL query expressions

## Capabilities System

Tests declare required capabilities using the `<capability>` element:

```xml
<capability code="arithmetic-operators"/>
<capability code="decimal-precision-and-scale" value="28,8"/>
<capability code="ucum-unit-conversion-support"/>
<capability code="system.long"/>
```

### Common Capability Codes

| Code | Description |
|------|-------------|
| `literals` | Value literal support |
| `arithmetic-operators` | Math operations |
| `decimal-precision-and-scale` | Decimal precision (value: precision,scale) |
| `ucum-unit-conversion-support` | UCUM unit handling |
| `system.long` | Long integer type |
| `precision-operators-for-decimal-and-date-time-types` | Precision functions |

## Running Tests

Use the [CQL Tests Runner](https://github.com/cqframework/cql-tests-runner) to execute these tests against your implementation.

### Integration Approach

For cqlpy integration:

1. Parse XML test files using the schema
2. Extract expression and expected output
3. Evaluate expression through CQL engine
4. Compare result with expected output
5. Handle capability declarations to skip unsupported tests

## Version History

Tests are versioned according to the CQL specification version where features were introduced:

- `version="1.0"` - CQL 1.0 (baseline)
- `version="1.3"` - CQL 1.3 additions
- `version="1.4"` - CQL 1.4 additions
- `version="1.5"` - CQL 1.5 additions

Some tests also have `versionTo` indicating when a feature was deprecated.

## References

- [CQL Specification](https://cql.hl7.org/)
- [CQL Reference](https://cql.hl7.org/09-b-cqlreference.html)
- [CQL Developers Guide](https://cql.hl7.org/03-developersguide.html)
- [Test Schema](cql-tests/tests/testSchema.xsd)
- [Change Management](cql-tests/CHANGE_MANAGEMENT.md)
