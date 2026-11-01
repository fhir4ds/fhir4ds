# Feature Plan Draft: WASM CQL Complete Runtime Parity

## Objective

Make every CQL expression or library supported by the existing Python
translator executable in DuckDB-WASM using only compiled DuckDB C++ extensions
and pure DuckDB SQL macros at execution time.

This explicitly supersedes the narrower browser-demo milestone. Passing the
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
  to ELM; this project translates those supported constructs directly to SQL,
  so each emitted SQL function or macro is part of the runtime contract.
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

The previous loop delivered a browser-required surface for the known demo paths,
including `fhirpath_repeat`, formerly WASM-only CQL interval/boundary helpers,
list/logical overloads, and C++ valueset cache functions.

That is not full parity. Initial name-level discovery shows:

- Python DuckDB UDF registrations: about 193 names.
- C++ DuckDB UDF registrations: about 145 names.
- SQL macro registrations: about 102 names.
- Python UDF names not covered by C++ UDF or SQL macro by exact name: about 67.
- C++ conflict names still shadowed by Python in native registration: 34.

High-risk uncovered or unproven areas include:

- Age/week aliases and `CalculateAgeIn*` variants.
- `CQLMessage`, `ConvertQuantity`, and variable helper UDFs.
- Precision-aware date/time helpers: `cqlSameOrBefore*`, `cqlBefore*`,
  `cqlAfter*`, `cqlDateTime*`, `cqlUncertain*`, `cqlDurationBetween`,
  `differenceIn*`.
- Interval helpers such as `expand*`, `interval_size`, and currently shadowed
  interval/boundary functions.
- Deprecated/direct string UDF names such as `stringLength`, `stringMatches`,
  and `stringReplace` if the translator or public runtime can emit/call them.

These counts are a discovery aid only. The implementation must generate the
authoritative inventory from source, translator output, macros, direct C++
catalogs, and WASM/runtime catalogs.

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

Add a maintained script or pytest helper, likely under
`fhir4ds/cql/duckdb/tests/integration/` or `tools/`, that computes:

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

Extend Playwright or Node/browser tests so they do more than run fixed samples:

- Load the rebuilt WASM extensions.
- Generate SQL for a representative arbitrary CQL library in Pyodide.
- Execute every translated definition in DuckDB-WASM.
- Assert no missing function errors and compare expected outputs.
- Include at least one CMS/DQM-style library with valueset use.

The native direct-extension test remains necessary, but browser execution is
the release gate because dynamic linking and macro registration can diverge.

### Phase 6: Release Artifact Gate

If implementation changes C++ extensions, Python package files, or browser
assets:

1. Rebuild native C++ extensions.
2. Rebuild WASM side modules with the pinned Emscripten SDK.
3. Rebuild the wheel and keep only the current wheel in `web/wasm-demo/public/`.
4. Rebuild `web/wasm-demo`.
5. Refresh `web/website/static/wasm-app`.
6. Verify standalone demo and website static output use the refreshed assets.

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

