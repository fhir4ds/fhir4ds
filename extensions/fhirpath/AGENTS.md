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

- **FHIRPath FP-20 HISTORIAN iteration 1 §9 Environment Variables + §10
  Types/Reflection + §11 Type Safety + §12 Formal Specifications
  (2026-06-30):** **1 NATIVE DEFECT RESOLVED, 1 INTENDED.** Fresh
  HISTORIAN systematic spec-walkthrough with 236 cases across 4 probe
  files walked every normative rule from FHIRPath v2.0.0 §9-§12 plus
  FHIR R4 datatype-hierarchy knowledge at the public DuckDB UDF
  boundary comparing bundled native C++ extension vs forced Python
  fallback through all 5 UDF wrappers + `fhirpath_is_valid`.

  **(QA-001 MEDIUM §11 / FHIR R4 RESOLVED):** Native C++
  `Evaluator::fn_isType` at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:8793-9012` returned
  `false` for `<FHIR primitive> is Element`. Per FHIR R4
  (https://hl7.org/fhir/R4/datatypes.html) every primitive datatype
  (boolean/integer/decimal/string/date/dateTime/time/code/id/etc.)
  inherits from `Element`; per FHIRPath §6.3.1 `is` returns true if
  the type of the left operand is the type specified, or a subclass
  thereof. 11 distinct reproducer cases confirmed:
  `valueInteger/valueDecimal/valueString/valueBoolean/valueDate/
  valueDateTime/valueTime/active/birthDate/gender/id is Element` all
  returned cpp=False vs py=True. `valueQuantity is Element` correctly
  True in both (Quantity handled via `fhirTypeIsA` path); `Patient is
  Element` correctly False in both (resources inherit from
  DomainResource → Resource, NOT from Element per FHIR R4). Root
  cause: C++ FHIR primitive branches at evaluator.cpp:8904+
  (`target == "boolean"|"integer"|"decimal"|"string"|"date"|
  "dateTime"|"time"`) returned strict equality without consulting
  primitive → Element hierarchy. `fhirTypeIsA()` table at lines
  874-1067 correctly models complex-type parents but does not include
  primitive → Element mappings.

  Surgical fix at evaluator.cpp inside `if (is_fhir)` primitive block
  (around line 8921): added fallthrough check
  `if (!exact && target == "Element" && (t == Boolean|Integer|Decimal|
  String|Date|DateTime|Time)) return true;`. Two scope gates: (a)
  `!exact` preserves `as Element` parity with Python fallback (both
  currently return empty for `as Element` on a primitive — Python has
  a separate latent `as Element` bug flagged as follow-up debt, not
  in FP-20 scope); (b) effective-type check ensures resource objects
  (effective type JsonVal) do NOT match — `Patient is Element`
  correctly remains false because resources inherit from
  DomainResource → Resource, not Element.

  2 new regression tests in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`:
  `test_fhir_primitive_is_element_root_subtype_fp20_historian` (17
  cases covering primitives, complex types, resources) and
  `test_as_element_on_primitive_preserves_empty_parity_fp20_historian`
  (2 cases asserting `as Element` continues to return NULL in both
  backends — parity preservation sentinel). Native C++ extension
  rebuilt (md5sum `8d418a00bc9f78f8bb860ef35a621b0f`) and copied to
  both package and user install paths. Post-fix: HISTORIAN probe4
  §11.4 0 diffs (was 1 diff / 7 cases); targeted `is Element` parity
  matrix 11/11 clean (was 0/11); FHIRPath duckdb integration 437/437
  pass (was 435, +2 new tests); full conformance 2822/2822 unchanged
  (ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM
  47/47).

  **(QA-002 LOW §9 INTENDED):** C++ lexer at
  `extensions/fhirpath/src/fhirpath/lexer.cpp:368` reads
  `%vs-administrative-gender` (simple-identifier form with hyphens)
  as a single env var token; Python parser tokenizes as `%vs` +
  arithmetic. 6 reproducer cases. Backtick and string forms work in
  both backends. Official R4 conformance tests use the backtick form.
  Carry-over from prior FP-20 SKEPTIC NOT A BUG Registry —
  HISTORIAN re-confirmed via direct parser AST inspection showing
  Python parses `%vs-administrative-gender` as
  `((%vs) - administrative) - gender` AdditiveExpression tree.
  Aligning either direction has costs exceeding benefit (C++ change
  would be breaking; Python change requires touching external
  fhirpathpy or our ANTLR grammar — risky and outside FP-20 scope).

  **Architecture Drift Log (FP-20 HISTORIAN additions):**
  - (LOW, follow-up debt) Python fallback `as Element` on a FHIR
    primitive returns empty
    (`fhir4ds/fhirpath/engine/invocations/types.py:as_fn`). Per FHIR
    R4, primitives ARE Elements, so `valueInteger as Element` should
    return the integer value (not empty). The C++ side now also
    returns empty for `as Element` (preserved via the `!exact` gate)
    to maintain parity. Fixing it requires coordinating with the
    in-repo engine's `TypeInfo.is_()` path AND removing the `!exact`
    gate in the C++ fix. Deferred to a future §11 / TypeInfo-focused
    chunk. Does not affect any production code path (`as Element` is
    not used in fhir4ds, CQL translator, ViewDefinition, or DQM).

  **NOT A BUG Registry (FP-20 HISTORIAN additions):**
  - Hyphenated env var simple-identifier form (`%vs-administrative-
    gender`): C++ lexer permissively accepts hyphens; Python parser
    correctly tokenizes as `%var` + arithmetic. Re-confirmation of
    the FP-20 SKEPTIC §8.6 lexer-permissiveness discovery. Backtick
    form `` %`name` `` and string form `%'name'` are the spec-
    compliant ways to reference env vars with hyphens; both work
    correctly in both backends.

  Probes: `/mnt/d/fhir4ds/.temp/qa/fp20_historian_2026_06_30/probe.py`
  (125 cases / 19 spec-rule groups), `probe2.py` (26 cases / bug-class
  confirmation), `probe3.py` (12 cases parser-AST diagnostic),
  `probe4.py` (73 cases / 9 deeper §10-§12 edge groups).

- **FHIRPath FP-20 SKEPTIC iteration 1 §9 Environment Variables + §10
  Types/Reflection + §11 Type Safety + §12 Formal Specifications
  (2026-06-30):** **1 NATIVE DEFECT RESOLVED, 1 DEFERRED.** Fresh
  SKEPTIC hypothesis-driven probe with 95+ expressions across 5 probe
  files tested every orchestrator-briefed §9-§12 item at the public
  DuckDB UDF boundary comparing bundled native C++ extension vs forced
  Python fallback through all 5 UDF wrappers + `fhirpath_is_valid`.

  **(QA-001 LOW §9 RESOLVED):** Native C++ `FhirpathIsValidFunction`
  at `extensions/fhirpath/src/fhirpath_extension.cpp:1819-1884`
  returned False for syntactically-valid env var forms `%'name'`
  (string form per §9 backward-compat note) and `` %`name` ``
  (backtick form). The is_valid UDF compiled + evaluated the
  expression against a minimal test resource and returned False on
  ANY runtime exception, conflating the runtime "undefined
  environment variable" error with syntactic invalidity. Per
  GLOBAL_RULES invariant, is_valid validates expression validity,
  not runtime evaluability. Reproducer:
  `SELECT fhirpath_is_valid(%'us-zip')` returned False; should return
  True. Also affected `%undefined-var` (simple-identifier form of an
  undefined env var). Root cause: evaluator throws
  `FHIRPathSpecError("Undefined variable: " + ...)` at
  `evaluator.cpp:2817` for any env var not in the hardcoded list
  (only `%ucum`/`%context`/`%resource`/`%rootResource`/`%sct`/`%loinc`/
  `%vs-administrative-gender`/`%ext-patient-birthTime`); the is_valid
  UDF's inner catch block then returned False unconditionally.

  Surgical fix at
  `extensions/fhirpath/src/fhirpath_extension.cpp:FhirpathIsValidFunction`
  inner catch (around line 1862): now checks
  `e.what().rfind("Undefined variable:", 0) == 0` and returns true
  for that case (the expression is syntactically valid; the error is
  a runtime semantic). Mirrors the existing
  `_is_valid_empty_result_error` pattern in the Python UDF.

  Native C++ extension rebuilt (md5sum
  `d8097c25ea1c01c92e85cf14bf16c7b7`) and copied to both package and
  user install paths. Post-fix: FP-20 probe P3 is_valid matrix 14/14
  spec-correct (was 8/14); FHIRPath duckdb integration 435/435 pass
  (was 434, +1 new test); full conformance 2822/2822 unchanged.

  **(QA-002 LOW §3.2/§5.2 DEFERRED — out of FP-20 scope):** Choice-
  type prefix-match heuristic at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:2958-2981`
  incorrectly treats `referenceRange` as a choice-type variant of
  `reference` because 'R' is uppercase. Reproducer:
  `%resource.descendants().reference` on a Patient with
  `contained[0].referenceRange` returns `[referenceRange[0]]` instead
  of empty. Both backends have the same bug (parity match). R4
  conformance passes 935/935 because patient-example.xml has no
  fields matching the prefix heuristic. Deferred to a future §3.2
  polymorphic items / §5.2 navigation chunk.

  **NOT A BUG Registry (FP-20 SKEPTIC additions):**
  - `%sctvsn` (SNOMED CT version) rejection: Core FHIRPath v2.0.0 §9
    only mandates `%ucum` and `%context`. `%sctvsn` is a FHIR-spec
    extension (FHIR §9.1.7), outside the chunk's authoritative spec
    scope.
  - `type()` returning `{name, namespace}` instead of full
    SimpleTypeInfo/ClassInfo/ListTypeInfo/TupleTypeInfo: §10.2 is STU
    ("Standard for Trial Use"). Partial implementation is defensible;
    native and fallback agree.
  - `%us-zip` (hyphen in simple identifier) accepted by C++ lexer:
    §8.6 lexer-permissiveness side discovery, not a §9 env var issue.
    C++ lexer at `lexer.cpp:368` accepts hyphens inside simple
    identifier env var names; Python fhirpathpy parser does too. Both
    backends consistently accept this non-standard form.

- **FHIRPath FP-18 SKEPTIC iteration 1 §6.6 Math Operations + §6.7
  Date/Time Arithmetic (2026-06-30):** **4 NATIVE DEFECTS RESOLVED,
  1 INTENDED.** Fresh SKEPTIC hypothesis-driven probe with 135
  expressions across 3 rounds (53 + 47 + 35 cases) at the public
  DuckDB UDF boundary comparing bundled native C++ extension vs
  forced Python fallback through all 5 UDF wrappers.

  **(QA-001 HIGH §4.1.4 RESOLVED):** Native C++ Integer*Integer
  overflow-to-Decimal lost precision via `setprecision(17)` scientific
  notation. Reproducer: `2000000000 * 2000000000` returned native
  `'4e+18'` vs fallback `'4000000000000000000.0'`. Root cause:
  pure Integer+Integer overflow path at `evaluator.cpp:8067` promoted
  to Decimal via `FPValue::FromDecimal(result)` without source_text.
  Surgical fix at `evaluator.cpp:8080` routes Integer*Integer overflow
  through `tryIntegerArithmeticText` for exact magnitude via
  schoolbook multiplication on string digits. Same binary64-drift bug
  class as FP-14 EXPLORER QA-001.

  **(QA-002 MEDIUM §4.1.4 RESOLVED):** Native Decimal*Decimal
  collapsed trailing-zero precision. Reproducer: `2.5 * 4.0` returned
  native `'10.0'` vs fallback `'10.00'`. Root cause:
  `decimalWithScaleText` lambda at `evaluator.cpp:8041-8044` stripped
  trailing zeros past `dot + 2`. Surgical fix removed the strip AND
  extended `tryIntegerArithmeticText` at `evaluator.cpp:6027-6097` to
  track operand fractional digit counts and produce scale-aware
  output (sum for `*`, max for `+`/`-`).

  **(QA-003 HIGH §4.1.8 / FP-11 SKEPTIC regression RESOLVED):** Native
  Quantity*scalar with `apply_integral_normalize=false` dropped the
  required `.0` decimal point for integer-valued products. Reproducer:
  `5.0 'g' * 3` returned native `'15 \'g\''` vs fallback `'15.0 \'g\''`.
  Root cause: `normalizeQuantityArithmeticSourceText` at
  `evaluator.cpp:2289-2296` fell through to `formatDecimalNumber` which
  returned source_text directly (e.g. `'5'` not `'5.0'`). FP-11
  SKEPTIC comment at line 7880-7883 documented intent to preserve
  `1.0` rendering but implementation didn't match. Surgical fix added
  `preserve_decimal_point` parameter at `evaluator.cpp:2240-2307`;
  scalar Quantity*number paths at line 7973-7990 pass it based on
  Quantity operand source_text. Also propagated source_text through
  unary minus on Quantity at `evaluator.cpp:8149-8162`. The
  `%g` shortest-round-trip loop was also updated to prefer
  `%.0f` integer rendering for integer-valued doubles within int64
  range (avoids `5e+01` scientific form for value 50).

  **(QA-004 LOW §5.5.8 RESOLVED):** Native fhirpath_json Quantity
  serialization used `%.15g` scientific notation for tiny/large
  doubles. Reproducer: `3 'cm' * 12 'cm2'` returned native
  `'[{"value":3.6e-05,"unit":"m.m2"}]'` vs fallback
  `'[{"value":0.000036,"unit":"m.m2"}]'`. Surgical fix at
  `fhirpath_extension.cpp` `FhirpathJsonFunction` Quantity branch
  (line ~1459): integer-valued quantity_value renders as integer text
  (mirroring Python `_to_native` `int(value)` conversion);
  non-integer doubles convert scientific-to-decimal within orjson's
  decimal range (`1e-5 <= |v| < 1e16`) and normalize `e-0N`/`E` to
  orjson's `e-N`/`e` format.

  **(QA-005 LOW §4.1.7 INTENDED):** Native DateTime arithmetic
  preserves input Z literal form; fallback normalizes to `+00:00`.
  Per §4.1.7 "Z is allowed as a synonym for the zero (+00:00) UTC
  offset" — both forms spec-equivalent.

  Native C++ extension rebuilt and copied to both package and user
  install paths. 31 new regression tests in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py`:
  `test_multiplication_precision_preservation_fp18_skeptic` (15 cases),
  `test_decimal_arithmetic_preserves_scale_fp18_skeptic` (3 cases),
  `test_quantity_arithmetic_json_serialization_fp18_skeptic_architect`
  (6 cases),
  `test_quantity_scalar_mult_preserves_decimal_authored_form_fp18_skeptic_architect`
  (7 cases). Post-fix: FHIRPath integration 410/410 (was 379, +31
  new); full conformance 2822/2822 unchanged. Probes:
  `/mnt/d/fhir4ds/.temp/qa/fp18_skeptic_2026_06_30/probe{,2,3}.py`,
  `architect_probe.py`.

  **Architecture Drift Log (FP-18 SKEPTIC additions):**
  - (LOW, deferred) Decimal Quantity * scalar where the Quantity has
    non-zero fractional digits (e.g. `3.14 'g' * 100`) preserves full
    scale in Python (`314.00 'g'`) but only preserves single-decimal
    in native (`314.0 'g'`). The current
    `normalizeQuantityArithmeticSourceText` only preserves the
    presence of a decimal point, not the full operand scale.
    Numerically equivalent under §6.1.1; deferred because full Decimal
    scale tracking through Quantity arithmetic requires either porting
    Python's Decimal module to C++ or using GMP.

  **NOT A BUG Registry (FP-18 SKEPTIC additions):**
  - DateTime Z offset preservation vs +00:00 normalization: per §4.1.7
    both are spec-equivalent UTC offset synonyms.

- **FHIRPath FP-16 HISTORIAN iteration 1 §6.4 Collections systematic
  spec-walkthrough (2026-06-29):** **VERIFIED CLEAN.** A fresh
  HISTORIAN systematic spec-walkthrough enumerated every normative
  rule from FHIRPath v2.0.0 §6.4.1 (`|`/`union()`), §6.4.2 (`in`
  membership), §6.4.3 (`contains` containership) at the public DuckDB
  UDF boundary comparing bundled native C++ extension vs forced
  Python fallback through all 5 UDF wrappers. 209 distinct cases ×
  5 wrappers = ~700+ parity cells across 9+ spec-rule groups. All
  cases parity-clean. Independent verification of the prior FP-16
  SKEPTIC clean-run; no native code changes, no native rebuild.
  Coverage: union dedup using §6.1 equality (Integer≡Decimal, UCUM
  commensurable, Date≠DateTime, Time precision-mergeable, Boolean≠
  Integer, negative-zero equivalence, Decimal arithmetic equality
  intact, Unicode/emoji/NUL byte byte-for-byte dedup); `in` empty-
  propagation rules (LHS empty→empty, RHS empty→false, missing-path
  variants); `contains` empty-propagation rules (RHS empty→empty,
  LHS empty→false); converse property exhaustive verification
  (`(a in b) = (b contains a)` across 9 type dimensions); singleton
  enforcement (literal multi-item LHS/RHS statically rejected by
  `fhirpath_is_valid`, resource-path runtime error via row-resilience);
  FP-13 HISTORIAN cross-unit temperature carry-over verified intact
  (`0 'Cel' in (32 '[degF]' | 100 '[degF]')` returns false in both
  backends because §6.1 equality returns empty per offset-temperature
  guard, and "empty equality" means "not a member" per §6.4.2);
  15 spec-anchor value verifications proved every documented spec
  example produces its spec-defined output. **0 non-terminal
  CRITICAL/HIGH/MEDIUM issues.** No source changes, no new regression
  tests (surface already has comprehensive coverage in 11 named tests
  in `test_collection_operator_parity.py` covering 100+ parametrized
  cases). Full conformance 2822/2822 unchanged. Probes:
  `/mnt/d/fhir4ds/.temp/qa/fp16_historian_2026_06_29/probe.py`
  (79 cases), `probe2.py` (57 deep edges), `probe3.py` (30 eval +
  30 validity), `probe_spec.py` (15 anchors + 25 validity pairs),
  `probe_singleton.py` (11 validity + 45 eval singleton cells).

- **FHIRPath FP-14 EXPLORER iteration 1 §6.2 Comparison Decimal
  arithmetic adjacent-integer parity (2026-06-29):** **RESOLVED
  (1 native defect).** Fresh EXPLORER pathological-input fuzz of 261
  expressions across 3 rounds (152 + 53 + 56 cases) targeting all
  orchestrator-briefed vectors (extreme Decimal magnitudes, NaN/Infinity
  edges, multi-byte Unicode strings, polymorphic choice-types, deeply
  nested comparison chains, timezone edges, composed comparisons with
  iif/where/implies, very large strings, integer overflow in comparison,
  mixed-type comparison edges) found 1 HIGH-severity native defect in
  the Decimal arithmetic path that feeds §6.2 comparison. Native C++
  Decimal +/- at `evaluator.cpp` ~7800+ used binary64 `double` via
  `getNumericValue(lv) + getNumericValue(rv)`; at the 2^53 boundary,
  `9007199254740992.0 + 1.0` rounded back to `9007199254740992.0`
  because binary64 cannot represent `9007199254740993`. The Python
  fallback uses Decimal arithmetic preserving exact digits. Reproducer
  (3 forms): `(2).power(53) < (2).power(53) + 1` returned `false` in
  native vs `true` in fallback; same for `(2).power(63)` and other
  adjacent-integer arithmetic cases above 2^53. Note: raw Decimal
  literal comparison `9007199254740992.0 < 9007199254740993.0` worked
  correctly (returns `true` in both) because the §6.2 comparison path
  uses `numericTextForComparison` + `compareDecimalText`. The defect
  was specifically in the Decimal arithmetic path producing the operand.

  Root cause: same binary64-drift bug class documented across FP-07/
  FP-08/FP-11 SKEPTIC/HISTORIAN/EXPLORER (6th instance). FP-11 SKEPTIC
  added `normalizeQuantityArithmeticSourceText` to mask binary64 noise
  at Quantity +/-/*/ sites (evaluator.cpp 7657-7735) but did NOT apply
  equivalent treatment to the plain Decimal arithmetic path. The mask
  approach also does NOT address the fundamental issue: binary64 cannot
  represent adjacent integers above 2^53. The mask only rounds shortest-
  round-trip; for `(2).power(53) + 1` both operands already round-trip
  identically so the mask has no effect.

  Surgical fix: added `tryIntegerArithmeticText` helper at evaluator.cpp
  after the existing `multiplyIntegerMagnitudes` helper (near line
  5907). Added supporting schoolbook helpers `addIntegerMagnitudes` and
  `subtractIntegerMagnitudes`. The helper performs exact text-based
  integer arithmetic on operands whose source_text represents a pure
  integer (fractional part is empty or all-zeros), returns Decimal-
  shaped source text (e.g. "9007199254740993.0"), and is capped at
  10000 digits to prevent OOM. Mirrors the FP-11 EXPLORER
  `powerIntegerExactText` pattern (QA-001) for +/-/* on integer-valued
  Decimal operands. The fix is wired into the Decimal arithmetic path
  before the binary64 fallback, but is gated on at least one operand
  being non-Integer type to preserve the existing int32-promote-on-
  overflow semantics for pure Integer+Integer arithmetic.

  1 new regression test (17 cases) added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py::
  test_decimal_arithmetic_feeding_comparison_preserves_adjacent_integers_fp14_explorer`.
  Native C++ extension rebuilt and copied to package + user install
  paths (md5sum `24f083eac762b21ddaefc396805842e4`). Post-fix:
  EXPLORER probe round 3 56/56 (was 53/56); rounds 1+2 unchanged;
  full FHIRPath integration 371/371 (was 370 + 1 new test); FP-14
  SKEPTIC fix intact; FP-13 HISTORIAN fix intact; full conformance
  2822/2822 unchanged. Same binary64-drift bug class as FP-07/FP-08/
  FP-11 SKEPTIC/HISTORIAN/EXPLORER — the lesson is unchanged: every
  native C++ Decimal-producing arithmetic path on FHIRPath values
  needs an audit for source_text preservation AND for binary64 noise
  masking AND (now) for adjacent-integer preservation above 2^53. The
  mask approach used at Quantity sites is insufficient for cases where
  binary64 cannot represent adjacent integers; text-based integer
  arithmetic is required for those. Audit pattern: `grep -n
  "getNumericValue" extensions/fhirpath/src/fhirpath/evaluator.cpp`
  returns all numeric-value extraction sites; each arithmetic use of
  getNumericValue on operands that may have integer-valued source_text
  is a candidate for the tryIntegerArithmeticText fast-path. Probe
  artifacts: `/mnt/d/fhir4ds/.temp/qa/fp14_explorer_2026_06_29/probe.py`
  (152 cases / 15 groups), `probe_round2.py` (53 cases / 7 groups),
  `probe_round3.py` (56 cases / 7 groups), `diag_power_arith.py`
  (root-cause diagnostic).

- **FHIRPath FP-14 SKEPTIC iteration 1 §6.2 Comparison cross-unit
  temperature parity (2026-06-29):** **RESOLVED (1 native defect).**
  Fresh SKEPTIC hypothesis-driven probe of 89 cases across 9 hypothesis
  groups found 1 HIGH-severity native defect in §6.2 comparison: the
  operator path at `evaluator.cpp:7539-7559` lacked the
  `isOffsetTemperatureUnit` guard that FP-13 HISTORIAN added to §6.1
  equality at 5 sites. Reproducer: `1 'Cel' < 33.8 '[degF]'` returned
  `False` native vs `NULL` fallback (must be `NULL`); same defect on
  `>`, `<=`, `>=`, and reverse-argument forms. Root cause: UCUM table
  marks `[degF]` with sentinel factor -1.0; the multiplicative-only
  `convertQuantityToBase` path at line 7570-7572 computed nonsense
  instead of either the correct affine conversion
  (degF = degC × 9/5 + 32) or empty. Surgical fix added the same
  `isOffsetTemperatureUnit` guard at line 7540-7558, mirroring the
  FP-13 HISTORIAN equality fix pattern at line 7290-7294. The
  unit-difference gate (`lv.quantity_unit != rv.quantity_unit && ...`)
  preserves same-unit passthrough (1 'Cel' < 2 'Cel') via the existing
  decimal-text fast-path at line 7559-7567. Native extension rebuilt
  and copied. Post-fix: SKEPTIC probe 89/89 (was 81/89); FP-13
  HISTORIAN equality fix intact; FHIRPath pytest 1498/1498 (was 1497,
  +1 new test); full conformance 2822/2822 unchanged. Same offset-
  temperature bug class as FP-08 EXPLORER (convertQuantityUnit),
  FP-13 HISTORIAN (§6.1 equality) — the lesson is unchanged: any
  cross-unit conversion edge requires explicit category/dimension
  validation, not just base-unit equality. **Known design debt
  (LOW priority):** the flat `ucum_units.hpp` table cannot represent
  offset-based conversions; the surgical `isOffsetTemperatureUnit`
  guard is the workaround.

- **FHIRPath FP-13 HISTORIAN iteration 1 §6.1 Equality cross-unit
  temperature parity (2026-06-29):** **RESOLVED (1 native defect).**
  Fresh HISTORIAN systematic spec-walkthrough of 231 cases found 1
  HIGH-severity native defect: cross-unit temperature equality
  returned wrong Booleans instead of empty. `1 'Cel' = 33.8 '[degF]'`
  returned `False` native vs `NULL` fallback. Root cause: FP-08
  EXPLORER added `isOffsetTemperatureUnit` guard to `convertQuantityUnit`
  (evaluator.cpp:2010, the toQuantity(unit) conversion path) but
  missed the equality operator path. Surgical fix added the same
  guard at 4 sites in evaluator.cpp: (1) forward declaration at line
  653; (2) `quantityEqualState` at line 1598 (returns -1/empty for
  JSON path `=`); (3) `quantityEquivalentState` at line 1622 (returns
  -1/empty for JSON path `~`); (4) `quantityValuesEqual` at line 1867
  (returns false for distinct/isDistinct/subsetOf/supersetOf —
  matches Python fallback's distinct() behavior); (5)
  `valuesEqualState` lambda at line 7240 (returns -1/empty for main
  `=` operator path). `valuesEquivalentState` lambda at line 7166
  already calls `quantityEquivalentState` so is automatically covered.
  Native extension rebuilt and copied. Post-fix: HISTORIAN probe
  231/231 (was 230/231); FHIRPath pytest 369/369; full conformance
  2822/2822 unchanged. Same offset-temperature bug class as FP-08
  EXPLORER (convertQuantityUnit) — the lesson is unchanged: any
  cross-unit conversion edge requires explicit category/dimension
  validation, not just base-unit equality. **Known design debt
  (LOW priority):** the §6.2 comparison operator path at line
  7460-7480 still lacks this guard (QA-002 deferred to FP-14).

- **FHIRPath FP-11 EXPLORER iteration 1 §5.7.7/§5.7.10/§5.7.3 Math
  pathological-input parity (2026-06-29):** **RESOLVED (3 native
  defects):** Fresh EXPLORER fuzz of 127 pathological expressions
  across 12 vector groups found 3 native C++ defects in §5.7 Math.
  (1) `fn_power` at `evaluator.cpp:5817` used `std::pow` returning
  binary64, producing scientific notation for results above 2^53 and
  empty for results above ~1.8e308. Fix: added `multiplyIntegerMagnitudes`
  helper at line 5818 and `powerIntegerExactText` helper at line 5853;
  exact-integer path in `fn_power` at line 5926 for non-negative integer
  exponents on integer bases (capped at 10000 digits to prevent OOM).
  (2) `fn_truncate` Quantity branch at line 5851-5856 rejected large-
  magnitude Quantity values via int64 overflow guard. Fix at line
  5971-5990: routes through `integralTextFromDecimalSource` when
  source_text is available.
  (3) `formatDecimalNumber` at line 7885 collapsed subnormal values to
  `'0.0'` via `setprecision(15) << std::fixed`. Fix: added subnormal
  branch checking `abs(value) < 1e-300` returning source_text (shortest-
  round-trip from `normalizeDecimalMathSourceText`) when it round-trips.
  Uses `strtod` instead of `std::stod` (which throws `std::out_of_range`
  for subnormals). Also added integer-valued re-rendering in
  `normalizeDecimalMathSourceText` at line 2304-2336 to convert
  `"-1e+01"` to `"-10"` for log/exp/ln/sqrt integer-valued results.
  Native extension rebuilt and copied. Post-fix: EXPLORER probe 125/127
  (was 113/127); FHIRPath pytest 1490/1490 (+4 new tests); full
  conformance 2822/2822 unchanged. Same binary64-drift bug class as
  prior FP-07/FP-08/FP-11 SKEPTIC/HISTORIAN. Probe artifact:
  `/mnt/d/fhir4ds/.temp/qa/fp11_explorer_2026_06_29/probe.py`.

- **FHIRPath FP-11 HISTORIAN iteration 1 §5.7.3/§5.7.5/§5.7.6/§5.7.9
  Math text-rendering parity (2026-06-28):** **RESOLVED:** Native C++
  `fn_ln`/`fn_exp`/`fn_sqrt`/`fn_log` (both inline `if (name == ...)`
  at `evaluator.cpp:3950/3967/3983` AND standalone
  `Evaluator::fn_ln`/`fn_log`/`fn_sqrt` at
  `evaluator.cpp:5721/5736/5806`) returned `FPValue::FromDecimal(<double>)`
  with empty `source_text`. The `toString` path at
  `evaluator.cpp:7596-7610` fell back to `std::setprecision(17)` rendering,
  producing 17-sig-digit binary64 expansions like `"2.3025850929940459"`.
  Python fallback `ln`/`log`/`sqrt` returned raw `float` (16 sig digits
  via `str()`); `exp` used `Decimal(format(result, ".17g"))` (17 sig digits).
  Numerical value identical between paths; divergence observable only via
  `fhirpath_text`. Same binary64-drift bug class as FP-07/FP-08/FP-11
  SKEPTIC. Surgical fix: new reusable helper
  `normalizeDecimalMathSourceText(double&)` at `evaluator.cpp:2235`
  produces shortest-round-trip text via precision 1..17 search (mirrors
  Python `str(float)`), appends `.0` for integer-valued results per
  §5.5.8 `(-)?#0.0#`, and does NOT re-parse the double (unlike
  `normalizeQuantityArithmeticSourceText`) because `std::log`/`exp`/`sqrt`
  already produce the same IEEE 754 nearest-double as Python
  `math.log`/`exp`/`sqrt`. Applied at 6 native call sites
  (`evaluator.cpp:3959/3980/4003/5734/5758/5824`). Python fallback
  `exp()` at `fhir4ds/fhirpath/engine/invocations/math.py:288` normalized
  to return raw `result`. Native extension rebuilt and copied. Post-fix:
  HISTORIAN probe 193/193, FP-11 SKEPTIC probe 92/92 unchanged, FHIRPath
  pytest 1486/1486 (+1 new regression test, 15 cases), full conformance
  2822/2822 unchanged. Rebuild/copy `fhirpath.duckdb_extension` after
  future changes to native §5.7 Decimal-returning math paths.

- **FHIRPath FP-09 EXPLORER iteration 1 §5.6 string-search
  embedded-NUL truncation (2026-06-28):** **RESOLVED:** Native C++
  truncated JSON strings at embedded U+0000 NUL bytes. Input
  `{"s":"a b"}` (3 code points) produced `s.length()=1`,
  `s.indexOf('b')=-1`, `s.substring(1,1)={}`, `s.endsWith('b')=false`,
  `s.contains('b')=false` in native, while the Python fallback correctly
  returned 3, 2, ' ', true, true. Root cause: `yyjson_get_str()`
  returns a NUL-terminated `const char*`, and the implicit
  `std::string(const char*)` constructor stops at the first NUL byte.
  Spec citations: FHIRPath §5.6.1-§5.6.5 (String Manipulation operates on
  full Unicode content), FHIR R4 string datatype ("sequence of Unicode
  characters"), RFC 8259 §7 (control chars U+0000-U+001F must be escaped
  but ` ` is valid JSON). Surgical fix: added inline helper
  `yyjsonStringToStd(yyjson_val*)` at evaluator.cpp forward-declarations
  block (uses `yyjson_get_str()` + `yyjson_get_len()`); applied at 3
  §5.6-relevant call sites: `jsonValToString()` line 7541 (PRIMARY —
  covers all search functions via `toString()`), `rawStringValue()`
  lines 1165-1166, `isDateTimeType()` line 1119. The other 45
  `yyjson_get_str` sites handle resourceType/reference/URL/code metadata
  where NUL bytes are not valid FHIR data — deferred to a later audit
  chunk. 2 new regression tests in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py`
  (`test_string_search_embedded_nul_byte_parity`,
  `test_string_search_other_control_chars_preserved`). Native extension
  rebuilt and copied to dev, package, and user-install paths.
  Post-fix: 8/8 string-search parity tests pass (was 6/6), 1480/1480
  FHIRPath pytest pass (was 1478), full conformance 2822/2822 unchanged.
  Reproducer:
  `/mnt/d/fhir4ds/.temp/qa/fp09_explorer_iter1_2026_06_28/post_fix_verify.py`.

- **FHIRPath FP-08 SKEPTIC iteration 1 fresh rerun §5.5.7
  toQuantity(unit) binary64 noise propagation (2026-06-28):**
  **RESOLVED:** Native `(0.1 'g' + 0.2 'g').toQuantity('mg')` returned
  `"300.00000000000006 'mg'"` while the Python fallback returned
  `"300 'mg'"`. Root cause: native Quantity arithmetic at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:6940-6998` uses
  `double` not `Decimal`, producing binary64 noise like
  `0.30000000000000004` which then propagated through
  `convertQuantityUnit` (`evaluator.cpp:1883-1955`). The prior FP-08
  EXPLORER fix to `convertQuantityUnit` only normalized the final
  rendered value at precision 17 (the shortest round-trip for noisy
  doubles). Surgical fix at `evaluator.cpp:1920`: cap the shortest-
  round-trip search at precision 15 (IEEE 754 double's guaranteed-
  unique significant digits) and add a `%.15g` fallback render for
  values that don't round-trip at 1..15. Spec citations: §5.5.7
  toQuantity unit conversion, §4.1.4 System.Decimal ("rational number
  with implicit precision" — not binary64 noise), §4.1.8 Quantity
  value is Decimal. The §5.7 root cause (native Quantity `+`/`-`/`*`
  using `double` not `Decimal`) is deferred to FP-11 SKEPTIC; the
  §5.5.7 boundary is now parity-clean but the underlying
  `(0.1 'g' + 0.2 'g').value` still returns `0.30000000000000004`.
  1 new regression test added in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py::
  test_arithmetic_result_quantity_conversion_uses_decimal_not_binary64_fp08_skeptic`
  (9 cases covering +, *, -, direct literal regression). Native C++
  extension rebuilt and copied to both package and user install paths.
  Full conformance 2822/2822 unchanged.

- **FHIRPath FP-08 HISTORIAN §5.5.7 toQuantity String-decimal precision
  drift (2026-06-28):**
  **RESOLVED:** Native `fn_toQuantity` String→Quantity branch at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:fn_toQuantity`
  (around line 4935-5007) constructed the output `FPValue` without
  setting `source_text`. As a result, `'0.0'.toQuantity().toString()`
  returned `"0 '1'"` (stripping the trailing `.0`) instead of
  `"0.0 '1'"`. Spec violations: §5.5.7 String→Quantity regex parses
  value as Decimal; §4.1.4 mandates fixed-precision decimal formats;
  §5.5.8 Quantity toString format `(-)?#0.0# (('«unit»')|(«unit»))`
  requires at least one fractional digit. Surgical fix captures the
  parsed numeric substring into `num_text` BEFORE the unit-parse loop
  advances `idx` (without this, `idx` would point past the unit suffix
  and `s.substr(num_start, idx - num_start)` would grab number+
  whitespace+unit), applies the same Python-`Decimal(str)` normalization
  that FP-07 SKEPTIC established for `fn_toDecimal` (drop leading `+`,
  collapse leading zeros in the integer part), and assigns
  `v.source_text = num_text`. Same binary64-drift bug class as FP-07
  SKEPTIC/HISTORIAN/EXPLORER (toDecimal branches) — String-decimal
  branch was the missed sibling for the Quantity path. 1 regression
  test added in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py::
  test_string_decimal_to_quantity_preserves_precision_fp08_historian`
  (6 parametrized cases: `'0.0'`, `'5.5'`, `'-5.5'`, `'+5'`, `'00.5'`,
  `'3.14159265'`). Native C++ extension rebuilt and copied to both
  package and user install paths. Full conformance 2822/2822 unchanged.

- **FHIRPath FP-07 HISTORIAN §5.5.6 toDecimal Integer-effective-type
  precision drift (2026-06-28):**
  **RESOLVED:** Native `fn_toDecimal` at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:4669-4671` Integer
  effective-type branch (for JsonVal-wrapped FHIR integer primitives)
  returned `FPValue::FromDecimal(getNumericValue(val))` without setting
  `source_text`. As a result, large JSON integers above 2^53 lost
  precision through binary double conversion AND produced scientific
  notation in downstream `toString()`. Reproducers:
  `9223372036854775807.toDecimal().toString()` returned
  `['9.2233720368547758e+18']` native vs `['9223372036854775807.0']`
  fallback; `-9223372036854775808.toDecimal().toString()` returned
  `['-9.2233720368547758e+18']` native vs
  `['-9223372036854775808.0']` fallback;
  `9007199254740993.toDecimal().toString()` returned
  `['9007199254740992.0']` native (rounded down to nearest binary64-
  representable integer) vs `['9007199254740993.0']` fallback (exact).
  Spec violations: §5.5.6 Integer/Long promotion to Decimal, §4.1.4
  fixed-precision decimal formats, §5.5.8 Decimal toString uses decimal
  digit notation. Single-branch surgical fix sets `source_text` from
  canonical JSON integer text via existing `jsonNumberText(val.json_val)`
  helper, appending `.0` for Decimal surface per §4.1.8. Same binary64-
  drift bug class as FP-13 EXPLORER (equality), FP-14 SKEPTIC
  (comparison), and prior FP-07 SKEPTIC (Decimal-effective-type +
  String branches of fn_toDecimal) — Integer-effective-type branch was
  the third missed sibling. All four Decimal-producing surfaces in
  `fn_toDecimal` (native-literal Decimal, JsonVal-Decimal, JsonVal-
  Integer, String) now preserve canonical text. 1 regression test
  added in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py::
  test_fhir_integer_primitive_to_decimal_preserves_exact_text_fp07_historian`.
  Probe artifacts: `.temp/qa/fp07_historian_2026_06_28/probe.py`
  (116 cases), `deep_probe.py` (68 cases). Native extension rebuilt
  and copied. Full conformance 2822/2822 unchanged.
- **FHIRPath FP-07 SKEPTIC §5.5.6 toDecimal FHIR-decimal-JsonVal gap +
  binary64 precision drift (2026-06-28):**
  **RESOLVED:** Native `fn_toDecimal` at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:4647` had two HIGH-severity
  defects. (1) It lacked a branch for `effectiveType(val)==Decimal` when
  the input is a JsonVal-wrapped FHIR decimal primitive, so
  `Observation.valueDecimal.toDecimal()` returned empty in native C++ while
  the forced Python fallback returned `[1.5]`. The check
  `if (t != FPValue::Type::String) return {};` was an under-reach: it
  correctly rejected Date/DateTime/Time/Quantity but also rejected Decimal
  effective type. Sanity check: `Observation.valueDecimal.convertsToDecimal()`
  returned `[true]` in both paths (so converts-to worked while to did not).
  (2) It parsed String→Decimal via `std::stod` (IEEE 754 binary64), losing
  decimal precision per §4.1.4 "implementations should use fixed-precision
  decimal formats". Reproducer: `'3.14159265'.toDecimal().toString()` returned
  `['3.1415926500000002']` in native vs `['3.14159265']` in fallback (same
  for `'0.1'`, `'123456789.123456789'`, etc.). Fix added an explicit Decimal
  effective-type branch (mirrors Integer branch but pulls canonical text via
  `jsonNumberText()`) and preserves the parsed String source_text on the
  output Decimal, normalized to drop leading '+' and collapse leading zeros
  to match Python's `Decimal(str)` formatting. Two regression tests added in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`:
  `test_fhir_decimal_primitive_to_decimal_matches_fallback_fp07_skeptic` and
  `test_string_to_decimal_preserves_precision_fp07_skeptic`. Probe artifact
  `.temp/qa/fp07_skeptic/probe.py` covers 122 §5.5.4-§5.5.6 cases.
- **FHIRPath FP-05 HISTORIAN §5.3 nested-array indexer parity drift
  (2026-06-28):**
  **DEFERRED:** `Evaluator::evalMemberAccess` uses an `add_flattened`
  lambda at `extensions/fhirpath/src/fhirpath/evaluator.cpp:2324-2345`
  that recursively flattens nested JSON arrays during member access.
  The recursion is intended to support FHIR R4 `array<primitive>`
  flattening (e.g. `Patient.name.given` from `[{given:["John","Q"]}]`
  to `["John","Q"]`), but produces divergent behavior vs the forced
  Python fallback when the input data has a non-FHIR nested-array
  field such as `{"resourceType":"Observation","matrix":[["x","y"],["z"]]}`:
  `matrix[0]` → native `['x']` (recurses into inner array), fallback
  `['["x","y"]']` (treats inner array as a single element); same
  divergence on `matrix.count()` (native 3, fallback 2) and
  `matrix.first()`/`last()`/`tail()` and on the `[index]` operator.
  Deferred because FHIRPath §2.1.1 mandates flat collections (spec is
  silent on collections-of-collections), FHIR R4 forbids nested-array
  resource JSON, and aligning native with fallback requires coordinated
  changes plus new parity tests for a case that cannot occur with
  conformant FHIR resources. Revisit only if FHIR R5 introduces
  nested-array primitives or the engine is repurposed for non-FHIR
  JSON. Probe artifacts: `.temp/qa/fp05_historian_iteration_probe.py`,
  `.temp/qa/fp05_historian_edge_probe.py`. Full conformance 2822/2822
  unchanged. No native code change required for this iteration.
- **FHIRPath FP-05 HISTORIAN §5.3/§5.4 exhaustive verification
  (2026-06-28):**
  **VERIFIED CLEAN:** A systematic HISTORIAN pass across all 11 §5.3/§5.4
  functions (`[index]`, `single`, `first`, `last`, `tail`, `skip`,
  `take`, `intersect`, `exclude`, `union`/`|`, `combine`) verified every
  normative rule with 115+ targeted test cases comparing native C++ vs
  forced Python fallback. Coverage included in-range/out-of-range/
  negative/non-integer index types, `single()` row-resilience vs
  literal-union static invalidity, empty/singleton first/last/tail,
  integer-only `skip`/`take` with negative/zero/extreme/empty/
  non-integer arguments, dedup-vs-preserve-duplicates semantics,
  Quantity/temporal/Integer≡Decimal/complex-object equality, 2-arg
  `combine(other, preserveOrder)` extension, scoped `select()` chains,
  and resource-backed `Patient.name`/`identifier` paths. Result: 0
  parity diffs, 0 validity diffs, 0 native/fallback exceptions on
  FHIR-conformant inputs. The prior FP-05 SKEPTIC `combine(other,
  preserveOrder)` fix remains intact. Existing 8 collection-operator
  parity tests pass. Full conformance 2822/2822 unchanged.
- **FHIRPath FP-03 HISTORIAN §5.1 Existence exhaustive verification
  (2026-06-28):**
  **VERIFIED CLEAN:** A systematic HISTORIAN pass across all 12 §5.1
  functions confirmed full native C++ vs forced Python fallback parity
  with 148 targeted test cases (77 iteration + 71 deep). Every normative
  rule from FHIRPath §5.1 was verified: vacuous truth on
  `all`/`allTrue`/`allFalse` empty inputs, false-on-empty for
  `anyTrue`/`anyFalse`, `subsetOf`/`supersetOf` empty-input asymmetry
  per spec, `count()` Integer-return (0 for empty), `distinct()` `=`
  semantics (1 'g' vs 1000 'mg' remain distinct), `isDistinct()` empty
  -> true (0 = 0). Coverage extended to resource-backed paths,
  `$index`/`$this` scope in criteria, composed select/where/distinct/
  count chains, Boolean-aggregate non-Boolean-item errors, and 9
  invalid arity cases. Result: 0 parity diffs, 0 validity diffs, 0
  exceptions. The prior FP-03 SKEPTIC fix (bare no-arg `exists()`
  dispatch in `Evaluator::evalFunction()`) remains intact. Existing
  14/14 existence parity tests pass. Full conformance 2822/2822
  unchanged. Probe artifacts: `.temp/qa/fp03_historian_iteration_probe.py`
  and `.temp/qa/fp03_historian_deep_probe.py`. No code changes required.
- **FHIRPath FP-03 SKEPTIC fresh §5.1.2 bare `exists()` silent failure
  (2026-06-27):**
  **FIXED:** `Evaluator::evalFunction()` previously had no dispatch
  branch for `name == "exists"` in the bare no-source no-arg form.
  Because `parser.cpp:456-468` parses bare `exists()` (without
  `source.exists(...)`) as `NodeType::FunctionCall` rather than
  `NodeType::ExistsCall`, the function fell through to the
  unknown-function return-empty `{}` at evaluator.cpp:4117. Public
  `fhirpath_is_valid()` reported True because the parser accepts the
  bare form, making the silent failure invisible to validity-based
  probes. Per FHIRPath §5.1.2, no-arg `exists()` must mirror
  `count() > 0`. Fix added `if (name == "exists") { return
  evalExists(node, input, doc); }` right after the `where` dispatch in
  `evalFunction()`. `evalExists` already handles both no-arg and
  1-arg cases. Guard with `.temp/qa/fp03_skeptic_fresh_probe.py`,
  `test_existence_parity.py::test_bare_exists_no_arg_matches_count_gt_zero_in_native_and_fallback`,
  and the new native sqllogictest assertions for `exists()` bare,
  `{}`-method, `(1)`-literal, and missing-path forms. Rebuild and
  copy `fhirpath.duckdb_extension` after future `evalFunction`
  dispatch changes.
- **FHIRPath FP-15 HISTORIAN iter 1 §6.3 Types FHIR primitive hierarchy
  + SimpleQuantity (2026-06-29):** **2 NATIVE DEFECTS RESOLVED.**
  (QA-001 HIGH §6.3.1 / FHIR R4) Native C++ at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:8793` over-permissive
  `is FHIR.string` matching — treated any JSON-string-encoded FHIR
  primitive as a subtype of `string`. Per FHIR R4 only `id`/`code`/`uri`/
  `url`/`canonical`/`oid`/`uuid`/`markdown` are valid string-subtypes;
  `date`/`dateTime`/`instant`/`time` are sibling primitives under Element.
  Reproducer: `Patient.birthDate is FHIR.string` returned `[true]` native
  vs `[false]` fallback. Surgical fix at evaluator.cpp:8775-8819
  restricts the non-exact `is FHIR.string` branch to actual string-subtypes
  via `fhirTypeIsA(actual_type, "string")`. (QA-003 LOW §6.3.1 / FHIR R4)
  `SimpleQuantity` was missing from the C++ `fhirTypeIsA` hierarchy table
  at evaluator.cpp:874-1062 — native rejected `X is SimpleQuantity` and
  `X as SimpleQuantity` as invalid type specifiers while the Python
  fallback accepted them. Surgical fix at evaluator.cpp:1028-1032 added
  `{"SimpleQuantity", "Quantity"}`. Native extension rebuilt (md5sum
  `e71c25424b22072e831d386fc5e477ec`) and copied to both package and
  user install paths. Post-fix: HISTORIAN probe 0 diffs for both
  categories; FHIRPath pytest 376/376 (+3 new tests); full conformance
  2822/2822 unchanged. Rebuild/copy `fhirpath.duckdb_extension` after
  future native hierarchy-table or `is FHIR.string` matching edits.
- **FHIRPath FP-15 HISTORIAN fresh §6.3 empty `is` inputs (2026-06-12):**
  **FIXED:** Native `Evaluator::fn_isType()` must validate type specifiers
  before empty-input short-circuiting. Ordinary missing-path checks such as
  `missing is Integer` and `missing.is(Integer)` return false, but absent FHIR
  primitive paths such as `Observation.issued is instant` stay empty to match
  the official R4 conformance fixture. Keep this aligned with Python
  `types.is_fn()` and DuckDB fallback choice assertion behavior; after native
  edits rebuild and copy `fhirpath.duckdb_extension`, then run type parity,
  environment parity, native unittest, FHIRPath R4 conformance, and full
  conformance.
- **FHIRPath FP-15 SKEPTIC fresh §6.3 type operators (2026-06-12):**
  **FIXED:** Native type-specifier validation must not be a stale resource
  allowlist split from `fhirTypeIsA()`. Fresh FP-15 probing reproduced the
  review-10 risk: valid R4 resources such as `CodeSystem`,
  `QuestionnaireResponse`, `Binary`, and `Parameters` were rejected by
  `ofType()`/`is`/`as` chains before subtype matching could run. Native
  `isKnownFHIRType()` now accepts resource/datatype names through
  `fhirTypeIsA(..., Resource|Element)` and keeps only primitive/root names as
  a small explicit set. Guard with `test_type_parity.py`, native
  `fhirpath.test`, and rebuilt bundled extension hash checks after future
  `fn_isType()`, `fn_asType()`, `evalOfType()`, or type metadata edits.
- **FHIRPath FP-14 EXPLORER fresh §6.2 comparison verification (2026-06-12):**
  **VERIFIED CLEAN:** A fresh 37-expression public DuckDB probe matched the
  bundled native extension against forced Python fallback for comparison
  operators over exact large Long/Decimal/JSON numerics, same-unit and
  converted Quantity paths, resource-backed Date/DateTime timezone ordering,
  Unicode lexical String ordering, empty/multi-item row resilience, and
  statically invalid Boolean/literal-multi-item comparisons. Keep ad hoc
  `.temp/qa` probes pinned to the checkout root on `sys.path`; running them
  from `.temp` can otherwise import an installed stale package and report
  false native comparison regressions.
- **FHIRPath FP-14 SKEPTIC fresh §6.2 comparison exact numeric ordering (2026-06-12):**
  **FIXED:** Native C++ comparison must not order Integer/Long/Decimal,
  JSON numeric paths, or same-unit Quantity values through binary `double`.
  Adjacent same-type comparable values above 2^53 must preserve authored/JSON
  decimal text, e.g. `9223372036854775806L < 9223372036854775807L`,
  `9007199254740992.0 < 9007199254740993.0`, `bigA < bigB`,
  `9007199254740992 'mg' < 9007199254740993 'mg'`, and
  `valueQuantity < component.valueQuantity`. Native now compares canonical
  decimal text for numeric operands and same-unit Quantity operands, preserves
  integer Quantity literal source text, and uses source-preserving JSON
  Quantity materialization in comparison. Guard with
  `.temp/qa/fp14_skeptic_fresh_probe.py`, Python/native parity tests, and
  native sqllogictest; rebuild/copy `fhirpath.duckdb_extension` after future
  native comparison changes.
- **FHIRPath FP-13 EXPLORER fresh §6.1 equality/equivalence (2026-06-12):**
  **FIXED:** Forced Python fallback Quantity equivalence must preserve
  original operand precision after unit conversion; comparing only converted
  base values made `185 '[lb_av]' ~ 83.9 'kg'` false while native/spec
  equivalence is true. Native C++ JSON number equality/equivalence must not
  route raw JSON numbers through binary `double`: values such as
  `9007199254740992` and `9007199254740993` must remain distinct for direct
  path, complex-object, and array `=`, `!=`, `~`, and `!~` checks. Keep
  `jsonNumbersEqual()`, `jsonNumbersEquivalent()`, `fpValuesEqual()`,
  `valuesEqualState`, and `valuesEquivalentState` aligned; rebuild/copy
  `fhirpath.duckdb_extension` after native equality edits.
- **FHIRPath FP-13 HISTORIAN fresh numeric/Quantity equality (2026-06-12):**
  **FIXED:** Native C++ and forced Python fallback now apply §6.1 implicit
  numeric-to-Quantity unit `1` comparison for examples such as
  `23 = 23 '1'`, `23 ~ 23 '1'`, and resource-backed UCUM code `1` Quantity
  comparisons against numeric primitives. Quantity equivalence over
  non-commensurable units such as `1 'cm' ~ 1 's'` returns empty/NULL, while
  commensurable mass units such as `[lb_av]` and `kg` compare through canonical
  UCUM base conversion. Keep `fpValuesEqual()`, `evalBinaryOp()`,
  `valuesEqualState`, `valuesEquivalentState`, Python `equality.py`, native
  sqllogictest, and bundled extension freshness aligned.
- **FHIRPath FP-13 SKEPTIC fresh §6.1 equality/equivalence (2026-06-12):**
  **FIXED:** Native string equivalence now decodes UTF-8, maps Unicode
  White_Space code points one-for-one to ASCII spaces without collapsing or
  trimming, and applies Unicode case mapping to match the Python fallback.
  Native Quantity equality now returns empty only for mixed calendar-vs-UCUM
  year/month equality; week/day/hour/minute/second/millisecond durations compare
  through normal unit conversion. Guard with
  `.temp/qa/fp13_skeptic_fresh_probe.py`, `test_equality_parity.py`, and native
  `fhirpath.test`; rebuild/copy `fhirpath.duckdb_extension` after future native
  equality edits.
- **FHIRPath FP-12 EXPLORER primitive metadata tree navigation (2026-06-12):**
  **FIXED:** Native C++ primitive JSON values retained only the FHIR
  field name, so root-level `extension(url)` can inspect `_field` on the root
  resource but nested primitives such as `name.given.extension(url)` could not.
  `children()` / `descendants()` also ignored sibling primitive metadata
  entirely, so `_birthDate.extension` and `_given.extension` are not visible
  through §5.8 tree navigation from the primitive element. `FPValue` now carries
  a `primitive_shadow` pointer, member access and `children()` zip primitive
  values with `_field` metadata, and `fn_extension()` / `fn_children()` consume
  that shadow. Guard with `.temp/qa/fp12_explorer_fresh_probe.py`,
  `test_tree_utility_parity.py`, and native `fhirpath.test`; rebuild/copy the
  bundled extension after future native primitive-navigation changes.
- **FHIRPath FP-12 SKEPTIC fresh trace projection scoping (2026-06-12):**
  **FIXED:** Native `trace(name, projection)` must evaluate the optional
  projection as a scoped function per input item, setting `$this` and `$index`,
  even though `trace()` returns the original input collection. Fresh probing
  found native C++ evaluated the projection once over the whole collection, so
  `name.trace('names', given.single()).given.count() = 2` returned empty when
  two `name` elements each had one `given`. Native now loops over input items
  for projection validation, sets `index_context_`, and restores evaluator
  scope before returning input. Rebuild/copy `fhirpath.duckdb_extension` after
  future native trace changes and keep the FP-12 parity tests aligned.
- **FHIRPath FP-11 EXPLORER fresh native large Long/Decimal math (2026-06-12):**
  **FIXED:** Native C++ Math STU functions that produce integral/Decimal
  results used `getNumericValue()` as `double` for some Integer/Long paths.
  Fresh probing found `9223372036854775807L.ceiling()`, `.floor()`, and
  `.truncate()` wrapping to `-9223372036854775808`,
  `9223372036854774785L.ceiling()` losing one, and
  `9223372036854775807L.power(1).toString()` emitting scientific notation.
  Native now uses preserved numeric `source_text` for exact integral math and
  Decimal-shaped identity powers. Rebuild/copy the bundled extension after
  future native math edits.
- **FHIRPath FP-11 HISTORIAN fresh §5.7 Math Long abs boundary (2026-06-12):**
  **FIXED:** Native C++ `fn_abs()` computed integer absolute values through
  `double`, so `9223372036854775807L.abs()` currently returns
  `-9223372036854775808` instead of the Long input's absolute value. Native
  now uses exact `int64_t` handling for representable Integer/Long `abs()` and
  unary negation values, with native sqllogictest coverage beside the FP-11
  Math assertions.
- **FHIRPath FP-11 SKEPTIC fresh current §5.7 Math Quantity/power semantics (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.7 says `ceiling()`, `floor()`,
  `round([precision])`, and `truncate()` accept Quantity and return Quantity
  with the same unit, and says `power()` always returns Decimal. Native C++
  and forced Python fallback now preserve Quantity units for those functions
  and return Decimal-shaped results for integer powers such as `2.power(3)`.
  Rebuild/copy `fhirpath.duckdb_extension` after future native math edits and
  guard with `.temp/qa/fp11_skeptic_fresh_probe.py`.
- **Milestone code review after FP-01 through FP-10 (2026-06-12):**
  **OPEN REVIEW FINDINGS:** Native regex class range normalization expands
  broad Unicode ranges such as `[a-😀]` codepoint-by-codepoint, causing a short
  valid user regex to take seconds and become invalid after normalized-length
  checks. `readDelimitedIdentifier()` still ignores failed
  `appendUnicodeEscape(...)` surrogate validation, so invalid delimited
  identifier escapes can be treated as valid. Native R4 type knowledge remains
  split across `fhirTypeIsA()` and `isKnownFHIRType()`; direct
  `ofType(CodeSystem)`, `ofType(QuestionnaireResponse)`, `ofType(Binary)`,
  and `ofType(Parameters)` are still not covered by the known-type allowlist.
  See `.ai_loop/code_review_findings.md` `REV-001` through `REV-003` before
  future regex, lexer, or type-reflection edits.
- **FHIRPath FP-10 ARCHITECT Unicode regex `i` flag (2026-06-12):**
  **FIXED:** Native `std::regex_constants::icase` is insufficient for FHIRPath
  Unicode regex behavior over UTF-8. Architect probing found `É` does not
  match `é`, `[é]`, or `[é-ë]` with flag `i` natively, while forced Python
  fallback returns true. Native regex normalization now threads an ignore-case
  signal and adds grouped original/uppercase/lowercase variants for non-ASCII
  literals, class members, and expanded ranges when the FHIRPath `i` flag is
  present, while keeping `std::regex` `icase` for ASCII behavior.
- **FHIRPath FP-10 ARCHITECT Unicode regex class ranges (2026-06-12):**
  **FIXED:** Native regex character-class normalization must handle Unicode
  scalar ranges, not just literal non-ASCII members and negated classes.
  Architect probing found `ecirc.matches('^[é-ë]$')` false natively while
  forced fallback returns true, and `ecirc.replaceMatches('[é-ë]', 'x')`
  leaves `ê` unchanged. The current normalizer separates non-ASCII endpoints
  from the class and leaves `-` as an ASCII literal, so `[é-ë]` became
  endpoints-only. Native now parses class atoms/ranges and expands ranges with
  any non-ASCII endpoint into grouped whole-codepoint alternatives while
  preserving compact pure-ASCII ranges. Guard with the FP-10 EXPLORER
  probe/parity tests and rebuild/copy the bundled extension after native regex
  edits.
- **FHIRPath FP-10 EXPLORER fresh Unicode regex character classes (2026-06-12):**
  **FIXED:** Native C++ regex handling must preserve FHIRPath §5.6 Unicode
  scalar-value semantics inside character classes, not only for normalized
  `.`. Fresh native-vs-forced-fallback probing found `std::regex` treating
  non-ASCII bracket literals as bytes: `accent.matches('^[é]$')` and
  `emoji.matches('^[😀]$')` return false natively while fallback returns true,
  and `replaceMatches('[é]', 'x')` / `replaceMatches('[😀]', 'x')` emit one
  replacement per UTF-8 byte (`xx` / `xxxx`) instead of one per Unicode
  scalar. Native `normalizeFHIRPathRegex()` now rewrites character classes into
  codepoint-aware regex fragments, including whole-codepoint alternatives for
  positive non-ASCII literals and a negative lookahead plus the shared UTF-8
  codepoint matcher for negated classes. Guard with
  `.temp/qa/fp10_explorer_fresh_probe.py`, `test_string_transform_parity.py`,
  and native sqllogictest assertions; rebuild/copy the bundled extension after
  native evaluator edits.
- **FHIRPath FP-10 HISTORIAN fresh Unicode upper/lower case mapping (2026-06-12):**
  **FIXED:** Native `upper()` / `lower()` must convert every Unicode scalar
  value case mapping required by FHIRPath §5.6.6/§5.6.7, not only the ranges
  present in local hand-written tables. Fresh probing found native C++ leaving
  characters such as `ẞ`, `ﬃ`, `𐐨`, `ա`, `ა`, and `ƀ` unchanged while the
  forced Python fallback returned their Unicode case mappings. Native
  `fn_upper()` / `fn_lower()` now decode UTF-8 codepoints, use DuckDB's
  vendored `utf8proc` for one-to-one Unicode case mapping, and preserve
  full-case uppercase expansions that single-codepoint helpers cannot express.
  Keep `.temp/qa/fp10_historian_fresh_probe.py`,
  `test_string_transform_parity.py`, and `extensions/fhirpath/test/sql/fhirpath.test`
  aligned; rebuild and copy `fhirpath.duckdb_extension` after native case-map
  edits.
- **FHIRPath FP-10 SKEPTIC fresh regex transform semantics and flags (2026-06-12):**
  **FIXED:** Native `matches()` must use regex search semantics, not
  `std::regex_match` full-string semantics, and current FHIRPath
  `matches(regex, [flags])` / `replaceMatches(regex, substitution, [flags])`
  accepts optional `i` and `m` flags. Fresh parity probing found native C++
  and forced Python fallback both returning false for official-style internal
  matches such as `url.matches('Library')` and rejecting valid flagged calls.
  Native `fn_matches()` now uses `std::regex_search`, validates only `i`/`m`
  flag characters, applies `icase` for `i`, and normalizes multiline anchors
  for `m`. `replaceMatches()` supports the same flags and uses line-wise
  replacement for multiline anchors to preserve separators. Rebuild and copy
  `fhirpath.duckdb_extension` after touching native regex helpers, and guard
  with `test_string_transform_parity.py` plus sqllogictest FP-10 assertions.
- **FHIRPath FP-09 EXPLORER fresh Python fallback negative substring length (2026-06-12):**
  **FIXED:** Native C++ already returns `''` for in-range `substring(start,
  length)` calls with zero or negative length, matching HL7 FHIRPath §5.6.2.
  Fresh forced Python fallback probing found `s.substring(1, -4)` over
  `abcdef` returning `bc` because fallback used Python's negative slice end
  semantics. Python fallback now returns `""` before slicing whenever the
  validated `length <= 0`. Keep native/fallback parity coverage in
  `.temp/qa/fp09_explorer_fresh_probe.py` and `test_string_search_parity.py`;
  no native evaluator change was needed for this defect.
- **FHIRPath FP-08 SKEPTIC §5.5.7 toQuantity + §5.5.9 toTime native
  over-permissiveness (2026-06-28):**
  **FIXED:** Native C++ `fn_toQuantity` String-bare-keyword path at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:4974-4986` previously
  accepted trailing junk after a calendar duration keyword by capturing
  the entire `s.substr(idx)` as unit_str (with trailing-whitespace trim).
  Per §5.5.7 spec regex full-match implication, `'4 days extra'`,
  `'4 day extra'`, `'4 year extra'`, `'4 d extra'`, and `'4 days '`
  (trailing whitespace) must all be rejected. Fix: removed trailing-
  whitespace trim; added `if (!isBareDurationKeyword(unit_str)) return {};`
  after the existing `isBareDurationCode` check. Native C++ `fn_toTime`
  and `fn_convertsToTime` at evaluator.cpp:7856-7886 and 7540-7568
  previously accepted malformed time strings with trailing colon because
  the check_pos advancement used lenient `if (check_pos+2 <= s.size())
  check_pos += 2;` which advanced past `:` even when 2 digits weren't
  present. Per §5.5.9 format `hh:mm:ss.fff`, colons must be followed by
  exactly 2 digits. Fix: replaced with strict digit-presence verification
  at each step; also added dangling-`.` rejection. Applied symmetrically
  to BOTH fn_toTime and fn_convertsToTime. 68-case post-fix probe shows
  0 native↔fallback diffs; 31/31 conversion parity tests pass; full
  conformance 2822/2822 unchanged. Native C++ extension rebuilt and
  copied to both package (`fhir4ds/fhirpath/duckdb/extensions/`) and
  user install (`~/.duckdb/extensions/v1.5.2/linux_amd64/`) paths.
  Same native-over-permissive-on-regex bug class as the FP-07 EXPLORER
  Python-fallback inverse (Unicode-digit `\d` over-acceptance) — the
  lesson is symmetric: any spec-text regex implies full-match, so both
  native and Python fallback parsers must enforce strict full-match
  semantics, not tolerant trim-then-accept.
- **FHIRPath FP-08 EXPLORER fresh resource-backed Decimal `toString()` (2026-06-12):**
  **FIXED:** Native C++ `Evaluator::jsonValToString()` and Decimal
  `Evaluator::toString()` must not use default stream formatting for JSON real
  values because §5.5.8 Decimal output is decimal digit notation, not
  scientific notation. Fresh probing found `smallDecimal.toString()` returning
  `1e-06` and `largeDecimal.toString()` returning `1e+15` in native paths.
  Native now routes JSON real and Decimal output through
  `formatDecimalNumber()`. The same pass fixed max-Long
  `toQuantity().toString()` by preserving integer text in `fn_toQuantity()`
  before Quantity stringification. Rebuild and copy
  `fhirpath.duckdb_extension` after changing native numeric stringification.
- **FHIRPath FP-08 HISTORIAN fresh Quantity string formatting (2026-06-12):**
  **FIXED:** Native `Evaluator::toString(FPValue::Quantity)` must not rely on
  default floating-point stream formatting, because current HL7 FHIRPath
  §5.5.8 Quantity `toString()` uses a decimal digit pattern and exponent
  notation is not a valid public Quantity string representation. Fresh probing
  found native output such as `1e-06 'kg'` and `1e+15 'g'`; native now keeps
  normal integer formatting for ordinary values and uses fixed notation when
  the stream would emit `e`/`E`. Keep the native sqllogictest assertions near
  the FP-08 conversion section and rebuild/copy `fhirpath.duckdb_extension`
  after evaluator formatting changes.
- **FHIRPath FP-07 EXPLORER fresh dynamic format and Long boundary issues (2026-06-12):**
  **FIXED:** Native `Evaluator::evalFunction()` must evaluate Date/DateTime
  conversion `format` arguments against the outer invocation focus for sourced
  calls, just like other ordinary value arguments. Fresh native-vs-forced
  fallback probing found `rawDate.toDate(dateFmt)`,
  `rawDateTime.toDateTime(dateTimeFmt)`, and
  `items.select(rawDate.toDate(dateFmt))` returning empty in native because
  the argument was evaluated against the source string. Native now uses
  `outer_input` for sourced String format arguments and skips format argument
  evaluation for non-String Date/DateTime inputs because §5.5.4/§5.5.5 say
  the format is ignored there. Native Long handling now preserves §4.1 bounds
  discipline for §5.5.6 Decimal conversion: positive
  `9223372036854775808L` is invalid, signed-minimum
  `-9223372036854775808L` is accepted through a parser sentinel, and exact
  Decimal text for Long `toDecimal()` outputs is preserved through
  `source_text`. Rebuild and copy the bundled extension after touching
  `parser.cpp` or `evaluator.cpp`.
- **FHIRPath FP-07 HISTORIAN fresh string Long Decimal conversion (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.5.6 examples require the String value
  `'42L'` to convert through `toDecimal()` and `convertsToDecimal()`, not only
  the Long literal `42L`. Fresh native C++ and forced Python fallback probing
  found both public DuckDB paths returning empty/false for the string form.
  Native `fn_toDecimal()` and `fn_convertsToDecimal()` now recognize optional
  sign + digits + uppercase `L` String inputs, strip the suffix before Decimal
  parsing, and keep malformed suffixes such as `1LL`, `1.0L`, lowercase `1l`,
  exponent notation, and whitespace-padded strings rejected. Rebuild and copy
  the bundled extension after future native Decimal conversion changes.
- **FHIRPath FP-07 SKEPTIC fresh Date/DateTime format and Long Decimal conversion (2026-06-12):**
  **FIXED:** Native now accepts one optional String format argument for
  `toDate`, `toDateTime`, `convertsToDate`, and `convertsToDateTime`, parses
  the required current HL7 §5.5.4/§5.5.5 format tokens, and ignores the
  format for non-string Date/DateTime inputs. Native lexer/parser support now
  recognizes uppercase STU Long literals, including values above the Integer
  range such as `2147483648L`, and feeds them to Decimal conversion, while
  malformed suffixes remain invalid. Rebuild and copy the bundled extension
  after any future changes to
  `extensions/fhirpath/src/fhirpath/evaluator.cpp` or native lexer/parser
  code.
- **FHIRPath FP-06 EXPLORER fresh iif/Boolean/Integer conversion rerun (2026-06-12):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback public UDF behavior for 46 fresh §5.5.1-§5.5.3 expressions in
  `.temp/qa/fp06_explorer_fresh_probe.py`. Coverage included lazy `iif()`
  branch evaluation, singleton non-Boolean criteria (`0`, `0.0`, strings),
  `$index` preservation in `select(iif(...))`, documented Boolean
  representations, Integer signed-string grammar and int32 bounds,
  resource-backed multi-item row resilience, invalid conversion arity, unary
  precedence for `-1.convertsToInteger()`, and prior FP-06 result-wrapper
  row-resilience fixes. Preserve native/fallback parity coverage in
  `test_conversion_parity.py` after touching native `fn_iif()`,
  `fn_toBoolean()`, `fn_convertsToBoolean()`, `fn_toInteger()`,
  `fn_convertsToInteger()`, or public result wrappers.
- **FHIRPath FP-06 HISTORIAN native invalid-expression result wrapper row resilience (2026-06-12):**
  **FIXED:** Public native result UDFs must return empty/NULL for parser or
  lexer invalid expressions and leave `fhirpath_is_valid()` as the validity
  signal. Fresh retry probing found `-2147483649.toInteger()` and invalid
  surrogate string literals throwing through `EvaluateFhirpath()` because
  `GetOrCompile(...) == nullptr` was converted to `std::runtime_error`.
  `EvaluateFhirpath()` now returns an empty collection for a missing AST,
  matching its existing row-resilient `FHIRPathSpecError` path. Guard with
  `.temp/qa/fp06_historian_fresh_probe.py`, Python native/fallback parity
  tests, and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the
  bundled extension after future wrapper edits.
- **SPEC milestone code review after FP-01 through FP-05 (2026-06-12):**
  **OPEN REVIEW FINDINGS:** `REV-FP-001` public native result-UDF invalid parse
  row-resilience was remediated during FP-06 HISTORIAN by returning empty
  collections from `EvaluateFhirpath()` when `GetOrCompile(...)` fails.
  Native delimited
  identifiers call `appendUnicodeEscape(...)` but do not check its failure
  return, so invalid unpaired surrogate identifier escapes are reported valid
  while the forced Python fallback rejects them. The FP-04 R4 hierarchy
  expansion also remains split across hand-maintained `fhirTypeIsA()` and
  `isKnownFHIRType()` tables; direct `ofType(CodeSystem)`,
  `ofType(QuestionnaireResponse)`, `ofType(Binary)`, and
  `ofType(Parameters)` are still rejected. Track the remaining `REV-FP-002`
  and `REV-FP-003` in the milestone `code_review_findings.md`; rebuild/copy
  the bundled extension and add native/fallback parity tests when remediating.
- **FHIRPath FP-05 EXPLORER fresh subsetting/combining rerun (2026-06-11):**
  **VERIFIED CLEAN:** The bundled native extension matched the forced Python
  fallback for 43 fresh §5.3/§5.4 expressions in
  `.temp/qa/fp05_explorer_fresh_probe.py`. Coverage stressed indexer/count
  boundary values, `single()` row resilience on multi-item inputs, dynamic
  scoped arguments inside `select()` for `[index]`, `skip()`, `take()`, and
  `combine()`, duplicate-retaining `combine()`/`exclude()`, duplicate-removing
  `union()`/`intersect()`, malformed `combine(..., preserveOrder)` argument
  shapes, and resource-backed `value[x]` paths. Keep native `evalIndexer()`,
  `fn_take()`, `fn_skip()`, `fn_intersect()`, `fn_exclude()`, `fn_union()`, and
  `fn_combine()` parity-tested against the Python fallback after evaluator
  changes.
- **FHIRPath FP-05 SKEPTIC fresh `combine(..., preserveOrder)` gap (2026-06-11):**
  **FIXED:** Current HL7 FHIRPath §5.4 defines
  `combine(other : collection, [preserveOrder : Boolean]) : collection`, with
  `combine(B, true)` preserving input order while retaining duplicates. Fresh
  native DuckDB/C++ and forced Python fallback probing found
  `ints.combine(otherInts, true)` returning empty/NULL and
  `fhirpath_is_valid=false`. Native `Evaluator::evalFunction()` now allows one
  or two arguments for `combine` only, validates the optional argument as a
  singleton Boolean, keeps duplicate-preserving append behavior, and preserves
  strict one-argument arity for `union()`, `intersect()`, and `exclude()`.
  Rebuild/copy the bundled `fhirpath.duckdb_extension` after future evaluator
  changes.
- **FHIRPath FP-04 EXPLORER native R4 resource hierarchy gap (2026-06-11):**
  **FIXED:** Fresh §5.2 probing found the bundled native extension dropping
  valid R4 resource subclasses from `ofType(Resource)` and
  `ofType(DomainResource)`. The root cause is the embedded native
  `fhirTypeIsA()` / `isKnownFHIRType()` model subset in
  `src/fhirpath/evaluator.cpp`, which lagged the generated Python R4 model
  hierarchy. Native now includes the missing R4 resource parent relationships
  for superclass checks and generated R4 type-specifier names needed by
  `ofType()`. Guard with `.temp/qa/fp04_explorer_fresh_probe.py`, focused
  filter/projection parity tests, and native sqllogictest assertions; rebuild
  and copy `fhirpath.duckdb_extension` after native evaluator edits.
- **FHIRPath FP-04 HISTORIAN fresh filtering/projection rerun (2026-06-11):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback for 24 fresh §5.2 filtering/projection expressions. Coverage
  included strict `where(criteria)` Boolean singleton behavior, `select()`
  flattening and `$index`, projection-only `repeat()` traversal and
  de-duplication, the absence of repeat-local `$index`, `ofType()` FHIR
  supertypes/choice primitives/type-specifier validation, and fresh
  `defineVariable()` scope-leak probes through `select()` and `repeat()`.
  Preserve the fresh probe and focused parity tests after touching
  `evalWhere()`, `fn_select()`, `fn_repeat()`, `evalOfType()`, or public UDF
  result wrappers; rebuild/copy `fhirpath.duckdb_extension` after native
  evaluator changes.
- **FHIRPath FP-04 SKEPTIC fresh repeat `$index` scoping (2026-06-11):**
  **FIXED:** FHIRPath §5.2 says `repeat(projection)` sets `$this` for each
  queued item, and explicitly leaves `$index` undefined/not set during repeat
  iteration. Native C++ must not assign `index_context_` inside
  `fn_repeat()`: doing so makes `a.repeat($index)` create an ever-growing
  sequence until the native loop guard trips, while forced Python fallback can
  hang. Preserve an outer scoped `$index` when repeat is nested under
  `where()`/`select()`/`all()`/`exists()` instead of replacing it. Keep
  `test_filter_projection_parity.py`, `.temp/qa/fp04_skeptic_fresh_probe.py`,
  and native sqllogictest assertions aligned; rebuild/copy the bundled
  `fhirpath.duckdb_extension` after native evaluator changes.
- **FHIRPath FP-03 EXPLORER composed existence rerun (2026-06-11):**
  **VERIFIED CLEAN:** The bundled native extension still matches forced
  Python fallback behavior for 32 fresh §5.1 composed/pathological existence
  expressions. Coverage includes empty/default truth values, nested
  `exists(criteria)` and `all(criteria)`, Boolean aggregate validation,
  scoped `subsetOf()`/`supersetOf()` argument focus, structural JSON equality,
  compatible Quantity equality, numeric/string de-duplication, and invalid
  helper arities. Preserve `.temp/qa/fp03_explorer_fresh_probe.py`,
  `test_existence_parity.py`, and native sqllogictest guardrails after future
  existence/equality evaluator changes; rebuild and copy the bundled
  extension when native code changes.
- **FHIRPath FP-03 SKEPTIC scoped `subsetOf()`/`supersetOf()` argument context (2026-06-11):**
  **FIXED:** Native `Evaluator::evalFunction()` previously evaluated
  `subsetOf()` and `supersetOf()` argument expressions against a root resource
  context, so calls inside scoped functions lost the current item focus.
  FHIRPath scoped-function semantics require expressions inside `select()`,
  `exists(criteria)`, and `all(criteria)` to evaluate relative to each scoped
  item. Native now evaluates those set-comparison arguments against
  `outer_input` when available, matching other ordinary function arguments and
  the forced Python fallback. Keep
  `.temp/qa/fp03_skeptic_fresh_probe.py`,
  `test_existence_parity.py::test_set_comparison_arguments_use_scoped_focus_in_native_and_fallback`,
  and `extensions/fhirpath/test/sql/fhirpath.test` aligned; rebuild and copy
  the bundled `fhirpath.duckdb_extension` after native evaluator changes.
- **FHIRPath FP-02 EXPLORER `implies` RHS singleton evaluation (2026-06-11):**
  **FIXED:** Native `Evaluator::evalBinaryOp()` previously short-circuited
  `false implies <rhs>` before evaluating `<rhs>` as a Boolean singleton.
  FHIRPath §4.2 says Boolean operands are first evaluated as Booleans using
  §4.5 singleton collection rules, so a multi-item RHS such as
  `false implies (1 | 2)` or `false implies arr` must be an evaluation error
  rather than `true`. Native now coerces the RHS before applying the false-LHS
  truth-table return. Keep native evaluation, `fhirpath_is_valid()`,
  `.temp/qa/fp02_explorer_fresh_probe.py`, Python fallback parity, and
  sqllogictest coverage aligned when revisiting this path.
- **FHIRPath FP-02 HISTORIAN native `trim()` invocation arity (2026-06-11):**
  **FIXED:** Native `Evaluator::evalFunction()` dispatches `trim()` but
  did not include it in the exact-zero-argument guard cluster, so calls such as
  `s.trim(1)` and `s.trim({})` evaluated as if no argument had been supplied.
  The HL7 FHIRPath signature is `trim() : String`; `trim` is now covered by
  native exact-zero-arity validation, Python fallback `fhirpath_is_valid()`,
  sqllogictest assertions, and `.temp/qa/fp02_historian_fresh_probe.py`.
  Rebuild and copy `fhirpath.duckdb_extension` after future evaluator changes.
- **FHIRPath FP-01 HISTORIAN unpaired Unicode surrogate string escapes (2026-06-11):**
  **FIXED:** Native `Lexer::readString()` must reject decoded UTF-16
  surrogate escape code units unless a high surrogate is immediately followed
  by a valid low surrogate. Before this fix, `'\uD834'` reached DuckDB as
  invalid Unicode and `fhirpath_is_valid()` returned true. Keep the rejection
  in `appendUnicodeEscape()` narrow: malformed non-surrogate escape sequences
  such as `\u005` are not Unicode escapes and should continue to preserve the
  existing string text. Rebuild and copy `fhirpath.duckdb_extension` after
  lexer changes, and keep `test_literal_parity.py`,
  `.temp/qa/fp01_historian_fresh_probe.py`, and native sqllogictest assertions
  aligned.
- **FHIRPath FP-01 SKEPTIC DateTime timezone offset bounds (2026-06-11):**
  **FIXED:** Native DateTime literal validation must enforce the same timezone
  offset range as FHIR `dateTime`: offset hours below 14 may use minutes
  `00`-`59`, but hour `14` only permits `14:00`. The semantic check belongs
  in `parseDateTimeParts()` rather than the lexer so public result UDFs keep
  returning empty/NULL for invalid temporal literals instead of failing at
  parse/bind time. Keep `extensions/fhirpath/test/sql/fhirpath.test`,
  `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py`, and
  `.temp/qa/fp01_skeptic_probe.py` aligned, and rebuild/copy the bundled
  `fhirpath.duckdb_extension` after native evaluator changes.
- **FHIRPath Section 5.1 native arity validation (Domain 1 SKEPTIC, 2026-06-07):**
  **FIXED:** Native `Evaluator::evalFunction()` must reject invalid arities for
  Section 5.1 existence helpers before dispatch, and `Evaluator::evalExists()`
  must independently reject more than one criteria expression because
  `exists()` is parsed as `NodeType::ExistsCall` and bypasses generic function
  dispatch. Guard zero-arg helpers (`empty`, `count`, `distinct`,
  `isDistinct`, Boolean aggregates), `exists([criteria])`, and exact-one
  helpers (`all`, `subsetOf`, `supersetOf`). Include the FHIR-specific
  zero-argument `hasValue()` helper in the same guard cluster. Keep
  `test_existence_parity.py::test_existence_helpers_reject_invalid_arity_in_native_and_fallback`,
  `.temp/qa/domain1_skeptic_probe.py`, and native SQL tests aligned, and
  rebuild/copy the bundled extension after future evaluator changes.
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
  `truncate` before evaluation. Concrete non-numeric inputs and functions that
  do not accept Quantity should throw `FHIRPathSpecError` so result UDFs return
  empty/NULL and `fhirpath_is_valid()` is false. Optional `round()` precision
  is validated before empty-input propagation to prevent sparse validation from
  hiding invalid precision arguments. `log(base)` uses the outer invocation
  focus for dynamic arguments like `p.log(base)`. Superseding current §5.7
  behavior from 2026-06-12: `ceiling()`, `floor()`, `round()`, and
  `truncate()` accept Quantity, and `power()` returns Decimal.
  Rebuild and copy `fhirpath.duckdb_extension` after native math edits.
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
- **FHIRPath FP-08 dynamic Quantity unit arguments (2026-06-12):** **FIXED:**
  Native `toQuantity([unit])` and `convertsToQuantity([unit])` evaluate
  dynamic unit arguments in the outer invocation context, not against the
  source Quantity/String value. Preserve parity for
  `value.toQuantity(targetUnit)`, `quantityText.toQuantity(targetUnit)`, and
  scoped `items.select(quantityText.toQuantity(targetUnit))`; rebuild and copy
  `fhirpath.duckdb_extension` after touching native dispatch.
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
- **FHIRPath §6.5 Boolean Operand Singleton Errors**: **FIXED 2026-05-17 / FP-17 SKEPTIC, corrected 2026-06-11 / FP-02 EXPLORER**: Native `collectionIsBool()` must throw `FHIRPathSpecError` when asked to convert a multi-item collection, not return `false` as though the operand were empty/unknown. Otherwise `arr or true`, `arr and false`, `arr implies true`, and `false implies arr` leak concrete results instead of public UDF empty/NULL resilience. `false implies <rhs>` may return true only after `<rhs>` has passed singleton Boolean evaluation. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py`; rebuild and copy `fhirpath.duckdb_extension` after touching this path.
- **FHIRPath §6.4 Membership Singleton Errors**: **FIXED 2026-05-17 / FP-16 EXPLORER, VERIFIED CLEAN 2026-06-29 / FP-16 SKEPTIC iter 1 fresh run**: Native `evalBinaryOp()` must throw `FHIRPathSpecError` when `in` has a multi-item left operand or `contains` has a multi-item right operand. Public UDF materialization catches `FHIRPathSpecError` and returns empty/NULL by design, so public DuckDB parity alone will not prove strict compliance. Keep direct/core regression coverage and rebuild/copy `fhirpath.duckdb_extension` after touching this path. The FP-16 SKEPTIC fresh probe (148 cases across 5 rounds) confirmed the multi-item needle rejection is intact in both native C++ and Python fallback, including for statically-known multi-item literal-union needles (`(1 | 2) in ...` → `fhirpath_is_valid=false` via `_has_invalid_membership_literal_unions` precheck in `udf.py:929-950`) and for runtime-only multi-item cases (`nums in nums` → empty via row-resilient wrapper). Empty-collection semantics per §6.4.2/§6.4.3 (LHS empty → empty for `in`; RHS empty → `false` for `in`; RHS empty → empty for `contains`; LHS empty → `false` for `contains`) all correct in both backends.
- **FHIR Quantity Path Equality in Collection Operators**: **FIXED 2026-05-17 / FP-16 HISTORIAN, VERIFIED CLEAN 2026-06-29 / FP-16 SKEPTIC iter 1 fresh run**: `fpValuesEqual()` is the native helper behind `|`, `union()`, `intersect()`, `exclude()`, `in`, `contains`, `distinct()`, and related set-style functions. It must materialize Quantity-like JSON values before raw `yyjson_equals()` checks, or FHIR Quantity paths that are equal under ordinary `=` (`1 cm` vs `10 mm`) will still fail membership/de-duplication. Regression coverage lives in `fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py`; rebuild and copy `fhirpath.duckdb_extension` after native helper changes. The FP-16 SKEPTIC fresh probe re-verified UCUM cross-unit membership (`1 'g' in (1000 'mg' | 2 'g')` → true in both backends), Quantity literal union dedup (`(1 'g' | 1000 'mg').count() = 1`), and the FP-13 HISTORIAN offset-temperature equality carry-over (`0 'Cel' in (32 '[degF]' | 100 '[degF]')` → false in both backends because equality returns empty per the offset-temperature guard, and "empty equality" means "not a member" per §6.4.2 definition).
- **FP-16 §6.4 Collections (SKEPTIC iter 1 fresh run, 2026-06-29)**: 148-case hypothesis-driven probe across 5 rounds (53 + 29 is_valid + 37 + 29 cases) targeting all 8 orchestrator-briefed §6.4 bug classes produced **0 new non-terminal CRITICAL/HIGH/MEDIUM issues**. The §6.4 surface (`|` union, `in` membership, `contains` containership) is well-hardened across native C++ and Python fallback. Coverage: empty handling (10 cases), multi-item needle (4 cases), mixed-type membership (9 cases), Quantity cross-unit membership (7 cases incl. offset-temperature carry-over), Date/Time precision-aware membership (4 cases), ResourceNode unwrap (5 cases), union dedup semantic equality (10 cases), union order unspecified but dedup correct (4 cases), plus 37 pathological stress cases (Unicode/emoji, large collections, polymorphic choice-types, nested unions) and 29 final edge cases (Decimal precision 1.0 vs 1.00000, singleton Date/Time equality, composed where() filters, negation interaction). Implementation cross-check: Python `fhir4ds/fhirpath/engine/invocations/collections.py:336-367` and `combining.py:9-10`; native `extensions/fhirpath/src/fhirpath/evaluator.cpp:7305-7332` and `6521-6540`. No source changes, no new regression tests, no native rebuild. Full conformance 2822/2822 unchanged. Probes: `.temp/qa/fp16_skeptic_2026_06_29/probe{,2,3,4,5}.py`.
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
- **Filtering/Projection Lambda Scope and `ofType()` Subtypes**: **FIXED 2026-05-16 / FP-04 SKEPTIC; UPDATED 2026-06-11**: `where()` and `select()` bind `$index` only for the expression currently under evaluation and restore any outer value afterward. `repeat()` is different under the current §5.2 scoped-function table: it sets `$this` but must not bind a repeat-local `$index`; preserve any outer `$index` instead. `ofType(type)` must include non-primitive FHIR subclasses per FHIRPath §5.2.4; exact-only matching dropped resources for `ofType(Resource)` and `ofType(DomainResource)`. Preserve official R4 primitive behavior: `Patient.gender.ofType(string)` remains empty for FHIR `code`.
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
- **Math Function Argument Guards**: **FIXED 2026-05-17 / FP-11 SKEPTIC, updated 2026-06-12**: Native C++ math functions validate evaluated arguments, not just input collections. `log(base)`, `power(exponent)`, and `round(precision)` reject multi-item arguments; `round()` precision is a singleton Integer with value >= 0; current §5.7 accepts Quantity for `abs()`, `ceiling()`, `floor()`, `round()`, and `truncate()` while `exp()`, `ln()`, `log()`, `power()`, and `sqrt()` remain numeric-only. Public UDFs convert semantic errors to empty/NULL and remain in parity with the forced Python fallback. Regression coverage lives in `test_math_parity.py` and `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled extension after future native math changes.
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

- **FHIRPath FP-12 HISTORIAN fresh rerun (2026-06-12):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback behavior for fresh §5.8/§5.9 tree navigation and utility probes.
  Keep native `children()` and `descendants()` aligned with Python for split
  primitive extension hiding, null-valued child counting, duplicate
  `repeat(children())` semantics, and deep traversal. Native `trace(name,
  projection)` must keep evaluating the optional projection per input item with
  `$this`/`$index`, restore evaluator scope, and return the original input.
  `now()`, `today()`, and `timeOfDay()` must stay deterministic within one
  expression. Guard with `.temp/qa/fp12_historian_fresh_probe.py`,
  `test_tree_utility_parity.py`, and native sqllogictest coverage when
  changing evaluator dispatch.

- **FHIRPath Section 5.6.1-5.6.5 HISTORIAN fresh rerun (FP-09, 2026-06-12):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback behavior for a fresh 66-expression string-search probe covering
  `indexOf(substring)`, `substring(start[, length])`, `startsWith(prefix)`,
  `endsWith(suffix)`, and string-function `contains(substring)`. Preserve
  UTF-8 scalar-value positions for emoji and combining marks, empty String
  search-term results, dynamic sibling-field argument focus inside scoped
  `select()` calls, row-resilient public outputs for runtime type/cardinality
  errors, and the parser/runtime split between `.contains()` and collection
  `contains`. Rebuild/copy the bundled extension after native search edits
  and guard with `.temp/qa/fp09_historian_fresh_probe.py` plus
  `test_string_search_parity.py`.
- **FHIRPath Section 5.6.1-5.6.5 SKEPTIC fresh rerun (FP-09, 2026-06-12):**
  **VERIFIED CLEAN:** The bundled native extension matched the forced Python
  fallback for a fresh 39-expression string-search probe covering
  `indexOf(substring)`, `substring(start[, length])`, `startsWith(prefix)`,
  `endsWith(suffix)`, and string-function `contains(substring)`. Preserve
  UTF-8 scalar-value indexing, sibling-field argument focus, row-resilient
  empty/NULL behavior for runtime type errors, and `contains` function versus
  collection-operator disambiguation. Dynamic runtime type errors should not
  make `fhirpath_is_valid()` false; only statically malformed expression forms
  should. Rebuild and copy the bundled extension after future native search
  edits.
- **FHIRPath FP-05 HISTORIAN fresh subsetting/combining rerun (2026-06-11):**
  **VERIFIED CLEAN:** The bundled native extension matched forced Python
  fallback behavior for a fresh 52-expression §5.3/§5.4 probe covering
  `[index]`, `single()`, `first()`, `last()`, `tail()`, `skip(num)`,
  `take(num)`, `intersect(other)`, `exclude(other)`, `union(other)`/`|`, and
  current `combine(other, preserveOrder)`. Preserve native sqllogictest and
  Python parity coverage for exact arity, strict Integer arguments, public
  row-resilient invalid-result UDF behavior, duplicate semantics, FHIRPath
  equality-backed set helpers, and scoped argument evaluation inside
  `select()`. Run probes with the workspace root pinned on `sys.path` to avoid
  accidentally testing an installed stale package from `.temp/qa`.
- **FHIRPath Section 5.1 HISTORIAN fresh rerun (FP-03, 2026-06-11):**
  **VERIFIED CLEAN:** The bundled native extension matched the forced Python
  fallback and direct Python wrappers for a fresh 36-expression §5.1 matrix
  after the FP-03 SKEPTIC scoped set-comparison fix. The probe covered
  `empty()`, `exists([criteria])`, `all(criteria)`, Boolean aggregates,
  `subsetOf()`, `supersetOf()`, `count()`, `distinct()`, and `isDistinct()`,
  including empty/default truth values, strict criteria failures, full Boolean
  aggregate validation, scoped argument evaluation, structural JSON equality,
  compatible Quantity equality, and public result-UDF row resilience. Keep
  `.temp/qa/fp03_historian_fresh_probe.py` and `test_existence_parity.py`
  aligned after native existence or `fpValuesEqual()` changes.
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
- **FP-12 EXPLORER (2026-06-29) native decimal-primitive text rendering in
  FastText/FastList paths**: `FastPathLookup` at `fhirpath_extension.cpp`
  line ~513 and `JsonValueToOwnedString` at line ~757 previously rendered
  JSON decimal primitives via `std::to_string(yyjson_get_real(value))`
  which uses `setprecision(6) << std::fixed` by the C++ standard
  ([string.conversions]), producing `'12.500000'` for `12.5`. The Python
  fallback uses shortest-round-trip rendering (`'12.5'`), and the non-fast-
  path `Evaluator::jsonValToString` correctly uses
  `formatDecimalNumber(yyjson_get_real(val), jsonNumberText(val))`. The
  fix at both native sites replaces `std::to_string(yyjson_get_real(x))`
  with `yyjson_val_write(x, 0, nullptr)` to extract the original JSON
  text, matching both the Python fallback and the fhirpath_json UDF
  wrapper (which already used `yyjson_val_write` directly). The bug was
  latent through 935/935 R4 conformance because official fixtures exercise
  `valueQuantity.value` via `fhirpath_json` (not `fhirpath_text`). After
  future FastPath or JsonValueToOwnedString changes, audit for any new
  `std::to_string(yyjson_get_real(...))` patterns and replace with
  `yyjson_val_write`. Probe: `.temp/qa/fp12_explorer_2026_06_29/probe.py`.
