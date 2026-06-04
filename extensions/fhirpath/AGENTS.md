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

### Browser/WASM Registration Invariant

SQL-on-FHIR/ViewDefinition browser SQL must not depend on Python-only FHIRPath
DuckDB UDFs. If generated browser SQL needs helper functions such as
`fhirpath_repeat`, implement and test them in the C++ extension or change the
generator so the browser path uses only C++ UDFs and SQL macros.

SQL-on-FHIR runner parity also depends on primitive metadata surviving native
evaluation. JSON numeric children must carry both their numeric value and raw
number text (`1.0` scale matters for `precision()`, `lowBoundary()`, and
`highBoundary()`), FHIR `date`/`dateTime`/`time` strings must coerce by
field/choice metadata before boundary functions, and root-level
`where(criteria)` must dispatch through the same filter implementation as
chained `.where(criteria)`. This was fixed by the SOF-VD-11 SKEPTIC fresh
rerun on 2026-06-01; keep `test_environment_type_parity.py`,
ViewDefinition runner regressions, and native/fallback official spec_tests
aligned after evaluator changes.

`fhirpath_repeat` is a public SQL-on-FHIR compatibility surface. Repeat paths
are FHIRPath expressions, not simple key chains; native C++ must stay aligned
with the Python fallback for recursive expression evaluation, duplicate-node
unioning, and deep parsed-JSON traversal. Rebuild and copy the bundled
extension into `fhir4ds/fhirpath/duckdb/extensions/` after touching this path.

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
- `std::regex` remains a backtracking engine; review-10 added length and nested-quantifier guards, but RE2 is still the stronger long-term option for fully untrusted regex input.
- Native FHIR type reflection still uses local model/type maps; review-10 deferred generated metadata registry work.
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
- **FHIRPath FP-20 EXPLORER resource-specific code metadata rerun (2026-05-24):**
  **FIXED:** Native `fhirFieldType()` must include R4 primitive code fields
  whose names are not globally obvious. `Questionnaire.subjectType` is typed
  as FHIR `code`; without an explicit entry, native `type()` reported
  `string` while the forced Python fallback reported `code`. Keep native SQL
  assertions and `test_environment_type_parity.py` synchronized, and rebuild
  plus copy `fhirpath.duckdb_extension` after changes to primitive field
  metadata.
- **FHIRPath FP-20 HISTORIAN external constant grammar rerun (2026-05-24):**
  **FIXED:** Native `Lexer::nextToken()` must call `skipWhitespace()` after
  consuming `%` before reading an external constant payload. The formal
  grammar hides whitespace and comments between `%` and an identifier or
  string literal, so `% 'ucum'`, `%/*grammar*/'ucum'`,
  `%//grammar\n'ucum'`, `% \`context\`.id`, and
  `% \`vs-administrative-gender\`` are valid and must not be rejected as a
  bare `%` token. Keep native sqllogictest assertions and Python
  native-vs-fallback parity coverage synchronized after future lexer changes.
- **FHIRPath FP-20 SKEPTIC environment/type reflection rerun (2026-05-24):**
  **FIXED:** Native `Evaluator::evalFunction()` must guard Section 9/10
  helper signatures before generic argument evaluation. `type()` is a
  zero-argument reflection function, and malformed calls such as
  `type(false)` / `1.type(false)` must throw `FHIRPathSpecError` internally so
  public UDFs return empty/NULL and `fhirpath_is_valid()` is false.
  `defineVariable()` accepts exactly one singleton String variable name and
  one optional value expression; missing names, non-String names, empty name
  expressions, and extra arguments are invalid. Rebuild and copy
  `fhirpath.duckdb_extension` after future evaluator changes and keep
  `test_environment_type_parity.py` plus native sqllogictest assertions
  aligned.
- **FHIRPath FP-19 EXPLORER aggregate arity rerun (2026-05-24):**
  **FIXED:** Native `Evaluator::evalFunction()` now enforces the Section 7
  aggregate signature before dispatch: `aggregate()` requires exactly one
  aggregator expression and may take one optional `init` expression. Calls such
  as `a.aggregate()`, `a.aggregate($this, 0, 1)`, `aggregate()`, and
  `aggregate($this, {}, {})` throw `FHIRPathSpecError`, so public result UDFs
  are empty/NULL and `fhirpath_is_valid()` is false. Keep sqllogictest,
  Python parity coverage, and the bundled extension aligned after future
  aggregate changes.
- **FHIRPath FP-19 SKEPTIC aggregate/lexical rerun (2026-05-24):**
  **FIXED:** Native `Evaluator::fn_aggregate()` now receives the outer
  invocation focus and evaluates optional `init` against that context, not the
  aggregate input collection. This preserves resource-backed seeds such as
  `a.aggregate($total + $this, seed)` and empty-input aggregate init values.
  Native lexical parsing now rejects bare `div`/`mod` as identifiers while
  preserving formal grammar exceptions (`as`, `contains`, `in`, `is`) and
  delimited identifiers such as `` `div` `` / `` `mod` ``. `Lexer::skipWhitespace()`
  now accepts only FHIRPath whitespace characters: space, tab, LF, and CR.
  Rebuild and copy `fhirpath.duckdb_extension` after future aggregate, parser,
  or lexer changes.
- **FHIRPath FP-18 EXPLORER arithmetic rerun (2026-05-24):**
  **FIXED:** Native date/time arithmetic must never serialize out-of-range
  FHIRPath years after calendar normalization. `Evaluator::fn_dateArith()`
  now throws `FHIRPathSpecError` if the computed year is outside 1..9999,
  making literal overflow invalid and public result UDFs empty/NULL instead of
  leaking strings such as `10000-01-01` or `0000-12-31T23:59:59`. Native
  scalar/Quantity division now treats the scalar as the left operand and emits
  reciprocal units, so `2 / 1 'mg'` returns `2 '1/mg'`. Rebuild and copy the
  bundled `fhirpath.duckdb_extension` after future arithmetic changes.
- **FHIRPath FP-18 HISTORIAN arithmetic rerun (2026-05-24):**
  **FIXED:** Native `Evaluator::evalBinaryOp()` no longer allows reversed
  `Quantity + Date/DateTime/Time`, and any remaining arithmetic with temporal
  operands now throws `FHIRPathSpecError` unless it is the valid
  `Date/DateTime/Time +/- Quantity` form. `fn_dateArith()` also throws for
  unknown date/time units such as `1 'cm'`, making `fhirpath_is_valid()` false
  while result UDFs remain row-resilient. Native Decimal `+`, `-`, and `*`
  now attach fixed-scale `source_text` based on operand scale, preventing
  public text/json drift such as `1.2 * 1.8 -> 2.1600000000000001`. Rebuild
  and copy `fhirpath.duckdb_extension` after future arithmetic changes.
- **FHIRPath FP-18 SKEPTIC arithmetic rerun (2026-05-24):**
  **VERIFIED:** Native `Evaluator::fn_dateArith()` must preserve the official
  R4 second-vs-millisecond arithmetic boundary. Second-unit quantities use the
  integer portion (`0.5 seconds` is a no-op), and millisecond-unit quantities
  carry sub-second changes (`500 milliseconds`). Keep native C++ and forced
  Python fallback parity for literal and resource-backed Time/DateTime
  arithmetic in `test_arithmetic_parity.py`; rebuild and copy the bundled
  extension after touching `fn_dateArith()`.
- **FHIRPath FP-17 EXPLORER boolean logic rerun (2026-05-24):**
  **VERIFIED:** No native C++ remediation was required for pathological §6.5
  Boolean chains after the prior FP-17 fixes. The bundled native extension
  matched forced Python fallback and direct fallback for low-precedence
  `implies`, same-level left-to-right `or`/`xor`, higher-precedence `and`,
  chained root/member `not()`, non-Boolean singleton truthiness, `where()`
  predicates with `or`/`implies`, and row-resilient multi-item operand errors.
  Guard examples include `t or f implies f`, `f implies t and f`,
  `t xor {} or t`, `t or f xor t`, `not().not()`, and `true implies arr`.
  Keep `.temp/qa/fp17_explorer_probe.py` as the EXPLORER evidence pattern
  before future parser or Boolean-dispatch changes.
- **FHIRPath FP-17 HISTORIAN boolean logic rerun (2026-05-24):**
  **VERIFIED:** No native C++ remediation was required after systematic §6.5
  truth-table and §6.8 precedence coverage. Native loaded DuckDB matched the
  forced Python fallback for `and`/`or`/`xor`/`implies` empty propagation,
  singleton non-Boolean truthiness, multi-item singleton-error row resilience,
  root `not()`, method `not()`, and invalid `not(...)` arity checks. Preserve
  `test_boolean_logic_parity.py` and `.temp/qa/fp17_historian_probe.py` as
  evidence patterns before future parser or Boolean-dispatch changes.
- **FHIRPath FP-17 SKEPTIC boolean logic rerun (2026-05-24):**
  **FIXED:** Native C++ must parse root `not()` as a standalone function over
  the current focus and must reject any `not()` arguments before dispatch.
  Fresh parity showed the stale native path accepted `t.not(false)` as if the
  argument were absent and rejected root `not()` at parse time, while the
  forced Python fallback followed §6.5.3. Keep `not()`, `not(false)`, and
  `t.not(false)` coverage in `test_boolean_logic_parity.py`, and rebuild/copy
  `fhirpath.duckdb_extension` after parser or dispatcher changes.
- **FHIRPath FP-15 EXPLORER type rerun (2026-05-24):**
  **VERIFIED:** No native C++ remediation was required for Section 6.3
  `is`/`as` after fresh EXPLORER probes. The bundled extension matched forced
  Python fallback for `Any`/`System.Any`, nested choice chains such as
  `component.value.ofType(Integer).as(Integer).is(Integer)`, FHIR
  resource/complex supertypes, qualified and delimited type specifiers,
  unknown type identifiers, static multi-item singleton errors, and
  row-resilient public DuckDB result behavior. Re-run equivalent native vs
  fallback coverage before future type-operator changes.
- **FHIRPath FP-15 SKEPTIC type rerun (2026-05-24):**
  **FIXED:** Native Section 6.3 type checks must recognize `Any` as the
  root/base type before ordinary System/FHIR namespace branches. The native
  C++ extension previously treated `System.Any` as known but returned false
  for `1 is System.Any`, `Patient is System.Any`, and returned empty for
  corresponding `as(System.Any)` assertions. `fn_isType()` now returns true
  for singleton input when target `Any` is requested, so `fn_asType()` preserves
  the input through its existing `fn_isType()` call. Rebuild and copy
  `fhirpath.duckdb_extension` after future type-operator changes, and keep the
  FP-15 assertions in `extensions/fhirpath/test/sql/fhirpath.test` aligned
  with Python fallback parity tests.
- **FHIRPath FP-14 SKEPTIC comparison rerun (2026-05-24):**
  **FIXED:** Native Section 6.2 comparison must not rely on host-language
  ordering for unsupported operand types. Boolean-vs-Boolean comparisons now
  throw `FHIRPathSpecError`, multi-item comparison operands throw singleton
  errors instead of returning empty directly, and mixed calendar-duration
  keywords versus UCUM duration codes above seconds return empty before unit
  conversion. Public UDFs still convert those errors to empty/NULL, and
  `fhirpath_is_valid('true > false')`,
  `fhirpath_is_valid('(1 | 2) < 3')`, and
  `fhirpath_is_valid('1 < (2 | 3)')` are false. Seconds/milliseconds remain
  comparable. Rebuild and copy `fhirpath.duckdb_extension` after future
  native comparison changes.
- **FHIRPath FP-13 EXPLORER nested complex equality/equivalence rerun (2026-05-24):**
  **FIXED:** Native §6.1 complex equality/equivalence must apply semantic
  recursion to nested JSON children, not raw `yyjson_equals()` or exact numeric
  comparison. `jsonValuesEquivalent()` now applies Decimal equivalence to
  nested numeric children, and native JSON equality/equivalence materializes
  nested Quantity-shaped child values before comparing parent complex objects.
  Guard cases include `decObjA ~ decObjB` for `1.24` versus `1.2`,
  `rangeA = rangeB`, `rangeA ~ rangeB` for `1 cm` versus `10 mm`, and
  incompatible nested Quantity dimensions returning empty for `=`/`!=` but
  false/true for `~`/`!~`. Rebuild and copy `fhirpath.duckdb_extension` after
  future native JSON equality recursion changes.
- **FHIRPath FP-13 HISTORIAN equality/equivalence rerun (2026-05-24):**
  **FIXED:** Native §6.1 ordered collection equality must not collapse
  indeterminate singleton comparisons to false. Multi-item `=`/`!=` now uses
  tri-state singleton equality so Date/Time precision mismatches and
  incompatible Quantity dimensions propagate empty, matching the forced Python
  fallback. Guard cases include `(@2012 | @2013) = (@2012-01 | @2013)` and
  `(1 'cm' | 2 'cm') = (1 'g' | 2 'cm')`. Rebuild and copy
  `fhirpath.duckdb_extension` after touching native equality; focused native
  coverage lives in `extensions/fhirpath/test/sql/fhirpath.test`.
- **FHIRPath FP-13 SKEPTIC equality/equivalence fresh rerun (2026-05-24):**
  **FIXED:** Native §6.1.2 multi-item equivalence previously missed
  resource-backed Quantity semantics when each operand has more than one
  Quantity path result. `component.value ~ referenceRange.high` should compare
  `[1 cm, 2 cm]` against `[0.02 m, 10 mm]` order-independently with unit
  conversion. Native `valuesEquivalent` now materializes Quantity-like JSON
  values before generic JSON equivalence, and `fpValueAsQuantity()` preserves
  the JSON numeric source text so precision-aware tolerance does not match the
  wrong item first. The Python fallback also now uses half-up Decimal
  equivalence rounding, so `1.25 ~ 1.2` returns false as implied by §6.1.2 and
  §5.7.8. Keep permanent coverage in `test_equality_parity.py` and
  `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy
  `fhirpath.duckdb_extension` after native equality changes.
- **FHIRPath FP-12 EXPLORER descendants repeat semantics (2026-05-24):**
  **FIXED:** Native §5.8.2 `descendants()` must use the same "new item"
  semantics as `repeat(children())`, not append every recursive child. Repeated
  primitive or complex descendant values must be de-duplicated before further
  traversal so `descendants().count() = repeat(children()).count()` remains
  true. Native repeat keys must canonicalize JSON object key order recursively;
  otherwise equal complex values like `{"x":1,"y":2}` and `{"y":2,"x":1}` can
  drift from `repeat(children())`. Native `fn_descendants()` must not keep a
  fixed shallow depth cutoff; a 105-level resource must reach the deepest
  descendant while retaining the result-size safety guard. Regression coverage lives in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py` and
  `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled
  `fhirpath.duckdb_extension` after native tree-navigation changes.
- **FHIRPath FP-12 HISTORIAN tree/utility rerun (2026-05-24):**
  **FIXED:** Native §5.9 `trace(name : String [, projection])` must evaluate
  the ordinary `name` argument against the outer invocation focus for sourced
  calls, while evaluating only the optional projection over the traced input.
  Guard dynamic labels such as `name.trace(id).given.count()`, which previously
  returned empty because native evaluated `id` against the `HumanName` source
  instead of the Patient. The Python fallback §5.8 `descendants()` path was
  also aligned with native tree traversal so split primitive JSON fields such
  as `_birthDate.extension.valueString` are not exposed by descendants when
  `children()` hides them. Rebuild and copy `fhirpath.duckdb_extension` after
  future native trace or tree-navigation changes.
- **FHIRPath FP-12 SKEPTIC tree/utility signatures (2026-05-24):**
  **FIXED:** Native §5.8 `children()`/`descendants()` and §5.9
  `now()`/`today()`/`timeOfDay()` must reject any arguments, and
  `trace(name : String [, projection])` must require one or two arguments with
  a singleton String name. Native `trace` must also evaluate the optional
  projection even though it returns the original input, so projection errors
  preserve row-resilient empty/NULL behavior. Rebuild and copy
  `fhirpath.duckdb_extension` after touching dispatcher validation.
- **FHIRPath FP-11 EXPLORER Decimal round source text (2026-05-24):**
  **FIXED:** Native `fn_round()` now uses source Decimal text for literal
  Decimal rounding instead of formatting the rounded result through binary
  `double` when exact source text is available. This preserves
  `1.23456789.round(20) -> 1.23456789` and correct half-up tie behavior for
  `1.005.round(2)` and `(-1.005).round(2)`. Keep native sqllogictest and
  Python fallback parity coverage aligned, and rebuild/copy
  `fhirpath.duckdb_extension` after future `fn_round()` changes.
- **FHIRPath FP-11 HISTORIAN round result type (2026-05-24):**
  **FIXED:** Native C++ `fn_round()` now returns Decimal when precision is
  omitted, matching §5.7.8 `round([precision : Integer]) : Decimal` and the
  default precision of 0. `1.round()` preserves the same Decimal type behavior
  as `1.round(0)` for `type()`/`is` checks while keeping equality conformance
  such as `1.round() = 1`. Rebuild and copy the bundled
  `fhirpath.duckdb_extension` after future `fn_round()` changes.
- **FHIRPath FP-11 SKEPTIC math functions (2026-05-24):**
  **FIXED:** Native C++ §5.7 math dispatch must validate exact arity for
  `abs`, `ceiling`, `exp`, `floor`, `ln`, `log`, `power`, `round`, `sqrt`, and
  `truncate` before evaluation. Concrete non-numeric or wrong-Quantity inputs
  should throw `FHIRPathSpecError` so result UDFs return empty/NULL and
  `fhirpath_is_valid()` is false. Optional `round()` precision is validated
  before empty-input propagation to prevent sparse validation from hiding
  invalid precision arguments. `log(base)` uses the outer invocation focus for
  dynamic arguments like `p.log(base)`, and integer `power()` preserves Integer
  output. Rebuild and copy `fhirpath.duckdb_extension` after native math edits.
- **FHIRPath FP-10 EXPLORER Unicode case mapping (2026-05-24):**
  **FIXED:** Native C++ `upper()`/`lower()` local UTF-8 case tables now include
  dotted/dotless Turkish I and accented Greek vowel pairs. Regression coverage
  lives in `extensions/fhirpath/test/sql/fhirpath.test` and
  `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`;
  rebuild and copy `fhirpath.duckdb_extension` after future `fn_upper` or
  `fn_lower` changes.
- **FHIRPath FP-10 HISTORIAN string-transform rerun (2026-05-24):**
  **FIXED:** Native §5.6.6-§5.6.12 regex validation must compile regex
  literals before input-empty short-circuiting so malformed syntax such as
  `s.matches('[invalid')` yields public empty/NULL results and
  `fhirpath_is_valid=false`. Native `upper()`/`lower()` must keep UTF-8 case
  mapping broad enough for common Latin Extended-A pairs, including `č/Č`,
  `ž/Ž`, and `š/Š`, not only ASCII/Latin-1 and early Ext-A ranges. Preserve
  native SQL coverage for malformed regex syntax, Latin Extended-A case
  conversion, and singleton empty-string `replace()` parity; rebuild and copy
  `fhirpath.duckdb_extension` after future native transform changes.
- **FHIRPath FP-10 SKEPTIC string-transform rerun (2026-05-24):**
  **FIXED:** Native §5.6.6-§5.6.12 transform dispatch enforces exact
  signatures for `upper()`, `lower()`, `replace(pattern, substitution)`,
  `matches(regex)`, `replaceMatches(regex, substitution)`, `length()`, and
  `toChars()` before sparse inputs can hide malformed calls. Dynamic transform
  arguments in sourced calls, such as `s.replace(pattern, sub)` and
  `s.matches(regex)`, evaluate against the outer invocation focus rather than
  the source string. Regex validation rejects invalid or dangerous literal
  patterns, including patterns over 1000 characters, before returning empty for
  missing input. Rebuild and copy `fhirpath.duckdb_extension` after future
  native transform changes.
- **FHIRPath FP-09 HISTORIAN string-search argument focus
  (2026-05-24):** **FIXED:** Native C++ FP-09 functions with sourced calls
  must evaluate ordinary value arguments against the outer focus, not the source
  string collection. Dynamic resource-backed calls such as `s.indexOf(term)`,
  `s.substring(start, length)`, `s.startsWith(prefix)`, `s.endsWith(suffix)`,
  and `s.contains(term)` must match the forced Python fallback. Use the
  `outer_input` focus for these argument expressions, while preserving current
  input focus for no-source calls such as `substring($this.length() - 3)` in
  scoped predicates. Rebuild and copy `fhirpath.duckdb_extension` after native
  evaluator changes.
- **FHIRPath FP-09 SKEPTIC string-search validation (2026-05-24):**
  **FIXED:** Native §5.6 string-search dispatch must enforce exact arity before
  reading `node.children[0]`, and helper functions must validate concrete
  argument types before empty-input short-circuiting can mask malformed calls.
  Guard missing/extra arguments for `indexOf`, `substring`, `startsWith`,
  `endsWith`, and string-function `contains`; reject non-String search terms
  and non-Integer `substring` bounds with `FHIRPathSpecError`. Public UDFs
  still convert these semantic errors to empty/NULL row resilience, but
  `fhirpath_is_valid()` must be false for malformed constant/argument cases.
  Rebuild and copy `fhirpath.duckdb_extension` after touching these paths.
- **FHIRPath FP-08 HISTORIAN resource-backed Quantity conversion
  (2026-05-24):** **FIXED:** Native FP-08 conversion functions must
  materialize Quantity-like JSON values before applying §5.5.7/§5.5.8
  conversion and stringification. Guard `value.toQuantity()`,
  `value.convertsToQuantity()`, `value.toQuantity('g')`, `value.toString()`,
  `value.convertsToString()`, and invalid shape rejection for
  `{"value":"abc","unit":"mg"}`. Native `fhirpath_json` Quantity
  serialization must emit valid JSON string escapes for units and avoid binary
  double artifacts for ordinary fractional conversions such as `0.005`.
  Rebuild and copy `fhirpath.duckdb_extension` after touching these paths.
- **FHIRPath Section 5.5 Quantity/String/Time conversion (FP-08 SKEPTIC rerun,
  2026-05-24):** **FIXED:** Native evaluator dispatch enforces exact
  FP-08 signatures. Guard `toString()` and `toTime()` against any
  arguments, `convertsToString()` and `convertsToTime()` against arguments, and
  `toQuantity([unit])` / `convertsToQuantity([unit])` against more than one
  argument, non-String unit arguments, and multi-item unit arguments. Invalid
  cases such as `s.toString(1)`, `time_min.toTime(1)`,
  `1.toQuantity('1','g')`, `1.toQuantity(1)`, and
  `1.convertsToQuantity(('1'|'g'))` must return public empty/NULL row
  resilience with `fhirpath_is_valid=false`. Rebuild and copy the bundled
  extension after touching native evaluator dispatch, and keep the FP-08
  sqllogictest assertions aligned with Python fallback parity coverage.
- **FHIRPath Section 5.5 Date/DateTime/Decimal conversion (FP-07 SKEPTIC rerun, 2026-05-24):**
  **FIXED:** Native C++ FP-07 conversion dispatch rejects arguments for
  zero-argument `toDecimal()`, `toDate()`, `toDateTime()`,
  `convertsToDecimal()`, `convertsToDate()`, and `convertsToDateTime()`
  instead of ignoring them. Native `toDecimal()` only parses String values
  through the decimal regex; unsupported temporal values such as
  `@2015.toDecimal()` return empty. Keep native sqllogictest and
  forced Python fallback parity coverage aligned, and rebuild/copy the bundled
  extension after source changes.
- **FHIRPath Section 5.5 HISTORIAN rerun (FP-06, 2026-05-24):**
  **FIXED:** Native evaluator dispatch now enforces exact signatures for
  `iif`, `toBoolean`, and `toInteger`; malformed calls such as `iif(true)`,
  `iif(true, 'yes', 'no', 'extra')`, `true.toBoolean(1)`, and
  `'1'.toInteger(2)` are invalid. `iif` criteria that evaluate to multiple
  items now signal a singleton Boolean error while retaining lazy evaluation
  of the unselected result branch. Keep C++ sqllogictest and Python
  native-vs-forced-fallback parity coverage aligned after future conversion
  dispatch changes, and rebuild/copy the bundled extension after touching
  native evaluator code.
- **FHIRPath Section 5.5 conversion arity (FP-06 SKEPTIC rerun,
  2026-05-24):** **FIXED:** Native `convertsToBoolean()` and
  `convertsToInteger()` reject arguments. Invalid calls such as
  `'true'.convertsToBoolean(2)`, `'1'.convertsToInteger(2)`,
  `convertsToBoolean(strTrue)`, and `convertsToInteger(strInt)` now produce
  public empty/NULL row resilience with `fhirpath_is_valid=false`. The
  signatures in FHIRPath §5.5.2/§5.5.3 are zero-argument invocation functions;
  preserve exact arity checks and rebuild/copy the bundled extension after
  native changes.
- **FHIRPath §5.3/§5.4 exact arity validation (FP-05 SKEPTIC,
  2026-05-24):** **FIXED:** Native C++ must reject malformed subsetting
  and combining calls that forced Python fallback rejects. Guard cases include
  `a.first(0)`, `a.last(0)`, `a.single(0)`, `a.tail(0)`, `a.skip()`,
  `a.take()`, `a.skip(1, 2)`, `a.take(1, 2)`, `a.combine()`, `a.union()`,
  `a.intersect()`, `a.exclude()`, and extra-argument forms such as
  `a.union(b, ints)`. `skip()`/`take()` must validate exact arity and Integer
  argument type before empty-input short-circuiting so `fhirpath_is_valid()`
  rejects invalid `num` arguments on sparse validation input. Rebuild and copy
  the bundled `fhirpath.duckdb_extension` after native evaluator changes.
- **FHIRPath §5.2 malformed arity/type specifiers (FP-04 EXPLORER,
  2026-05-24):** **FIXED:** Native C++ must reject malformed
  `where(criteria)`, `select(projection)`, `repeat(projection)`, and
  `ofType(type)` invocations before evaluating data. Regression cases include
  `Patient.where()`, `item.where(true, false)`, `item.select(linkId, item)`,
  `item.repeat()`, and `Patient.ofType('Patient')`; native now returns
  `fhirpath_is_valid=false` and empty public results in parity with the forced
  Python fallback. Keep sqllogictest and Python parity coverage aligned, and
  rebuild/copy the bundled
  `fhirpath.duckdb_extension` after native changes.
- **FHIRPath §5.2 `ofType(type)` missing-argument validation (FP-04 HISTORIAN,
  2026-05-24):** **FIXED:** Native `evalOfType` throws a spec error unless the
  call has exactly one type-specifier child. This keeps `fhirpath_is_valid()`
  false for `entry.resource.ofType()` while public result UDFs return
  empty/NULL through the existing row-resilience path. Rebuild and copy the
  bundled extension after native evaluator changes.
- **FHIRPath §5.2 `ofType(type)` empty-input validation (FP-04 SKEPTIC,
  2026-05-24):** **FIXED:** Native `evalOfType` validates the type specifier
  before looping over input. `fhirpath_is_valid()` evaluates against a sparse
  Patient validation resource, so expressions like
  `entry.resource.ofType(NotAType).id` can reach `ofType` with empty input; this
  must still return invalid because FHIRPath §5.2.4 requires the type argument
  to resolve to a model type. Rebuild and copy the bundled extension after
  native evaluator changes.
- **FHIRPath §5.1 `exists(criteria)` full criteria validation (FP-03 EXPLORER, 2026-05-24):**
  **FIXED:** `exists(criteria)` is normative shorthand for
  `where(criteria).exists()`; native C++ must not return `true` immediately
  after the first matching item if later criteria evaluations would violate
  the single-Boolean criteria rule. Guard cases include
  `nested.exists(flags)` where an early item has `flags=[true]` and a later
  item has `flags=[false,true]`; public DuckDB wrappers return empty/NULL in
  parity with the forced Python fallback. Rebuild and copy the bundled
  `fhirpath.duckdb_extension` after touching `evalExists`.
- **FHIRPath §4.2-§4.5 operator/function QA rerun (FP-02 EXPLORER, 2026-05-24):**
  **FIXED:** Native unary `+`/`-` must apply after dot/function invocation and
  must reject multi-item operands. Per §6.8, `-7.combine(3)` is
  `-(7.combine(3))`, not `(-7).combine(3)`. Guard native evaluator changes
  with `-7.combine(3)`, `+7.combine(3)`, and `(-7).combine(3)` across
  sqllogictest and Python fallback parity. Rebuild and copy the bundled
  `fhirpath.duckdb_extension` after touching unary evaluator paths.
- **FHIRPath §4.2-§4.5 operator/function QA rerun (FP-02 SKEPTIC, 2026-05-24):**
  **FIXED:** Native parser precedence must match the normative §6.8 table:
  `is`/`as` bind tighter than union `|`. Expressions such as
  ``1 | 2 is Integer`` and ``1 | 'a' as String`` must stay valid and match
  the forced Python fallback. Native string helper functions that expect a
  singleton string, including `trim()`, must reject multi-item input through
  public row resilience rather than using `input[0]`. Rebuild and copy
  `fhirpath.duckdb_extension` after fixing native parser/evaluator paths.
- **FHIRPath §4.1 literal QA rerun (FP-01 EXPLORER, 2026-05-24):**
  **FIXED:** Native temporal literal evaluation must reject year `0000` and
  throw a spec error so `fhirpath_is_valid()` returns false while public row
  UDFs stay resilient. Native Quantity literal evaluation rejects empty quoted
  units such as ``1 ''``. Python fallback now mirrors native string-unescape
  behavior for quoted Quantity units such as ``10'\u006Dg'`` and avoids mixed
  temporal/non-temporal equality crashes during literal `|` de-duplication.
  Rebuild and copy the bundled `fhirpath.duckdb_extension` after touching
  native literal validation paths.
- **FHIRPath §4.1 literal QA rerun (FP-01 SKEPTIC, 2026-05-23):**
  **FIXED:** Native string/delimited-identifier unescape combines valid
  UTF-16 surrogate pairs such as ``'\uD834\uDD1E'`` into one Unicode scalar
  value instead of emitting invalid UTF-8 surrogate code units. The native
  parser accepts no-whitespace quoted UCUM Quantity literals such as
  ``10'mg'``; preserve that behavior and keep the Python fallback/validation
  path aligned. Rebuild and copy the bundled `fhirpath.duckdb_extension` after
  native lexer changes.
- **FHIRPath §4.1 literal QA rerun (FP-01 HISTORIAN, 2026-05-23):**
  **FIXED:** Native `fhirpath_timestamp` and `fhirpath_quantity` wrappers must
  validate FPValue type/shape before calling `toString()`. Timestamp accepts
  DateTime literals and resource-backed dateTime strings only; Quantity accepts
  Quantity literals and JSON Quantity objects only. Native Integer literals are
  32-bit at evaluation time, with parser support for `2147483648` only so
  unary minus can produce valid `-2147483648`. Rebuild, run
  `./build/release/test/unittest '*fhirpath*'`, and copy the rebuilt extension
  into `fhir4ds/fhirpath/duckdb/extensions/` after touching these paths.
- **SQL-on-FHIR View Runner key helpers**: **FIXED 2026-05-20 /
  SOF-VD-11 HISTORIAN**: Native C++ must recognize and dispatch
  `getResourceKey()` and `getReferenceKey([Type])`, matching Python fallback.
  `getResourceKey()` returns canonical `ResourceType/id` for root resources,
  and `getReferenceKey(Type)` returns a Reference only when the referenced type
  matches. Regression coverage lives in `extensions/fhirpath/test/sql/fhirpath.test`,
  `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`, and
  `fhir4ds/viewdef/tests/integration/test_duckdb.py`; rebuild and copy
  `fhirpath.duckdb_extension` after native changes.
- **Review-20 environment-variable explicit policy (2026-05-17):** Native C++ environment-variable evaluation must match the forced Python fallback. Only built-ins and known default variables such as ``%`vs-administrative-gender``` and ``%`ext-patient-birthTime``` are valid by default; do not fabricate arbitrary `%vs-*` or `%ext-*` URLs, and do not accept `%factory` or `%terminologies` unless the Python fallback gains the same behavior. Guard these cases in both native SQL tests and `test_environment_type_parity.py`; rebuild and copy the bundled extension after touching this path.
- **FHIRPath §10 TypeInfo public surface metadata**: **FIXED 2026-05-17 / FP-20 HISTORIAN**: Native `type()` must return a TypeInfo item for every input item, not only the first item, and its raw JSON string/list surface must match the Python fallback key order (`name`, then `namespace`). FHIR JSON metadata must preserve primitive subtypes (`uri`, `code`) and common complex datatypes (`Reference`, `Attachment`) for type reflection and `is`/`as` checks. Guard `Questionnaire.url.type()`, `Parameters.parameter.valueUri.type()`, `DocumentReference.content.attachment.contentType.type()`, `managingOrganization.is(Reference)`, and `(1|2).type()` against forced fallback parity. Rebuild and copy the bundled extension after touching this path.
- **FHIRPath §9 Environment Variables and §10/§11 Type Safety**: **FIXED 2026-05-17 / FP-20 SKEPTIC**: Native `%` lexing must support both backtick-delimited and legacy quoted string environment-variable names (`%`name`` and `%'name'`) with the same escape semantics. Undefined environment variables remain invalid for `fhirpath_is_valid()`, while public result UDFs return empty/NULL. Object-valued FHIR child fields with field metadata should participate in `BackboneElement` subtype checks, matching existing `type()` behavior; guard `contact.is(BackboneElement)` and `contact.as(BackboneElement).name.family` against forced Python fallback parity. Rebuild and copy the bundled extension after lexer/type changes.
- **FHIRPath JSON UDF string-vs-owned-JSON materialization**: **FIXED 2026-05-17 / FP-19 HISTORIAN**: Native `fhirpath_json` must serialize `FPValue::String` as JSON strings even when the text starts with `{` or `[`. Owned JSON objects/arrays converted after `yyjson_doc_free()` carry the internal `fhir_type="__json__"` marker and only those marked values serialize raw. Guard with string literals such as `'['`, `'[1]'`, and `'{"a":1}'`, and with `combine($this)` to ensure owned JSON objects still serialize as objects. Rebuild and copy `fhirpath.duckdb_extension` after changing this path.
- **FHIRPath §8 Delimited Identifier Escapes**: **FIXED 2026-05-17 / FP-19 SKEPTIC**: Native `Lexer::readDelimitedIdentifier()` must honor FHIRPath string escapes inside backtick identifiers, including escaped backticks, newline escapes, and Unicode escapes. The percent environment-variable path reuses the same reader. Guard with expressions such as `` `back\`tick` `` and `` `line\nbreak` `` and rebuild/copy `fhirpath.duckdb_extension` after lexer changes.
- **Malformed Temporal Lexemes vs No-Whitespace Arithmetic**: **FIXED 2026-05-17 / FP-19 SKEPTIC**: Native temporal lexing must reject malformed literal fragments such as `@2014-1`, `@2014-01-2`, and incomplete DateTime timezone `@2014-01-25T14+09` while preserving no-whitespace arithmetic such as `@2016-02-29T23:59+61 seconds`. Keep `fhirpath_is_valid()` parity with the forced Python fallback.
- **FHIRPath §6.7 No-Whitespace Temporal Arithmetic**: **FIXED 2026-05-17 / FP-18 EXPLORER**: Native `Lexer::readDateLiteral()` must only consume `+`/`-` as timezone text when a complete `(+|-)hh:mm` offset follows. Otherwise the character belongs to the arithmetic operator stream. Guard no-whitespace forms such as `@T23+119 minutes`, `@2016-02-29T23+119 minutes`, and `@2016-02-29T23:59+61 seconds` against the forced Python fallback. Rebuild and copy `fhirpath.duckdb_extension` after touching lexer code.
- **FHIRPath §6.7 Date/Time Arithmetic**: **FIXED 2026-05-17 / FP-18 SKEPTIC**: Native `fn_dateArith()` must validate units by operand type and by calendar-vs-definite duration semantics. Definite year/month UCUM quantities (`'a'`, `'mo'`) are execution errors, `Date` arithmetic does not accept hour/minute/second/millisecond units, and partial `Time` values must not gain precision when a more precise quantity is added/subtracted. Also keep native temporal arithmetic over FHIR JSON strings aligned with Python fallback by recognizing date/dateTime/time-shaped string values for arithmetic. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy `fhirpath.duckdb_extension` after changing this path.
- **FHIRPath §6.6 Math/Quantity Arithmetic Parity**: **FIXED 2026-05-17 / FP-18 SKEPTIC**: Native C++ and forced Python fallback public DuckDB arithmetic must agree on `div`, `mod`, 32-bit integer overflow, and compatible Quantity operations. Keep `div` integer-shaped when appropriate, preserve decimal `mod` source text so binary double artifacts do not leak, promote 32-bit integer overflow to Decimal at the public surface, canonicalize compatible Quantity `+`/`-`/`*` through base units, and return dimensionless Quantity `1 '1'` for compatible same-dimension Quantity `/` rather than a bare Decimal. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py`; rebuild and copy `fhirpath.duckdb_extension` after native arithmetic changes.
- **FHIRPath §6.5 Boolean Operand Singleton Errors**: **FIXED 2026-05-17 / FP-17 SKEPTIC**: Native `collectionIsBool()` must throw `FHIRPathSpecError` when asked to convert a multi-item collection, not return `false` as though the operand were empty/unknown. Otherwise `arr or true`, `arr and false`, and `arr implies true` leak concrete results instead of public UDF empty/NULL resilience. Preserve the intentional `false implies <expr>` short-circuit. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py`; rebuild and copy `fhirpath.duckdb_extension` after touching this path.
- **FHIRPath §6.4 Membership Singleton Errors**: **FIXED 2026-05-17 / FP-16 EXPLORER**: Native `evalBinaryOp()` must throw `FHIRPathSpecError` when `in` has a multi-item left operand or `contains` has a multi-item right operand. Public UDF materialization catches `FHIRPathSpecError` and returns empty/NULL by design, so public DuckDB parity alone will not prove strict compliance. Keep direct/core regression coverage and rebuild/copy `fhirpath.duckdb_extension` after touching this path.
- **FHIR Quantity Path Equality in Collection Operators**: **FIXED 2026-05-17 / FP-16 HISTORIAN**: `fpValuesEqual()` is the native helper behind `|`, `union()`, `intersect()`, `exclude()`, `in`, `contains`, `distinct()`, and related set-style functions. It must materialize Quantity-like JSON values before raw `yyjson_equals()` checks, or FHIR Quantity paths that are equal under ordinary `=` (`1 cm` vs `10 mm`) will still fail membership/de-duplication. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py`; rebuild and copy `fhirpath.duckdb_extension` after native helper changes.
- **FP-15 EXPLORER Type Operator Sweep**: **VERIFIED CLEAN 2026-05-17**: Fresh probes over §6.3 `is`/`as` operator and function forms confirmed native C++ parity with the forced Python fallback for resource and complex supertypes, primitive exact `as()` behavior, backtick-qualified type specifiers, invalid namespaces/types, wrong arity, empty input, and multi-item singleton resilience. Guard with `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`, `fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py`, and the native SQL `fhirpath.test` suite.
- **Qualified Type Specifier Namespace Validation**: **FIXED 2026-05-17 / FP-15 HISTORIAN**: Native C++ and Python fallback must reject FHIR-qualified System primitive aliases such as `FHIR.Boolean` and `FHIR.Integer` as unresolved type specifiers. Do not reject `System.Patient`; the official R4 conformance suite expects it to resolve as a non-matching type so `Patient.is(System.Patient).not()` is true. Native `fn_isType()` must validate type specifiers before empty-input short-circuiting so `fhirpath_is_valid()` catches wrong namespaces even when the validation resource lacks the left-side field. Preserve unqualified choice-type suffix matching (`value.ofType(Integer)`) through `fhir_type` metadata.
- **Type Specifier Validation and `as` Supertype Semantics**: **FIXED 2026-05-17 / FP-15 SKEPTIC**: Native C++ `is`/`as` must reject unknown or missing type specifiers and `is()`/`as()` wrong arity instead of returning false/empty with `fhirpath_is_valid=true`. `is` and `as` throw singleton errors internally for multi-item input; public UDF wrappers convert those row-level errors to empty/NULL. `as` accepts FHIR resource/complex supertypes such as `Patient as DomainResource` and `name.first() as Element`, but primitive FHIR casts remain exact for R4 conformance (`gender.as(string)` empty, `gender.as(code)` succeeds). Keep native and forced Python fallback parity coverage in `test_type_parity.py`; rebuild and copy the bundled extension after touching this path.
- **Quantity Equality**: `=` incorrectly treats equivalent quantities as equal (converts units instead of strict match).
- **String Concatenation (`&`)**: Incorrectly accepts multi-item collections, concatenating their first elements instead of throwing an error.
- **Nested Collections**: Navigation into nested JSON arrays (e.g., `[[1, 2]]`) does not flatten them into the FHIRPath collection; instead, inner arrays are serialized to JSON strings.
- **Substring boundaries**: Negative start indexes wrap or default to 0 instead of returning empty as required by spec.
- **Singleton Enforcement (Systemic)**: Binary math operators, comparison operators, and most string/math functions silently use the first element of multi-item collections instead of throwing an error or returning empty per the FHIRPath specification.
- **Polymorphic Metadata**: Accessing choice types directly by their full name (e.g., `valueQuantity`) fails to populate `fhir_type` metadata, causing `ofType()` filters to fail.
- **Date Validation**: `fhirpath_date` allows invalid components (e.g., 99 for month). **FIXED v0.0.4**: Added ISO-8601 month/day range validation with proper days-in-month logic.
- **Precision Loss**: `fhirpath_number` uses 64-bit DOUBLE, losing specification-mandated 24-digit precision. **INTENDED**: DOUBLE return type is a platform limitation. Users needing arbitrary precision should use `fhirpath_text` or `fhirpath_json`. Not fixable without changing the return type.
- **JSON Error Swallowing**: Suppresses malformed JSON strings, returning empty arrays instead. **INTENDED**: Per architectural mandate for population analytics resilience (GLOBAL_KNOWLEDGE §7). Single-row failures must not crash entire queries.
- **Singleton Coercion**: `fhirpath_number` silently resolves multiple-item arrays to the first item. **FIXED v0.0.4**: Multi-item collections now return NULL per FHIRPath singleton enforcement rules.
- **Parser Escape Bugs**: Syntax errors occur on correctly escaped single quotes (`\\'`). **UNCONFIRMED**: Lexer code handles `\'` correctly. Unable to reproduce with FHIRPath expression `'O\'Connor'` directly.
- **Literal Parity Drift**: C++ literal handling diverged from the Python fallback for `Time` serialization (`@T14:34`), invalid Date/DateTime/Time components, partial DateTime precision, Quantity JSON serialization, malformed Unicode escapes, and string escape handling. **FIXED 2026-05-14 / FP-01**: C++ and Python fallback now agree for public DuckDB literal UDF outputs; unknown string escapes follow FHIRPath §4.1.2 by ignoring the backslash, malformed Unicode escapes degrade consistently, partial DateTime literals preserve precision, invalid temporal components return empty, and Quantity JSON units omit literal quotes.
- **String Literal Double-Escape Reinterpretation**: Python fallback string unescaping must be a single left-to-right pass. **FIXED 2026-05-16 / FP-01 HISTORIAN**: `\\` now yields a literal backslash without the produced backslash being reinterpreted as an escape for the following character; regression coverage includes `'\p'` via `\\p` and `'\u005Cp'`.
- **Partial DateTime Timezone Validation**: C++ DateTime parsing must consume optional timezone offsets after hour, minute, or second precision and validate `(+|-)hh:mm` ranges. **FIXED 2026-05-16 / FP-01 HISTORIAN**: invalid partial offsets such as `@2014-01-25T14+99:99` return empty like Python fallback, while lexical shapes such as `@2014-01-25T14+09` fail `fhirpath_is_valid`.
- **Trailing Backslash String Literal Parity**: C++ string lexing must preserve FHIRPath section 4.1.2's ignored-backslash behavior when a backslash immediately precedes the closing delimiter with no later delimiter. **FIXED 2026-05-16 / FP-01 EXPLORER**: native C++ now matches Python fallback for `'abc\'` and returns `abc`; regression coverage lives in `test_literal_parity.py`.
- **Singleton Boolean Evaluation for `not()`**: Native C++ `not()` must apply FHIRPath §4.5 singleton Boolean evaluation, matching Boolean operators: a single non-Boolean node evaluates as true and `not()` returns false. **FIXED 2026-05-16 / FP-02 SKEPTIC**: C++ `gender.not()` now matches Python fallback; regression coverage lives in `test_operator_parity.py`.
- **Bundled Extension Freshness After Singleton Fixes**: Public native DuckDB behavior comes from `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`, not just `extensions/fhirpath/src`. **REFRESHED 2026-05-16 / FP-02 EXPLORER**: after singleton Boolean source fixes, rebuild with `cmake --build build/release --config Release -j 8` and copy the rebuilt extension into the Python package before validating `gender.not()` or Boolean operator parity.
- **Numeric Fast Path Through Repeating Objects**: `fhirpath_number` simple-path fast path must preserve singleton enforcement for paths such as `a.v` where `a` has multiple objects. **FIXED 2026-05-14 / QA-001**: The number fast path now resolves through flattened path traversal and only emits when exactly one terminal numeric value exists. Regression coverage: `fhir4ds/fhirpath/duckdb/tests/integration/test_number_fastpath_parity.py`.
- **Standalone `extension(url)` Dispatch**: The C++ parser must treat root-level `extension('url')` as `ExtensionCall`, not a generic `FunctionCall`. **FIXED 2026-05-14 / QA-002**: `extension('u').value` now matches Python fallback and `.extension.where(url = 'u').value`; regression coverage in `test_extension_parity.py`.
- **Existence Criteria Iteration Context**: `exists(criteria)` and `all(criteria)` must expose `$this` and `$index` for every input item, just like `where()` and `select()`. **FIXED 2026-05-16 / FP-03 SKEPTIC**: Native C++ now sets/restores `index_context_` for both criteria functions; regression coverage in `test_existence_parity.py`.
- **Boolean Aggregate Type Validation**: `allTrue()`, `anyTrue()`, `allFalse()`, and `anyFalse()` operate on Boolean collections. **FIXED 2026-05-16 / FP-03 SKEPTIC**: Native C++ now raises a spec error for non-Boolean items, which public UDFs convert to empty/NULL like the Python fallback; regression coverage in `test_existence_parity.py`.
- **Existence Equality Semantics**: `distinct()`, `isDistinct()`, `subsetOf()`, and `supersetOf()` must use the same FHIRPath `=` semantics as equality operators. **FIXED 2026-05-16 / FP-03 HISTORIAN**: Native C++ `fpValuesEqual()` now handles structural JSON equality independent of object key order and compatible-unit quantity equality; Python core existence functions now route through the equality helper. Rebuild and copy the bundled extension after touching this helper. Regression coverage in `test_existence_parity.py`.
- **Criteria Boolean Strictness**: `where(criteria)`, `exists(criteria)`, and `all(criteria)` must reject criteria results that are not a single Boolean. **FIXED 2026-05-16 / FP-03 EXPLORER**: Native C++ now uses strict criteria validation for filter-style criteria while leaving non-strict singleton truthiness helpers available for intentional callers such as `iif`; Python `where_macro` now routes criteria through `util.is_true()`. Public UDFs convert the spec error to empty/NULL outside strict mode.
- **Boolean Aggregate Full-Collection Validation**: `allTrue()`, `anyTrue()`, `allFalse()`, and `anyFalse()` must validate every item is Boolean before short-circuiting the truth calculation. **FIXED 2026-05-16 / FP-03 EXPLORER**: native C++ and Python core now materialize/validate Boolean values before computing the aggregate truth table; regression coverage includes mixed literal collections such as `true.combine('x')` and `false.combine('x')`.
- **Filtering/Projection Lambda Scope and `ofType()` Subtypes**: **FIXED 2026-05-16 / FP-04 SKEPTIC**: `where()`/`select()`/`repeat()` must bind `$index` only for the expression currently under evaluation and restore any outer value afterward; Python fallback leaked `$index` after `where()`/`select()` and did not bind it inside `repeat()`. `ofType(type)` must include non-primitive FHIR subclasses per FHIRPath §5.2.4; exact-only matching dropped resources for `ofType(Resource)` and `ofType(DomainResource)`. Preserve official R4 primitive behavior: `Patient.gender.ofType(string)` remains empty for FHIR `code`.
- **`repeat()` Projection De-Duplication**: **FIXED 2026-05-16 / FP-04 HISTORIAN**: `repeat(projection)` must de-duplicate newly produced projection results using FHIRPath `=` equality, including duplicates produced within one projection evaluation. Native C++ must not treat input items as already emitted and must not add numeric/temporal input seeds through shortcuts. Regression coverage in `test_filter_projection_parity.py` includes `'a'.repeat($this)`, bounded numeric projection, and duplicate child objects.
- **Subsetting Integer Argument Coercion**: **FIXED 2026-05-16 / FP-05 SKEPTIC**: Native C++ and Python fallback now reject non-Integer arguments for `[index]`, `skip(num)`, and `take(num)` instead of coercing strings, booleans, decimals, or JSON reals through `int()`/`toNumber()`. Public UDF wrappers convert those semantic errors to empty/NULL. Regression coverage lives in `test_collection_operator_parity.py`.
- **`intersect()` Equality Semantics**: **FIXED 2026-05-16 / FP-05 SKEPTIC**: Python core `intersect()` now uses FHIRPath `=` equality like native C++ `fpValuesEqual()`, `union()`, and `distinct()`. Compatible quantities such as `1 'cm'` and `10 'mm'` now intersect as one value in both backends.
- **FP-05 HISTORIAN Parity Sweep**: **VERIFIED 2026-05-16**: Native C++ and Python fallback agree for §5.3/§5.4 edge cases covering out-of-bounds and negative indexers, `single()` strict errors, `first()`/`last()`/`tail()`, `skip()`/`take()` boundary values, invalid Integer arguments, duplicate-preserving `exclude()`/`combine()`, equality-backed `union()`/`intersect()`, structurally equal objects with different member order, and compatible quantities.
- **JsonVal Numeric Equality in Set Helpers**: **FIXED 2026-05-16 / FP-05 EXPLORER**: Native C++ `fpValuesEqual()` must apply numeric equality before generic `yyjson_equals()` when both operands are JSON numeric values. Otherwise JSON integer `1` and JSON real `1.0` compare equal through direct `=` but diverge in `union()`, `intersect()`, and `exclude()`. Regression coverage lives in `test_collection_operator_parity.py`.
- **Direct Collection Negative Subsetting**: **FIXED 2026-05-16 / FP-05 EXPLORER**: `FHIRPathCollection.take()` and `FHIRPathCollection.skip()` guard negative counts before Python slicing. The exported `functions.filter.take/skip` helpers were already spec-compliant, but the collection methods are also public and must preserve §5.3 semantics. Regression coverage lives in `test_filter.py`.
- **Expression-Parameter Scope Restoration**: **FIXED 2026-05-16 / review-5 remediation**: Every expression-parameter function must restore transient scope after evaluating criteria/projection expressions. Python `all(criteria)` must save/restore `$index`, matching `where()`/`select()`/`repeat()`. Native C++ `where(criteria)` must save/restore `defined_variables_` as well as `chain_defined_vars_` and `index_context_`; `defineVariable()` inside criteria must not leak into subsequent chained expressions. Regression coverage lives in `test_existence_parity.py` and `test_filter_projection_parity.py`.
- **Conversion Type Tables and Singleton Input**: **FIXED 2026-05-16 / FP-06 SKEPTIC**: Native `toInteger()`/`convertsToInteger()` must not accept Decimal inputs, including `1.0`; FHIRPath §5.5.3 permits Integer, Boolean, and regex-integer Strings only. Guard string parsing with exact lexical validation before `std::stoll` because it skips leading whitespace. `iif()` belongs to §5.5 and must reject multi-item input before lazy branch evaluation, with public DuckDB UDFs converting the semantic error to empty/NULL outside strict mode. After source changes, rebuild and copy the bundled extension before validating public DuckDB behavior.
- **Source/Binary Drift Watch**: **FIXED 2026-05-16 / FP-06 HISTORIAN**: Public bundled native UDFs already rejected multi-item `iif()` input, but `extensions/fhirpath/src/fhirpath/evaluator.cpp::fn_iif` had drifted and would have evaluated branches after a rebuild. Keep the explicit `input.size() > 1` guard in source and the native SQL regression in `extensions/fhirpath/test/sql/fhirpath.test`.
- **Decimal Conversion Lexical Validation**: **FIXED 2026-05-16 / FP-07 SKEPTIC**: Native `toDecimal()`/`convertsToDecimal()` must validate String input against the FHIRPath §5.5.6 regex `(+|-)?\d+(\.\d+)?` before calling `std::stod`, because `std::stod` accepts non-spec forms such as exponent notation, leading whitespace, `1.`, and `.1`. Keep native C++ and forced Python fallback parity tests for these rejected shapes, and rebuild/copy the bundled extension after source changes.
- **Date String Timezone Suffix Truncation**: **FIXED 2026-05-16 / FP-07 HISTORIAN**: Native `toDate()` must not strip `Z` or timezone-offset suffixes from String input such as `2015-02-04+05:00` or `2015Z`. FHIRPath §5.5.4 String conversion uses Date format `YYYY-MM-DD`; forced Python fallback and `convertsToDate()` reject these strings. Regression coverage lives in `test_conversion_parity.py`; rebuild and copy the bundled extension after touching native conversion code.
- **Date/DateTime Conversion Type Guards**: **FIXED 2026-05-16 / FP-07 EXPLORER**: Native `toDate()`/`toDateTime()` must not coerce arbitrary non-string values with `toString()`. Integer `2015` is not a Date, DateTime, or String input and must return empty/NULL, matching forced Python fallback and `convertsToDate*()`. Regression coverage lives in `test_conversion_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after source changes.
- **Malformed DateTime String Truncation**: **FIXED 2026-05-16 / FP-07 EXPLORER**: Native `toDate()` must validate the full String input before extracting a date from a DateTime-like value. Strings such as `2015-02-04T99` and `2015-02-04Tbogus` are neither valid Dates nor valid DateTimes and must return empty/NULL rather than `2015-02-04`. Regression coverage lives in `test_conversion_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after source changes.
- **Quantity String Empty Quoted Unit**: **FIXED 2026-05-16 / FP-08 EXPLORER**: Native `toQuantity()` must reject String input `1 ''` and `convertsToQuantity()` must return false. FHIRPath §5.5.7 requires quoted units to match `[^']+`, so empty quoted units return empty/false and match forced Python fallback behavior. Regression coverage lives in `test_conversion_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after touching native quantity conversion code.
- **Quantity Conversion Unit and String Parsing**: **FIXED 2026-05-16 / FP-08 SKEPTIC**: `toQuantity()` and `convertsToQuantity()` must apply the §5.5.7 string grammar strictly and honor the optional `unit` argument. Native C++ rejects leading-whitespace strings, unterminated quoted units, and bare duration UCUM abbreviations such as `wk`; `convertsToQuantity(unit)` rejects incompatible target units instead of ignoring the argument. Python fallback uses a dedicated quantity conversion check instead of routing the optional target unit through the generic `create_converts_to_fn()` argument-as-input path. Rebuild and copy the bundled extension after touching native conversion code.
- **Time Conversion Precision Preservation**: **FIXED 2026-05-16 / FP-08 HISTORIAN**: `toTime()` and `Time.toString()` must preserve partial precision. `14:34` is minute precision and must serialize as `14:34`, not `14:34:00`; native C++ normalization and Python `FP_Time.__str__` both avoid precision promotion. Regression coverage includes literal `@T14:34.toString()` and String conversion `'14:34'.toTime().toString()` across native and forced Python fallback backends. Rebuild and copy the bundled extension after native changes.
- **Python `fhirpath_bool` Type Erasure**: **FIXED 2026-05-16 / FP-08 HISTORIAN**: The forced Python fallback bool convenience UDF must evaluate raw FHIRPath results before coercion. Do not call `fhirpath_scalar()` from `fhirpath_bool_udf()` because it stringifies numbers and string conversion results alike; `num` may convert to boolean, but `num.toString()` and JSON string `"1"` must return NULL in `fhirpath_bool`, matching native C++ string validation.
- **String Search Type Guards and Substring Boundary**: **FIXED 2026-05-16 / FP-09 SKEPTIC**: Native C++ search functions reject invalid argument/input types instead of coercing through `toString()` or `toNumber()`; examples include `s.indexOf(123)`, `s.endsWith(123)`, `s.contains(123)`, `s.substring('1')`, and `num.contains('2')`. Python fallback `substring()` treats `start == length` as empty per the normative example `'abcdefg'.substring(7, 1) // { }`. Regression coverage lives in `test_string_search_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after future native search-function changes.
- **String Transform Type Guards**: **FIXED 2026-05-16 / FP-10 SKEPTIC**: Native C++ transform functions in §5.6.6-§5.6.12 reject non-String inputs and non-String arguments instead of coercing through `toString()`. Fragile paths include `matches()`, `replace()`, `replaceMatches()`, and `toChars()`. Public UDFs convert these semantic errors to empty/NULL, matching forced Python fallback behavior. Direct helper `fhir4ds/fhirpath/duckdb/functions/string.py` also keeps `matches()` full-string/DOTALL, `replaceMatches('', sub)` unchanged, and exposes `toChars`.
- **Unicode Case Transform Mapping**: **FIXED 2026-05-16 / FP-10 HISTORIAN**: Native C++ `upper()` must preserve Unicode case semantics for multi-code-point and special-case mappings. Regression coverage includes German sharp s (`Straße` -> `STRASSE`) and Greek final sigma (`Σςσ` -> `ΣΣΣ`). Keep native and forced Python fallback parity coverage when changing the UTF-8 case mapping table.
- **Unicode Regex Dot Semantics**: **FIXED 2026-05-16 / FP-10 EXPLORER**: Native C++ `matches()` and `replaceMatches()` must treat unescaped regex `.` as one Unicode code point in DOTALL mode, not one UTF-8 byte. The evaluator normalizes standalone dots to a UTF-8 code-point regex atom before calling `std::regex`; regression coverage includes `é.matches('.')`, `😀.matches('.')`, `é.replaceMatches('.', 'x')`, and `😀.replaceMatches('.', 'x')`. Rebuild and copy the bundled extension after changing this path.
- **Regex ReDoS Guard**: **FIXED 2026-05-17 / review-10 remediation**: Native regex paths must validate the original user pattern before UTF-8 dot normalization and before `std::regex` compilation. Reject overlong patterns and nested quantified groups/quantified alternations such as `(a+)+` and `(a|aa)+`. Do not run the ReDoS detector on the normalized UTF-8 dot expansion; valid patterns like `A.*c` must still pass. Direct Python helpers in `fhir4ds/fhirpath/duckdb/functions/string.py` use the same guard.
- **Native Type Reflection Metadata Debt**: **DEFERRED 2026-05-17 / review-10**: `fhirTypeIsA()`, `fhirFieldType()`, and complex field-name type heuristics still encode FHIR model knowledge inside `evaluator.cpp`. A safe fix requires a generated C++ registry from `fhir4ds/fhirpath/models/r4/type2Parent.json`, `fhir_type_hierarchy.json`, and path/type metadata, plus parity coverage. Do not extend the hand-maintained maps for new model behavior; generate or load metadata instead.
- **Math Function Argument Guards**: **FIXED 2026-05-17 / FP-11 SKEPTIC**: Native C++ math functions validate evaluated arguments, not just input collections. `log(base)`, `power(exponent)`, and `round(precision)` reject multi-item arguments; `round()` precision is a singleton Integer with value >= 0; and only `abs()` accepts Quantity input in FHIRPath §5.7. Public UDFs convert these semantic errors to empty/NULL and remain in parity with the forced Python fallback. Regression coverage lives in `test_math_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after future native math changes.
- **Math Round Decimal Formatting**: **FIXED 2026-05-17 / FP-11 HISTORIAN**: Native C++ `round(precision)` preserves the requested decimal precision in `source_text` before returning a Decimal. Otherwise public string/JSON UDF surfaces can expose binary double artifacts such as `3.14159.round(3)` returning `3.1419999999999999` instead of the spec example `3.142`. Regression coverage lives in `test_math_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after future native math changes.
- **Math Decimal Literal Formatting**: **FIXED 2026-05-17 / FP-11 EXPLORER**: Native C++ math functions that transform Decimal literals must preserve or intentionally reset `source_text` for public text/json surfaces. `abs()` on `3.14159` and `-3.14159` previously leaked binary double text (`3.1415899999999999`) while the Python fallback returned `3.14159`. Regression coverage lives in `test_math_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after future native math changes.
- **Explicit `round(0)` Decimal Result**: **FIXED 2026-05-17 / FP-11 EXPLORER**: Treat an explicit precision argument as precision-bearing even when it is zero. Native C++ and direct Python helper `round_fn(value, 0)` should return Decimal-form output (`3.0`) while no-argument `round()` keeps existing whole-number behavior. Regression coverage lives in `test_math_parity.py`, `test_math.py`, and `extensions/fhirpath/test/sql/fhirpath.test`.
- **Tree Navigation Null Preservation**: **FIXED 2026-05-16 / FP-12 SKEPTIC**: Native C++ `children()` and `descendants()` preserve JSON null children. FHIRPath field navigation skips null, but §5.8 tree navigation exposes child nodes and the project invariant explicitly requires null children to remain visible. Native UDF materialization uses an owned `FPValue::Null` sentinel after `yyjson_doc_free()`, and `count()` counts null child nodes produced by tree navigation. Keep native and forced Python fallback parity coverage for `children().count()`, `descendants().count()`, and `fhirpath_json(..., 'children()')` on resources with null-valued fields.
- **Trace Projection Diagnostics**: **FIXED 2026-05-16 / FP-12 SKEPTIC**: Python core `trace(name, projection)` logs the evaluated projection while returning the original input unchanged. Do not drop the second trace argument in `doInvoke()`; regression coverage asserts `traceFn` receives projected values such as `name.trace('names', given) -> ['Ann', 'Bob']`.
- **Current-Time Determinism**: **FIXED 2026-05-16 / FP-12 EXPLORER**: Native C++ `now()`, `today()`, and `timeOfDay()` must share one cached timestamp per `Evaluator::evaluate()` call. Calling `time(nullptr)` independently lets long expressions cross a second boundary and makes `now() = now()` false, violating FHIRPath §5.9.2. Regression coverage lives in `test_tree_utility_parity.py`; rebuild and copy the bundled extension after future native current-time changes.
- **Multi-Item Equivalence Semantics**: **FIXED 2026-05-17 / FP-13 SKEPTIC**: `~` over multi-item collections must be order-insensitive but still compare each item with full FHIRPath equivalence semantics. Do not compare lowercased `toString()` values, sorted raw Python lists, or `Counter(str(item))`; these lose string whitespace normalization, quantity unit conversion, and calendar/definite duration equivalence. Regression cases live in `test_equality_parity.py`: `(1 'mg' | 2 'mg') ~ (0.002 'g' | 0.001 'g')`, `stringsA ~ stringsB` with whitespace/case differences, and `(1 year | 1 second) ~ (1 'a' | 1 's')`.
- **Calendar Duration Equality Result Shape**: **FIXED 2026-05-17 / FP-13 SKEPTIC**: Python fallback `=` for calendar vs definite year/month quantities now branches by strictness. Strict Python core preserves official R4 conformance (`'1 \'a\''.toQuantity() = 1 year` returns empty), while non-strict DuckDB fallback returns Boolean `false` to match native public UDF behavior for `1 year = 1 'a'`; `!=` returns the converse. Keep native and forced Python fallback parity coverage for public UDFs and strict-mode smoke coverage for R4 conformance.
- **Multi-Item Date/Time Equality and Complex Equivalence**: **FIXED 2026-05-17 / FP-13 HISTORIAN**: Multi-item `=`/`!=` now compares every ordered pair through full singleton equality semantics, including DateTime timezone normalization and seconds/milliseconds decimal precision. Native complex `~`/`!~` recursively compares JSON object/array child properties with equivalence semantics instead of raw JSON equality, so child strings normalize case/whitespace and multi-item complex collections remain order-insensitive. Regression coverage lives in `test_equality_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after future native equality changes.
- **Date vs DateTime Equality/Equivalence**: **FIXED 2026-05-17 / FP-13 EXPLORER**: Native C++ must not treat `Date` and partial `DateTime` literals as equal merely because populated date components match. FHIRPath §6.1 single-item equality/equivalence requires operands to be the same type or implicitly convertible; `@2012 = @2012T` is empty for `=`/`!=`, and `false`/`true` for `~`/`!~`, matching the Python fallback. The native evaluator now explicitly rejects `Date`/`DateTime` pairs in singleton, multi-item, and helper equality/equivalence paths. Regression coverage lives in `test_equality_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after future native equality changes.
- **Quantity Path Comparison Materialization**: **FIXED 2026-05-17 / FP-14 HISTORIAN**: Native comparison pre-processing must convert FHIR JSON Quantity path results into `FPValue::Quantity` even when both operands are JSON values. The old conversion gate only fired when one side was already a literal Quantity, so `value > component.value` returned empty while `4 'm' > 4 'cm'` worked. `isQuantityLike()` now recognizes `fhir_type` metadata such as `Quantity`, Quantity subtypes, and structural `{value, code|unit}` objects before comparison. Regression coverage lives in `test_comparison_parity.py`; rebuild and copy the bundled extension after future native comparison changes.

### NOT A BUG Registry

- **FHIRPath Section 7/8 HISTORIAN rerun (FP-19, 2026-05-24):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback behavior for a fresh 31-case aggregate/lexical probe and 7 direct
  core checks. Keep native and Python parity aligned for aggregate init outer
  focus, empty-source init, accumulator/index restoration, comment stripping
  only outside strings/delimited identifiers, strict FHIRPath whitespace,
  keyword identifier exceptions (`as`, `contains`, `in`, `is`), reserved
  `div`/`mod`/duration keyword delimiters, case-sensitive keywords, numeric
  literal grammar rejection, and no-whitespace calendar quantities. Rebuild and
  copy the bundled extension after future lexer, parser, or aggregate changes.
- **FHIRPath Section 5.5.4-5.5.6 EXPLORER rerun (FP-07, 2026-05-24):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback behavior for a fresh 46-case pathological conversion probe covering
  invalid calendar/timezone ranges, partial Date/DateTime precision, strict
  Decimal string grammar, empty and resource-backed multi-item row resilience,
  invalid arity, lazy `iif()` branches, `select()` chains, and explicit
  root-filter chains. Keep native sqllogictest and Python parity coverage
  aligned when changing conversion dispatch or temporal parsing.
- **FHIRPath Section 5.5.4-5.5.6 HISTORIAN rerun (FP-07, 2026-05-24):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback behavior for a fresh 56-case probe covering `toDate()`,
  `convertsToDate()`, `toDateTime()`, `convertsToDateTime()`, `toDecimal()`,
  and `convertsToDecimal()`. Keep native sqllogictest and Python parity
  coverage aligned for exact zero-argument signatures, strict decimal lexical
  validation, date/calendar ranges, DateTime timezone validation, partial
  precision preservation, empty propagation, and multi-item singleton
  resilience after future evaluator changes.
- **FHIRPath Section 5.3/5.4 HISTORIAN rerun (FP-05, 2026-05-24):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback behavior for a fresh 53-case section-by-section probe covering
  `[index]`, `single()`, `first()`, `last()`, `tail()`, `skip(num)`,
  `take(num)`, `intersect(other)`, `exclude(other)`, `union(other)`/`|`, and
  `combine(other)`. Keep native sqllogictest and Python parity coverage
  aligned for exact arity, strict Integer arguments, duplicate semantics, and
  FHIRPath equality-backed set helpers after future native evaluator changes.
- **FHIRPath Section 5.1 HISTORIAN rerun (FP-03, 2026-05-24):**
  **VERIFIED CLEAN:** The bundled native extension matched the forced Python
  fallback for a 52-case section-by-section probe over every mandatory
  existence function: `empty()`, `exists([criteria])`, `all(criteria)`,
  `allTrue()`, `anyTrue()`, `allFalse()`, `anyFalse()`, `subsetOf()`,
  `supersetOf()`, `count()`, `distinct()`, and `isDistinct()`. Preserve
  parity for vacuous empty defaults, criteria `$index` binding/restoration,
  invalid criteria row resilience, full Boolean aggregate validation, and
  `fpValuesEqual()`-backed structural/numeric/Quantity equality.
- **FHIRPath Section 5.1 SKEPTIC rerun (FP-03, 2026-05-24):**
  **VERIFIED CLEAN:** The bundled native extension matched the forced Python
  fallback for 35 fresh existence-function cases covering criteria `$index`,
  no scope leakage, non-Boolean criteria row resilience, Boolean aggregate
  type validation, vacuous empty defaults, set-function equality semantics,
  compatible quantities, FHIR Quantity paths, and structural JSON equality.
  Preserve `test_existence_parity.py` and rebuild/copy the bundled extension
  after native existence or `fpValuesEqual()` changes.
- **FHIRPath §4.2-§4.5 HISTORIAN rerun (FP-02, 2026-05-24):**
  **VERIFIED CLEAN:** Public native C++ DuckDB behavior matches the forced
  Python fallback for operator syntax, function invocation syntax, null/empty
  propagation, and singleton row-resilience across 24 fresh HISTORIAN cases.
  Preserve subprocess-isolated native/fallback probes and explicit workspace
  imports when checking this chunk; otherwise installed-package drift can look
  like extension behavior drift.
- **Nested JSON arrays**: Divergence on invalid FHIR-shaped data such as `{"nested":[[{"v":1}],[{"v":2}]]}` is not release-blocking. FHIR resources do not model arrays of arrays directly; public behavior is only guaranteed for valid FHIR JSON shapes and documented resilience behavior on malformed/invalid rows.
- **FP-06 EXPLORER no-new-bug verification (2026-05-16)**: Public DuckDB UDFs returning empty/NULL for multi-item conversion errors is intentional row-level resilience outside strict mode. Strict Python core evaluation remains the conformance surface for semantic errors such as non-Boolean `iif` criteria, while non-strict public wrapper parity must be checked against both native C++ and forced Python fallback.
- **FP-12 HISTORIAN current-time backend policy (2026-05-17)**: Native DuckDB and forced Python fallback may use different timestamp sources/precision for `now()`, `today()`, and `timeOfDay()` (for example UTC native vs local Python around midnight). This is not a spec bug as long as each function returns the required type/shape and remains deterministic within a single expression.
