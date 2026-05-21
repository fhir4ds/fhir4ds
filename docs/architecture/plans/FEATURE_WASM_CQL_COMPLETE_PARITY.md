# Feature: WASM CQL Complete Runtime Parity

## Status

Implemented and verified.

Target release: `0.0.6`

Verification date: 2026-05-16

## Objective

Make every CQL expression or library supported by the existing Python
translator executable in DuckDB-WASM using only compiled DuckDB C++ extensions
and pure DuckDB SQL macros at execution time.

This is broader than the previous browser-demo surface milestone. Passing the
current playground/CMS samples is not sufficient. The required contract is:

1. Pyodide may parse CQL and generate SQL.
2. DuckDB-WASM executes the generated SQL.
3. Generated SQL never depends on Python `duckdb` package UDF registration.
4. Native registration may keep Python fallback for development installs, but
   release validation must prove the WASM/no-Python execution path is complete.

## Spec Alignment

- CQL 1.5.3 Appendix B is the normative operator/function reference and covers
  types, logical, nullological, comparison, arithmetic, string, date/time,
  interval, list, aggregate, clinical, and messaging operators.
- CQL 1.5.3 translation semantics maps CQL declarations and operator families
  to ELM; this project translates supported constructs directly to SQL, so each
  emitted SQL function or macro is part of the runtime contract.
- FHIRPath Normative Release defines collection behavior, path traversal,
  singleton evaluation, type operations, and FHIR navigation semantics used by
  translated CQL and ViewDefinition/FHIRPath UDFs.
- SQL-on-FHIR/ViewDefinition browser execution continues to require C++ FHIRPath
  UDFs and SQL macros only.

Reference URLs:

- https://cql.hl7.org/09-b-cqlreference.html
- https://cql.hl7.org/06-translationsemantics.html
- https://cql.hl7.org/05-languagesemantics.html
- https://hl7.org/fhirpath/N1/index.html

## Current State

The implementation closes the translator-required no-Python CQL runtime gaps
found by the strict official-suite gate. The final browser contract is:

- Pyodide can translate supported CQL to SQL.
- DuckDB-WASM executes the generated SQL with `fhirpath.duckdb_extension.wasm`,
  `cql.duckdb_extension.wasm`, and pure SQL macros only.
- The native strict no-Python runtime passes the official CQL XML suite:
  `1706/1706`.

New coverage includes:

- direct no-Python translate-and-execute pytest coverage for temporal,
  uncertainty, boundary, predecessor, interval-null, imprecise-DateTime
  overlap, expand, string, and age behavior;
- browser-side SQL macro registration for CQL runtime macros;
- rebuilt native CQL extension, rebuilt CQL WASM extension, rebuilt WASM demo,
  and refreshed website static `wasm-app` snapshot.

## Architecture

### Runtime Layers

- CQL parser/translator in Pyodide emits SQL only. It must not require Python
  DuckDB or Python UDF execution.
- DuckDB-WASM loads `fhirpath.duckdb_extension.wasm` and
  `cql.duckdb_extension.wasm`.
- Pure SQL macros may supplement the C++ extensions.
- Valueset runtime state must be available through C++ cache functions or
  static SQL data expansion, never through Python UDFs in browser execution.

### Inventory Boundary

Create a generated runtime contract with these columns:

- function or macro name
- source category: Python UDF, C++ UDF, SQL macro, DuckDB builtin, translator
  emitted, CMS/static SQL emitted, ViewDefinition emitted
- arity/signature where available
- runtime availability: native Python-only, native C++ direct, WASM extension,
  SQL macro
- semantic status: parity-tested, smoke-tested only, intentionally unsupported
- required by supported translator output: yes/no/unknown

The gate must fail when any function required by supported translator output is
not available through C++ UDF, SQL macro, or DuckDB builtin in a no-Python
connection.

### Supported Scope

"Any CQL" means any CQL expression/library accepted by the current fhir4ds
Python translator as supported behavior. Unsupported translator features must
fail clearly at translation time and must not be hidden by a browser runtime
fallback.

## Implementation Plan

### Phase 1: Generated Inventory And Missing-Surface Gate

Status: implemented as strict emitted-function catalog checks in
`test_wasm_translate_execute_gate.py`.

Add a maintained script or pytest helper that computes:

1. Python UDF names from `fhir4ds/cql/duckdb/udf/*.py`.
2. C++ UDF names/signatures from `extensions/cql/src/cql_extension.cpp` and
   `extensions/fhirpath/src/fhirpath_extension.cpp`.
3. SQL macro names from `fhir4ds/cql/duckdb/macros/*.py`.
4. Names emitted by translator integration/parity test libraries.
5. Names emitted by CMS/DQM/static browser SQL and ViewDefinition/browser paths.
6. Names present in a direct C++-only DuckDB connection after loading the built
   extensions without calling Python registration.

Output a JSON report in `tests/output/` or `conformance/reports/`, and fail the
strict test when a required emitted name is Python-only.

### Phase 2: Strict Translate-And-Execute Harness

Status: implemented with `no_python_connection()` in
`wasm_runtime_helpers.py`; it loads only compiled extensions and SQL macros.

Create a reusable test fixture that:

1. Parses/translates CQL using the Python translator.
2. Registers only C++ extensions and pure SQL macros in DuckDB.
3. Executes translated SQL without `fhir4ds.cql.duckdb.register()` and without
   Python UDF supplements.
4. Compares results to the Python-fallback/native registration path where the
   Python path is the current semantic oracle.

The harness must run synthetic libraries covering every supported CQL operator
family from the CQL reference:

- primitive/type/nullological/logical/comparison
- arithmetic and quantity
- string
- date/time and uncertainty
- interval
- list and aggregate
- clinical/value set
- errors and messaging
- query/retrieve/library include paths used by CMS/DQM

### Phase 3: Close Python-Only Runtime Gaps

Status: implemented for translator-required gaps discovered by the strict
official-suite no-Python run.

For each required Python-only emitted function:

- Prefer a pure SQL macro when the behavior is a direct DuckDB expression and
  does not require custom parsing, state, or complex CQL semantics.
- Implement in C++ when behavior needs CQL-specific parsing, temporal
  uncertainty, interval/quantity semantics, valueset state, or FHIR JSON
  traversal.
- If a name is legacy/public but not translator-emitted, classify it as
  direct-public surface, deprecated, or unsupported. Public deprecated names
  still need a browser-safe macro/C++ implementation if playground users can
  call them from generated SQL or examples.

Initial candidates:

- SQL macro candidates: simple string helpers, simple aliases, direct wrappers
  around DuckDB builtins, some age alias names if they map to existing C++
  functions.
- C++ candidates: `CQLMessage`, `ConvertQuantity`, precision/uncertainty
  date-time helpers, `expand*`, variable helpers if translator-emitted, and any
  interval helper whose semantics are not safely expressible in SQL.

### Phase 4: Remove Or Justify Python Shadowing

Status: translator-required runtime behavior is now proven in the no-Python
C++/macro path. Native development registration may still keep Python fallback
for non-browser installs, but the WASM release contract no longer depends on it.

For every name in `_PYTHON_PREFERRED_CPP_CONFLICTS`:

1. Add direct Python-vs-C++ parity tests covering valid values, nulls, invalid
   input, partial precision, time-only values, quantities, open/closed
   intervals, and malformed JSON.
2. Fix C++ until it matches the Python semantic oracle or a spec-cited
   correction updates both implementations.
3. Remove the name from the shadow set only after the parity tests pass.
4. Leave a documented exception only if the function is not required by
   supported browser CQL and the exception cannot affect generated WASM SQL.

The final desired state is that no translator-required function is shadowed in
native registration for conformance.

### Phase 5: Browser/WASM Gate

Status: implemented by the rebuilt WASM demo and Playwright coverage for the
standalone playground and website web component.

Extend Playwright or Node/browser tests so they do more than run fixed samples:

- Load the rebuilt WASM extensions.
- Generate SQL for a representative arbitrary CQL library in Pyodide.
- Execute every translated definition in DuckDB-WASM.
- Assert no missing function errors and compare expected outputs.
- Include at least one CMS/DQM-style library with valueset use.

The native direct-extension test remains necessary, but browser execution is
the release gate because dynamic linking and macro registration can diverge.

### Phase 6: Release Artifact Gate

Status: completed for changed artifacts in this loop.

If implementation changes C++ extensions, Python package files, or browser
assets:

1. Rebuild native C++ extensions.
2. Rebuild WASM side modules with the pinned Emscripten SDK.
3. Rebuild the wheel and keep only the current wheel in `web/wasm-demo/public/`.
4. Rebuild `web/wasm-demo`.
5. Refresh `web/website/static/wasm-app`.
6. Verify standalone demo and website static output use the refreshed assets.

## Focused Evolution Domains

After implementation and code review, run at least five focused evolution
iterations:

1. **Inventory/Sufficiency**: generated emitted-function inventory, no-Python
   native catalog, WASM catalog, and shadow-set audit.
2. **Temporal/Interval/Quantity Semantics**: precision, uncertainty, partial
   dates/times, interval algebra, units, invalid input, and edge cases.
3. **Translator Coverage**: synthetic arbitrary CQL libraries for every
   supported operator family translate and execute no-Python.
4. **Clinical/CMS/DQM Browser Runtime**: valuesets, includes, retrieves, measure
   SQL, and CMS-style browser execution.
5. **Release Regression**: full pytest, C++ SQL suites, conformance, Playwright,
   wheel/WASM/static artifacts, and install/runtime smoke tests.

## Test Strategy

Focused gates:

- Generated inventory test: required emitted names are all C++ UDF, SQL macro,
  or DuckDB builtin in no-Python mode.
- Direct no-Python native translate-and-execute tests for every CQL operator
  family.
- Python-vs-C++ parity tests for all shadowed functions and all newly added C++
  functions.
- Browser/WASM translate-and-execute tests for synthetic arbitrary CQL and
  CMS/DQM-style CQL.

Baseline validation:

```bash
python3 -m pytest fhir4ds/ -q
python3 conformance/scripts/run_all.py
cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*"
cd extensions/cql && ./build/release/test/unittest "*cql*"
cd web/wasm-demo && npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts tests/e2e/cms-measures.spec.ts
```

Release artifact validation when artifacts change:

```bash
cd extensions/fhirpath && make wasm_eh
cd ../cql && make wasm_eh
cd ../../web/wasm-demo && npm run build
node test-extension-load.mjs --skip-load
```

Actual validation from the 2026-05-16 implementation pass:

```bash
python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_wasm_translate_execute_gate.py -q
# 2 passed

cd extensions/cql && ./build/release/test/unittest "*cql*"
# 612 assertions in 2 test cases

cd extensions/fhirpath && ./build/release/test/unittest "*fhirpath*"
# 114 assertions in 2 test cases

python3 -m pytest fhir4ds -q
# 6942 passed, 5 skipped

python3 conformance/scripts/run_all.py
# Overall: 2822/2822, 100.0%

cd web/wasm-demo && npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts
# 12 passed
```

Additional strict no-Python CQL proof:

```text
CqlAggregateFunctionsTest.xml: 50/50
CqlAggregateTest.xml: 9/9
CqlArithmeticFunctionsTest.xml: 212/212
CqlComparisonOperatorsTest.xml: 198/198
CqlConditionalOperatorsTest.xml: 9/9
CqlDateTimeOperatorsTest.xml: 317/317
CqlErrorsAndMessagingOperatorsTest.xml: 4/4
CqlIntervalOperatorsTest.xml: 412/412
CqlListOperatorsTest.xml: 212/212
CqlLogicalOperatorsTest.xml: 39/39
CqlNullologicalOperatorsTest.xml: 22/22
CqlQueryTests.xml: 12/12
CqlStringOperatorsTest.xml: 81/81
CqlTypeOperatorsTest.xml: 35/35
CqlTypesTest.xml: 28/28
ValueLiteralsAndSelectors.xml: 66/66
SUMMARY: 1706/1706
FAILURE_COUNT: 0
```

Final conformance acceptance:

- ViewDefinition: 134/134.
- FHIRPath R4: 935/935.
- CQL: 1706/1706.
- DQM QI Core 2025: 47/47.
- Overall: 2822/2822.

## Acceptance Criteria

- Every SQL function/macro name emitted by supported CQL translation is present
  in a no-Python DuckDB-WASM execution path.
- No supported playground CQL fails at runtime due to a missing Python-only UDF.
- Every required Python-only UDF gap is closed by C++ or SQL macro, or is proven
  not translator-emitted and documented as unsupported/deprecated.
- `_PYTHON_PREFERRED_CPP_CONFLICTS` contains no translator-required function at
  final acceptance.
- Strict translate-and-execute tests run without Python UDF supplements.
- Direct native C++/macro-only, browser/WASM, unit pytest, C++ SQL, Playwright,
  and full conformance gates all pass.
- Release artifacts are rebuilt and website static WASM assets refreshed when
  implementation touches package, extension, or browser runtime outputs.

## Out Of Scope

- Implementing CQL features the current Python translator rejects as unsupported.
- Replacing the Python CQL translator with a C++ translator.
- Removing Python fallback support for native development installs where no
  compiled extension is available.
