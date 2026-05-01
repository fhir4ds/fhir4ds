# FHIRPath DuckDB Extension (C++)

Native C++ DuckDB extension implementing a FHIRPath evaluation engine. Evaluates FHIRPath expressions against FHIR JSON resources directly inside DuckDB queries.

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

# 4. Test (72 assertions)
./build/release/test/Release/unittest.exe "*fhirpath*"
```

On Windows with VS 2022, use the full cmake path:
```
"C:/Program Files/Microsoft Visual Studio/2022/Community/Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe"
```

## DuckDB Version Compatibility

Pinned to **DuckDB v1.5.2**. Key constraints:

- **C++11 only** — DuckDB compiles with C++11. No `std::optional`, `std::variant`, `std::string_view`, structured bindings, or other C++17+ features.
- **yyjson namespace** — yyjson types are wrapped in `namespace duckdb_yyjson`. Use `using namespace duckdb_yyjson;` in .cpp files. Forward declarations must be inside `namespace duckdb_yyjson {}`.
- **No `ExtensionUtil`** — Removed in v1.5.0. Use `ExtensionLoader` and `loader.RegisterFunction()`.
- **No `ExpressionState::GetFunctionData<T>()`** — Use `FunctionLocalState` via `init_local_state` callback + `ExecuteFunctionState::GetFunctionState(state)`.
- **`ListVector::GetData()` returns a pointer** — Use `auto list_entries = ...` not `auto &list_entries = ...`.

## Architecture

```
src/
  fhirpath_extension.cpp    — Extension entry, 10 UDF registrations, bind/state management
  include/
    fhirpath_extension.hpp  — Extension class declaration
  fhirpath/
    lexer.hpp/cpp            — Tokenizer (314 lines)
    parser.hpp/cpp           — Recursive descent parser → AST (509 lines)
    evaluator.hpp/cpp        — Tree-walking evaluator (1505 lines)
    ast.hpp                  — AST node types with C++11 tagged union (NodeValue)
    expression_cache.hpp     — LRU cache (1024 entries) for parsed expressions
    arena_allocator.hpp      — Per-batch arena allocator for temporary strings
```

### Pipeline: Expression String → Result

1. **Lexer** tokenizes the FHIRPath expression
2. **Parser** builds a shared_ptr AST (`ASTNode` tree)
3. **Evaluator** walks the AST against a yyjson-parsed FHIR resource
4. Results are converted from `FPValue` collection to DuckDB output types

### Performance Optimizations

- **Bind-time compilation**: Constant FHIRPath expressions are parsed once at bind time
- **Expression cache**: LRU cache (1024 entries) avoids re-parsing identical expressions
- **Simple path fast path**: Expressions like `birthDate` or `name.given` (pure member access chains) bypass the full evaluator and use direct yyjson field lookup. Falls back to full evaluator on miss (e.g., choice types).
- **Arena allocator**: Per-batch temporary string allocation reuse

## Registered UDFs

| Function | Signature | Returns |
|---|---|---|
| `fhirpath` | `(JSON, VARCHAR) → VARCHAR[]` | All matching values as string list |
| `fhirpath_text` | `(JSON, VARCHAR) → VARCHAR` | First matching value as string |
| `fhirpath_number` | `(JSON, VARCHAR) → DOUBLE` | First matching value as double |
| `fhirpath_date` | `(JSON, VARCHAR) → VARCHAR` | First date value, normalized to YYYY-MM-DD |
| `fhirpath_bool` | `(JSON, VARCHAR) → BOOLEAN` | First matching value as boolean |
| `fhirpath_json` | `(JSON, VARCHAR) → VARCHAR` | Results as JSON array string |
| `fhirpath_timestamp` | `(JSON, VARCHAR) → VARCHAR` | First datetime value as-is |
| `fhirpath_quantity` | `(JSON, VARCHAR) → VARCHAR` | First quantity value as string |
| `fhirpath_is_valid` | `(VARCHAR) → BOOLEAN` | Whether expression parses successfully |

## Supported FHIRPath Features

- **Navigation**: member access (`name.given`), indexing (`[0]`), `ofType()`
- **Filtering**: `where()`, `exists()`, `extension(url)`
- **Functions**: `count()`, `first()`, `last()`, `single()`, `empty()`, `hasValue()`, `not()`, `all()`, `allTrue()`, `anyTrue()`, `startsWith()`, `endsWith()`, `contains()`, `matches()`, `replace()`, `substring()`, `length()`, `upper()`, `lower()`, `trim()`, `toInteger()`, `toDecimal()`, `toString()`, `toDate()`, `toDateTime()`, `toBoolean()`, `toQuantity()`, `abs()`, `ceiling()`, `floor()`, `round()`, `ln()`, `log()`, `power()`, `sqrt()`, `truncate()`, `iif()`, `select()`, `repeat()`, `distinct()`, `combine()`, `union()`, `intersect()`, `exclude()`, `tail()`, `take()`, `skip()`
- **Operators**: `=`, `!=`, `<`, `>`, `<=`, `>=`, `and`, `or`, `xor`, `implies`, `+`, `-`, `*`, `/`, `mod`, `div`, `&` (string concat), `|` (union), `in`, `contains`
- **Choice types**: `value` resolves `valueString`, `valueQuantity`, etc. (FHIR `value[x]` pattern)
- **Literals**: integer, decimal, string, boolean, date (`@2024-01-01`), dateTime, time, quantity

## Test File

`test/sql/fhirpath.test` — 72 assertions covering all UDFs, NULL handling, complex where clauses, string functions, choice types, and malformed input.

---

## Audit Findings (2026-03-31)

See `docs/architecture/AUDIT_REPORT.md` §7 for full details.

### Critical
1. **Thread safety in `FhirpathIsValidFunction`** (`fhirpath_extension.cpp:740`) — calls shared parser with mutable state, no synchronization.
2. **Static `null_ast` race condition** (`fhirpath_extension.cpp:110-111,117-118`) — shared_ptr returned by reference to concurrent callers.
3. **15 bare `catch(...)` blocks** swallowing all exceptions including OOM.

### Design Debt
- 4,879-line `evaluator.cpp` monolith — 70+ functions in one file.
- `std::regex` compiled per-call in hot paths (`evaluator.cpp:1736,1761`) — 1-10ms each.
- Hardcoded 40-field FHIR type mapping (`evaluator.cpp:118-153`).
- Incomplete JSON escaping — missing control characters (`fhirpath_extension.cpp:617-631`).
- Fast path / full evaluator inconsistency — different array handling.

### Test Gaps
- No C++ unit tests. Only 72 SQL assertions.
- No fuzz testing for parser/evaluator.
- No concurrent execution tests.

### Remediation Status: COMPLETE (2026-04-02)
- Thread-local parser for FhirpathIsValidFunction
- Thread-local null_ast and empty vector (race condition fix)
- All catch(...) → catch(const std::exception&) (evaluator.cpp + extension.cpp)
- Thread-local regex cache (get_cached_regex) eliminating per-call compilation
- Complete JSON escaping including all control characters (0x00-0x1F, \b, \f)
- Build: ✅ | Tests: 72 SQL assertions pass

### Known Fragile Areas (Found by QA - 2026-04-30)
- **Quantity Equality**: `=` incorrectly treats equivalent quantities as equal (converts units instead of strict match).
- **String Concatenation (`&`)**: Incorrectly accepts multi-item collections, concatenating their first elements instead of throwing an error.
- **Nested Collections**: Navigation into nested JSON arrays (e.g., `[[1, 2]]`) does not flatten them into the FHIRPath collection; instead, inner arrays are serialized to JSON strings.
- **Substring boundaries**: Negative start indexes wrap or default to 0 instead of returning empty as required by spec.
- **Singleton Enforcement (Systemic)**: Binary math operators, comparison operators, and most string/math functions silently use the first element of multi-item collections instead of throwing an error or returning empty per the FHIRPath specification.
- **Polymorphic Metadata**: Accessing choice types directly by their full name (e.g., `valueQuantity`) fails to populate `fhir_type` metadata, causing `ofType()` filters to fail.
