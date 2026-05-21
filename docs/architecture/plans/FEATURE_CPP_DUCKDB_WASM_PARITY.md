# Feature: C++ DuckDB WASM Parity

## Status

Implemented and validated for the 0.0.6 browser runtime.

The browser-required C++/WASM function surface is now present and guarded by
direct-extension tests that do not register Python fallback UDFs. Native Python
registration intentionally shadows the known interval/time/boundary conflict
set with Python UDF macros to preserve 100% CQL conformance until the remaining
C++ edge-case semantics are closed.

Target release: `0.0.6`

## Objective

Make the WASM demos work without Python DuckDB fallback UDFs. Pyodide can continue to install `fhir4ds-v2` for CQL translation, but translated SQL must execute entirely through DuckDB-WASM using compiled FHIR4DS C++ extensions and SQL macros.

Success means:

- Every DuckDB UDF emitted into browser SQL exists in `fhirpath.duckdb_extension.wasm`, `cql.duckdb_extension.wasm`, or as a SQL macro.
- Native C++ tests exercise the same implementation as WASM for browser-required functions.
- Python fallback remains a native/development fallback only; it is not required for browser correctness.
- FHIRPath, CQL, SQL-on-FHIR/ViewDefinition, and DQM conformance do not regress from the current 100% baseline.

## Original Design Problem

The project already has native FHIRPath and CQL DuckDB extensions, but the runtime surface is not fully unified:

- `extensions/cql/src/cql_extension.cpp` has `__EMSCRIPTEN__`-only registration for several interval, boundary, and date/quantity helper functions.
- Native registration still defers those names to Python UDFs because some C++ implementations are documented as less complete than Python.
- DuckDB-WASM cannot call those Python UDFs, so the browser executes a distinct, less-tested C++ surface.
- `fhirpath_repeat` is registered by Python fallback but is not registered by `extensions/fhirpath/src/fhirpath_extension.cpp`.
- The WASM demo release path requires rebuilt `.wasm` side modules, a rebuilt wheel, a Vite build, and a copied website static snapshot.

## Spec Alignment

Normative behavior must come from these sources:

- FHIRPath Normative Release: collection singleton behavior, empty propagation, conversion behavior, and function singleton constraints. https://hl7.org/fhirpath/N1/
- CQL 1.5.3 Reference: interval, temporal, list, arithmetic, aggregate, and logical operator semantics. https://cql.hl7.org/09-b-cqlreference.html
- CQL Author's Guide: interval precision and set operation behavior, including null for interval `except` results that would not be one well-formed interval. https://cql.hl7.org/02-authorsguide.html
- SQL-on-FHIR v2 Functional Model: `column`, `where`, `forEach`, and related transforms evaluate FHIRPath expressions. https://sql-on-fhir.org/ig/functional-model.html
- SQL-on-FHIR v2 ViewDefinition: ViewDefinition column paths are FHIRPath expressions with single-column type constraints. https://sql-on-fhir.org/ig/2.0.0/StructureDefinition-ViewDefinition.html

Project invariants also apply:

- Do not introduce hardcoded clinical profile, measure, or terminology assumptions in generic runtime paths.
- Preserve FHIRPath C++ fast-path invariants for resource-type prefixes, fallthrough on type misses, JSON null handling, and yyjson pointer lifetimes.
- Keep DuckDB wrapper resilience distinct from strict core evaluator semantics where the architecture already requires it.
- Do not remove `-p no:benchmark` from pytest configuration.

## Required Runtime Contract

Browser execution contract:

1. Load `fhirpath.duckdb_extension.wasm`.
2. Load `cql.duckdb_extension.wasm`.
3. Register or create SQL macros that are pure DuckDB SQL.
4. Execute translated/generated SQL without Python `duckdb` package UDFs.

Allowed in browser:

- Pyodide CQL parsing and SQL generation.
- SQL macros.
- Static valueset CTE expansion.
- C++ valueset cache functions when interactive SQL uses `in_valueset`.

Not allowed in browser:

- Python UDF functions registered through native Python `duckdb`.
- A runtime path where a missing C++ function is silently replaced by Python.

## Implementation Plan

### Phase 1: Build The Browser UDF Inventory

Create a generated inventory that records:

- Functions registered by native `extensions/fhirpath`.
- Functions registered by native `extensions/cql`.
- Functions registered only under `__EMSCRIPTEN__`.
- Python fallback UDF names in `fhir4ds/fhirpath/duckdb/extension.py` and `fhir4ds/cql/duckdb/extension.py`.
- SQL macro names.
- Function names emitted by CQL translator tests, ViewDefinition tests, static CMS SQL, and WASM demo source.

The inventory should fail CI or release validation when a browser-required function is Python-only.

Initial high-risk names:

- CQL interval core: `intervalStart`, `intervalEnd`, `intervalWidth`, `intervalContains`, `intervalProperlyContains`, `intervalOverlaps`, `intervalBefore`, `intervalAfter`, `intervalMeets`, `intervalIncludes`, `intervalIncludedIn`, `intervalProperlyIncludes`, `intervalProperlyIncludedIn`, `intervalOverlapsBefore`, `intervalOverlapsAfter`, `intervalMeetsBefore`, `intervalMeetsAfter`, `intervalStartsSame`, `intervalEndsSame`, `intervalFromBounds`, `collapse_intervals`.
- CQL date/quantity helpers: `quantityToInterval`, `dateAddQuantity`, `dateSubtractQuantity`.
- CQL boundary helpers: `HighBoundary`, `LowBoundary`, `predecessorOf`, `successorOf`.
- CQL interval set operations: `intervalIntersect`, `intervalUnion`, `intervalExcept`, `intervalOnOrAfter`, `intervalOnOrBefore`.
- FHIRPath SQL-on-FHIR support: `fhirpath_repeat`.

Implementation note: the initial inventory is captured in `fhir4ds-private/docs/plans/WASM_FUNCTIONS.md`. Native registration now includes the former CQL WASM-only interval, boundary, date/quantity, interval set, logical boolean-list, and list-concat surfaces, plus FHIRPath `fhirpath_repeat`. In normal native Python registration, the documented conflict set is shadowed back to Python UDFs through temporary macros; direct-extension and browser tests cover the no-Python execution contract.

### Phase 2: Converge Native And WASM Registration

Do not leave browser-required functions behind `__EMSCRIPTEN__` once they are parity-tested.

For each currently WASM-only function:

1. Add native C++ parity tests against the Python fallback behavior.
2. Fix semantic gaps.
3. Register the C++ implementation in native builds.
4. Keep Python fallback registration as a no-extension fallback only.
5. Add a C++-only test that loads the extension directly and does not call `fhir4ds.cql.duckdb.register()`.

This makes the fast native test loop catch browser runtime bugs before Playwright.

### Phase 3: Finish CQL Interval And Boundary Parity

Use the existing `BoundValue` and `Interval` C++ structure, but verify it against the Python fallback for:

- Date, DateTime, Time, Integer, Decimal, and Quantity interval bounds.
- Open-ended intervals with null low or high bounds.
- Inclusive and exclusive boundaries.
- `contains`, `includes`, `properlyIncludes`, `before`, `after`, `meets`, `overlaps`, and start/end equality variants.
- Precision-aware interval operators.
- `intervalIntersect`, `intervalUnion`, and `intervalExcept`.
- `intervalExcept` returning NULL when the mathematical result is not one contiguous interval.
- Quantity bounds with unit compatibility and no unit-discarding comparison.
- Time-only values and midnight wrapping behavior.

Boundary helpers must avoid permissive parsing. Replace unchecked `atoi`/`strtod` style acceptance where it affects observable behavior. Invalid temporal components should return NULL, not a best-effort value.

### Phase 4: Finish Browser FHIRPath Surface

Add C++ coverage for `fhirpath_repeat(resource, paths_json)` unless the ViewDefinition generator is changed so browser SQL never emits it.

Preferred implementation:

- Parse `paths_json` as a JSON array of simple dotted paths.
- Perform bounded DFS over object and array children.
- Preserve SQL-on-FHIR `repeat` semantics for recursive unnesting.
- Return the same list shape as the Python UDF.
- Apply a depth guard and invalid input returns consistent with current wrapper resilience.

Also keep existing FHIRPath C++ parity tests green for wrapper functions:

- `fhirpath`
- `fhirpath_text`
- `fhirpath_number`
- `fhirpath_date`
- `fhirpath_bool`
- `fhirpath_json`
- `fhirpath_timestamp`
- `fhirpath_quantity`
- `fhirpath_is_valid`
- `fhirpath_predicate`

### Phase 5: Valueset Browser Contract

Support both browser valueset modes:

- Static CMS demo SQL may keep inlining `in_valueset` calls to CTEs.
- Interactive translated CQL that emits `in_valueset` must be able to load valuesets into the C++ cache or fail clearly when no valueset data is loaded.

Required tests:

- `cql_valueset_cache_clear`, `cql_valueset_cache_add`, `cql_valueset_cache_size`, and `in_valueset` work after loading valueset data in native C++ and WASM.
- Unknown/unloaded valuesets return the agreed Python-equivalent result, preferably SQL NULL, not silent false.
- QICore not-done valueset behavior is covered without adding new hardcoded clinical knowledge.

### Phase 6: Add Strict No-Python Runtime Gates

Add validation helpers:

- Native C++-only connection test: loads `.duckdb_extension` files directly, checks required functions, and runs focused SQL.
- Browser/WASM function-surface test: loads side modules and checks required functions through DuckDB-WASM.
- Optional strict environment mode: when `FHIR4DS_REQUIRE_CPP_UDFS=1`, registration fails if a required browser UDF would be served by Python fallback.

The strict gate should be used in release validation, not in ordinary development installs where Python fallback remains useful.

### Phase 7: Rebuild Artifacts For 0.0.6

Release steps must include:

1. Update package version references to `0.0.6`.
2. Build the Python wheel.
3. Copy the new wheel to `web/wasm-demo/public/` and remove old wheels.
4. Rebuild native C++ extensions.
5. Rebuild WASM side modules with the pinned Emscripten SDK for the current DuckDB-WASM package.
6. Copy new `.duckdb_extension.wasm` files into `web/wasm-demo/public/extensions/`.
7. Run `npm run build` in `web/wasm-demo`.
8. Replace `web/website/static/wasm-app/` with the fresh build output.
9. Run Playwright for playground, web component, and CMS measure flows.

## Test Strategy

Focused implementation tests:

- `extensions/fhirpath` SQL tests for any new `fhirpath_repeat` behavior.
- `extensions/cql` SQL tests for interval, boundary, date/quantity, valueset cache, and strict invalid-input behavior.
- Python/C++ parity tests under `fhir4ds/fhirpath/duckdb/tests/integration/` and `fhir4ds/cql/duckdb/tests/integration/`.
- Direct-extension tests that do not register Python fallbacks.
- WASM extension load tests under `web/wasm-demo`.
- CMS measure browser tests, including `cms-measures.spec.ts`.

Baseline validation:

```bash
python3 conformance/scripts/run_all.py
python3 -m pytest fhir4ds/ -x --tb=short
```

Release artifact validation:

```bash
cd extensions/fhirpath && make wasm_eh
cd ../cql && make wasm_eh
cd ../../web/wasm-demo && npm run build
npx playwright test tests/e2e/playground.spec.ts tests/e2e/web-component.spec.ts tests/e2e/cms-measures.spec.ts
```

Use the exact current validation guidance from `fhir4ds-private/docs/prompts/.ai_loop/PROC_VALIDATION.md` when implementing.

## Acceptance Criteria

- No browser-required DuckDB UDF is Python-only.
- No browser-required CQL function remains `__EMSCRIPTEN__`-only unless a native C++-only test exercises the same source through a deliberate build configuration.
- Native C++ and WASM function inventories match for required browser functions.
- FHIRPath, CQL, ViewDefinition, and DQM conformance remain at the current clean baseline.
- WASM demo standalone and website static builds both use the new 0.0.6 wheel and rebuilt extensions.
- Playwright playground, web component, and CMS measure tests pass.
- Release Engineer artifact gate is complete before final completion.

## Out Of Scope

- Rewriting the CQL translator architecture.
- Removing the Python fallback for native environments where no compiled extension is available.
- Replacing Pyodide translation with a C++ CQL translator.
- Changing public UDF names unless a compatibility alias is retained.
