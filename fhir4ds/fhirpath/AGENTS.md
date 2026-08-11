# fhir4ds.fhirpath Notes

## Known Fragile Areas

- **FHIRPath FP-20 SKEPTIC iteration 1 §9 Environment Variables + §10
  Types/Reflection + §11 Type Safety + §12 Formal Specifications
  (2026-06-30):** **1 ISSUE RESOLVED, 1 DEFERRED.** A fresh SKEPTIC
  hypothesis-driven probe with 95+ expressions across 5 probe files
  tested every orchestrator-briefed §9-§12 item at the public DuckDB
  UDF boundary comparing bundled native C++ extension vs forced Python
  fallback through all 5 UDF wrappers + `fhirpath_is_valid`.

  **(QA-001 LOW §9 RESOLVED):** Both native and fallback
  `fhirpath_is_valid` UDFs returned False for syntactically-valid env
  var forms `%'name'` (string form per §9 backward-compat note) and
  `` %`name` `` (backtick form). The is_valid UDFs compiled + evaluated
  the expression against a minimal test resource and returned False on
  ANY runtime exception, conflating the runtime "undefined environment
  variable" error with syntactic invalidity. Per GLOBAL_RULES
  invariant, is_valid validates expression validity, not runtime
  evaluability. Reproducer: `SELECT fhirpath_is_valid(%'us-zip')`
  returned False in both backends; should return True. Also affected
  `%undefined-var` (simple-identifier form of an undefined env var).

  Surgical fix in both backends: (1) Python UDF
  `fhir4ds/fhirpath/duckdb/udf.py:fhirpath_is_valid_udf` gained new
  helper `_is_undefined_environment_variable_error(exc)` that
  substring-matches "Attempting to access an undefined environment
  variable" (handles both raw ValueError and FHIRPathError-wrapped
  forms) plus "Undefined variable:" (C++ mirror); added a new
  `except ValueError as exc:` arm plus a parallel branch in the
  existing `except FHIRPathError` arm. (2) C++ UDF
  `extensions/fhirpath/src/fhirpath_extension.cpp:FhirpathIsValidFunction`
  inner catch block now checks `e.what().rfind("Undefined variable:", 0) == 0`
  and returns true for that case.

  2 pre-existing assertions in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_environment_type_parity.py`
  that hard-coded the OLD incorrect `is_valid('%unknown') == False`
  expectation were updated to spec-correct `== True`. 1 new regression
  test `test_is_valid_accepts_undefined_env_var_forms_fp20_skeptic`
  (12 valid + 1 invalid case) added. Side discovery: C++ lexer accepts
  `%1var` (digit-led) and `%` alone (empty name) as implementation
  extensions where Python parser is stricter — out of FP-20 scope,
  attributed to future §8.6 lexer-permissiveness audit.

  Native C++ extension rebuilt (md5sum
  `d8097c25ea1c01c92e85cf14bf16c7b7`) and copied to both package and
  user install paths. Post-fix: FP-20 probe P3 is_valid matrix 14/14
  spec-correct (was 8/14); FP-20 parity test_environment_type_parity.py
  12/12 pass (was 11/12 + 1 new); FHIRPath duckdb integration 435/435
  pass (was 434, +1 new); full conformance 2822/2822 unchanged. Probe
  artifacts: `/mnt/d/fhir4ds/.temp/qa/fp20_skeptic_2026_06_30/probe{,2,3,4,5}.py`.

  **(QA-002 LOW §3.2/§5.2 DEFERRED — out of FP-20 scope):** Side
  discovery while probing `%resource.descendants().reference`. Choice-
  type prefix-match heuristic at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:2958-2981` and Python
  mirror incorrectly treats `referenceRange` as a choice-type variant
  of `reference` because 'R' is uppercase. Reproducer:
  `%resource.descendants().reference` on a Patient with
  `contained[0].referenceRange` returns `[referenceRange[0]]` instead
  of empty. Both backends have the same bug (parity match). R4
  conformance passes 935/935 because patient-example.xml has no fields
  matching the prefix heuristic. Deferred to a future §3.2 polymorphic
  items / §5.2 navigation chunk.

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



- **FHIRPath FP-19 EXPLORER iter 1 §7 Aggregates (STU) + §8 Lexical
  Elements (2026-06-30):** **1 ISSUE RESOLVED.** A fresh EXPLORER
  pathological-input fuzz pass threw 182 EVAL cases × 2 modes = 364 parity
  cells across 9 vector groups (V1 extreme aggregate depths / V2 nested
  aggregate `$this`/`$index`/`$total` interplay / V3 every Unicode
  whitespace / V4 every literal escape edge / V5 Unicode identifiers /
  V6 pathological comment placements / V7 reserved keyword edges /
  V8 pathological aggregate type coercion / V9 composed
  aggregate+iif+where+select) at the public DuckDB UDF boundary comparing
  bundled native C++ extension vs forced Python fallback through all 5
  UDF wrappers + `fhirpath_is_valid`.

  **(QA-001 MEDIUM §7.1/§8 RESOLVED):** Python fallback raised
  `RecursionError` on expressions with deep syntactic nesting (~250+
  pipes / parens / function calls). Native C++ has no such limit. The
  UDF wrapper row-resiliently swallowed the resulting
  `FHIRPathEvaluationError` as empty/None, silently diverging from
  native. Reproducer (3 forms): `(1 | 2 | ... | 500).aggregate($this +
  $total, 0)` returned `125250` (native) vs `None` (fallback);
  `(((((...((1))...)))))` 250-deep returned `1` (native) vs `None`
  (fallback); `true.not().not()...not()` 250-deep returned `true`
  (native) vs `None` (fallback). Root cause: both the ANTLR-generated
  parser (`fhir4ds/fhirpath/parser/__init__.py:80` `parser.expression()`)
  AND the recursive `do_eval` evaluator
  (`fhir4ds/fhirpath/engine/__init__.py:41-54`) consume ~5-10 Python
  stack frames per AST node; Python's default `recursionlimit=1000` hits
  ceiling around 250 nodes.

  Surgical fix in `fhir4ds/fhirpath/duckdb/udf.py`:
  - New helper `_expression_max_nesting_depth(expression)` counts
    AST-node-introducing tokens (`(`, `[`, `|`, `&`, `,`, `.`) outside
    strings/delimited-identifiers/comments. Mirrors the resource-side
    `_json_max_nesting_depth` pattern.
  - New helper `_eval_with_recursion_budget(func, resource, expression)`
    temporarily raises `sys.recursionlimit` to
    `max(current, expr_depth*10 + json_depth*4 + 1000)`, runs
    `func(resource)`, restores. Thread-safe via existing
    `_RECURSION_LIMIT_LOCK`.
  - Applied at 9 evaluation sites (fhirpath_scalar, fhirpath_predicate,
    fhirpath_is_valid_udf, fhirpath_text_udf, fhirpath_bool_udf,
    fhirpath_number_udf, fhirpath_json_udf via _evaluate_raw_items,
    _evaluate_repeat_expression). Each site wraps BOTH `_get_compiled_evaluator`
    (ANTLR parser) AND `evaluator.evaluate` (recursive do_eval) in the
    budget.

  1 new regression test
  `test_pathological_expression_depth_does_not_silently_return_empty_fp19_explorer`
  in `test_aggregate_lexical_parity.py` (4 assertions). Post-fix: probe
  7→5 diffs (remaining 5 are pre-existing FP-08 deferred negative-zero,
  test-expectation artifacts, UDF serialization-layer divergences — not
  runtime spec bugs); FP-19 parity tests 8/8 pass (was 7/7, +1 new);
  FHIRPath integration 434/434 pass; full conformance 2822/2822
  unchanged.

  **Recurring pattern reinforced (2nd instance for "Python fallback
  recursive algorithm on unbounded user input" bug class — after FP-12
  EXPLORER `_descendant_repeat_key` 2026-06-29):** Any Python helper that
  processes user-supplied FHIR data (resources OR expressions)
  recursively is a candidate for the iterative-algorithm audit or a
  recursion-budget wrapper. The data-driven
  `*_max_nesting_depth` + `*_with_recursion_budget` pattern is the
  generalizable solution. EXPLORER methodology (pathological-input
  fuzzing with extreme-depth vectors) is the only methodology that
  surfaces these defects — systematic spec-walkthrough and hypothesis-
  driven probes systematically miss them.

  Probe artifact: `/mnt/d/fhir4ds/.temp/qa/fp19_explorer_2026_06_30/probe.py`
  (182 EVAL cases × 2 modes = 364 parity cells / 9 vector groups).

- **FHIRPath FP-19 HISTORIAN iter 1 §7 Aggregates (STU) + §8 Lexical
  Elements (2026-06-30):** **VERIFIED CLEAN — 0 non-terminal issues.** A
  fresh HISTORIAN systematic spec-walkthrough enumerated every normative
  rule from FHIRPath v2.0.0 §7.1 (`aggregate(aggregator, [init])`) and
  §8.1-§8.7 (Whitespace, Comments, Literals syntax, Symbols, Keywords,
  Identifiers, Case-Sensitivity) at the public DuckDB UDF boundary
  comparing bundled native C++ extension vs forced Python fallback through
  all 5 UDF wrappers + paired `fhirpath_is_valid` validity checks.
  Independent of prior FP-19 passes — 3rd independent clean-run on the
  §7/§8 surface (SKEPTIC + HISTORIAN 2026-05-24, SKEPTIC 2026-06-30,
  HISTORIAN 2026-06-30).

  **Probe composition**: 175 EVAL cases × 5 wrapper mapping + 175 paired
  validity cases across 33 spec-rule groups. All 9 §7.1 spec examples
  transcribed verbatim (sum / min / avg + 0-based $index + outer-context
  init + $total scope restoration + nested aggregate + Quantity
  accumulator + iif laziness + arity rejection). §8.1 strict whitespace
  (9 cases: NBSP/VT/FF/ZWSP/LineSep/ParaSep all rejected; tab/space/LF/CR
  any number any position accepted). §8.2 comments (12 cases: `//` line,
  `/* */` block, empty block, multi-line, nested-as-single, comment
  markers inside strings and delimited identifiers preserved as literals).
  §8.3 literals (55 cases: empty, Boolean, Integer with INT32 boundaries,
  Decimal with exponential rejection, all 9 string escapes + spec
  TestEscape1-5, Date/DateTime/Time with partial + invalid forms, Quantity
  UCUM + all 8 calendar durations singular/plural). §8.4 symbols (17
  cases: every operator). §8.5 keywords (26 cases: 24 reserved keywords
  correctly require backticks; 4 exceptions `as`/`contains`/`in`/`is`
  work bare). §8.6 identifiers (9 cases: simple + delimited with escape
  sequences). §8.7 case-sensitivity (25 cases: `True`/`AND`/`NOT`/`DIV`/
  `Year`/`DAY` all rejected; lowercase `day`/`year`/etc work; System type
  `Integer` valid while `integer`/`INTEGER` not System types).

  **Result**: **Zero native↔fallback parity diffs across all 175 EVAL
  cases. Zero native↔fallback validity diffs across all 175 paired
  `fhirpath_is_valid` cases.** All 9 §7.1 spec examples produce their
  spec-defined outputs.

  Probe artifact:
  `/mnt/d/fhir4ds/.temp/qa/fp19_historian_2026_06_30/probe.py`
  (175 cases / 33 spec-rule groups). Full FHIRPath integration 433/433
  (no regression). Existing `test_aggregate_lexical_parity.py` 7/7 pass.
  No source changes, no new tests, no native rebuild required.

  **Recurring pattern reinforced** (3rd independent clean-run on FP-19
  §7/§8): when multiple adversarial personalities using different
  methodologies (SKEPTIC hypothesis-driven + HISTORIAN systematic
  spec-walkthrough) each independently produce 0 issues on a surface
  with pre-existing comprehensive native↔fallback parity tests, that is
  the highest-confidence evidence the surface is spec-compliant. Future
  spec-chunk iterations on FP-19 would be low-yield.

- **FHIRPath FP-19 SKEPTIC iter 1 §7 Aggregates + §8 Lexical Elements
  (2026-06-30):** **VERIFIED CLEAN — 0 in-scope non-terminal issues,
  2 out-of-scope side discoveries logged (both already documented in prior
  chunks).** A fresh SKEPTIC hypothesis-driven probe with 100+ FP-19-scope
  expressions across 12 hypothesis groups (H1-H12) tested every
  orchestrator-briefed §7/§8 item at the public DuckDB UDF boundary
  comparing bundled native C++ extension vs forced Python fallback through
  all 5 UDF wrappers + `fhirpath_is_valid`. Independent of prior FP-19
  passes (FP-19 SKEPTIC/HISTORIAN/EXPLORER rerun 2026-05-24). All 10
  SKEPTIC predictions REJECTED: aggregate arity (`aggregate()` / 3+ args
  correctly invalid), `$total` scope restoration, `init` outer-focus
  evaluation, `iif()` lazy evaluation inside aggregator, nested aggregate
  `$total` shadowing, strict whitespace (only `\t`/space/`\n`/`\r` —
  NBSP/vertical-tab/form-feed/thin-space/zero-width/line-sep/para-sep all
  rejected), comment markers inside strings/delimited-identifiers treated
  as literal chars, all 9 spec-defined string escapes work + unknown-escape
  `\\p`→`'p'` per spec, reserved keywords require delimiters (exceptions
  `as`/`contains`/`in`/`is` work bare), case-sensitivity for `True`/`AND`/
  `NOT`/`INTEGER`/`Year`/etc.

  **NOT A BUG Registry (FP-19 SKEPTIC additions):**
  - §8.5 reserved keyword list correctly enforced. `year`/`month`/`day`/
    `hour`/`minute`/`second`/`millisecond` (+ plurals) and `div`/`mod`
    require backtick-delimiting as identifiers; `as`/`contains`/`in`/`is`
    exceptions work bare. All confirmed via 30+ validity-only parity cases.
  - §8.7 case-sensitivity strict. `True`/`False`/`AND`/`OR`/`XOR`/`IMPLIES`/
    `NOT`/`IN`/`CONTAINS`/`IS`/`AS`/`DIV`/`MOD` all rejected; type names
    `Integer` valid, `integer`/`INTEGER` not System type; duration keywords
    `Year`/`YEAR`/`Years` rejected.
  - §8.1 whitespace strict. Vertical-tab (U+000B), form-feed (U+000C),
    NBSP (U+00A0), thin space (U+2009), zero-width space (U+200B), line
    separator (U+2028), paragraph separator (U+2029) all correctly rejected.
  - §8.2 comments correctly tokenized. `//` line, `/* */` block, `/**/`
    empty block, nested-block-as-single (`/*/ still comment */`), comments
    between any two tokens, comments at start/end of expression all
    correct. Comment markers inside strings/delimited identifiers treated
    as literal characters.
  - §8.3 literals: all 9 string escapes (\\' \\" \\` \\r \\n \\t \\f \\\\
    \\uXXXX) work; unknown escape `\\p`→`'p'` per spec ("backslash at
    beginning of non-escape sequence will be ignored"); invalid `\\u005`
    → `'u005'` per spec example TestEscape4. Empty string `''` valid.
  - §7.1 aggregate scope semantics intact: `$total`/`$index`/`$this`
    correctly scoped per iteration; `$total` undefined outside aggregator
    expression (post-aggregate `$total` reference returns empty via
    row-resilient NULL); init expression uses outer invocation focus;
    empty input + init returns init; empty input + no init returns empty.

  **Architecture Drift Log (FP-19 SKEPTIC additions):**
  - **(LOW, deferred, out of FP-19 scope)** 9th documented instance of
    "native C++ uses IEEE-754 binary64 where Decimal arithmetic is required"
    bug class: native Decimal `+`/`-`/`*` rendering produces 17-sig-digit
    binary64 noise when an operand comes from integer division. Family:
    `1 + 2/3` → native `'1.6666666666666665'` vs fallback
    `'1.6666666666666666'`; `2 + 1/3`, `1 - 1/3`, `1/3 + 2/3`,
    `0.5 + 1/3` all show similar 17th-digit noise. Root cause:
    `decimalWithScaleText` at `extensions/fhirpath/src/fhirpath/
    evaluator.cpp:8078-8099` uses fractional-digit count as
    `setprecision`, not sig-digit count, producing 17-sig-digit noise
    when integer part is non-zero. The FP-18 HISTORIAN fix at
    evaluator.cpp:8174 only patched the `/` operator's source_text via
    `normalizeDecimalMathSourceText`; the same shortest-round-trip
    rendering is needed for `+`/`-`/`*` results when an operand's
    source_text already represents a shortest-round-trip Decimal. Same
    fix pattern would close this 9th instance. **Belongs to future §6.6
    math-precision chunk, not §7/§8.**

  Probe artifacts: `/mnt/d/fhir4ds/.temp/qa/fp19_skeptic_2026_06_30/probe.py`
  (100+ cases / 12 hypothesis groups), `probe2.py` (60+ focused FP-19-scope
  cases), plus inline shells (22 whitespace+comment deep edges, 22
  case-sensitivity cases, 8 aggregate scope semantics). Full conformance
  2822/2822 unchanged. No source changes, no new tests, no native rebuild
  required (FP-19 surface spec-compliant; existing
  `test_aggregate_lexical_parity.py` 7/7 pass).

- **FHIRPath FP-18 HISTORIAN iter 1 §6.6 Math Operations + §6.7 Date/Time
  Arithmetic (2026-06-30):** **3 ISSUES RESOLVED, 2 INTENDED.** A fresh
  HISTORIAN systematic spec-walkthrough with 142 expressions across 9
  spec-rule groups enumerated every normative rule from FHIRPath v2.0.0
  §6.6.1-§6.6.7 (Math) and §6.7.1-§6.7.2 (Date/Time Arithmetic) at the
  public DuckDB UDF boundary comparing bundled native C++ extension vs
  forced Python fallback through all 5 UDF wrappers. Independent of
  prior FP-18 SKEPTIC pass — found 3 fresh bugs SKEPTIC had missed.

  **(QA-001 HIGH §6.6.2 RESOLVED):** Native C++ Decimal division `/`
  produced 17-sig-digit binary64 noise via `setprecision(17)` fallback
  because `source_text` was empty for division results. Reproducer:
  `1/3` returned native `'0.33333333333333331'` vs fallback
  `'0.3333333333333333'`. Surgical fix at `evaluator.cpp:8148` added
  dedicated `op == "/"` branch that calls existing
  `normalizeDecimalMathSourceText(result)` helper (FP-11 HISTORIAN
  pattern) to populate `source_text` with shortest-round-trip rendering.
  8th documented instance of the "native C++ uses IEEE-754 binary64
  where Decimal arithmetic is required" bug class.

  **(QA-002 HIGH §6.6 RESOLVED):** Python fallback silently coerced
  Boolean→1/0 for `*`, `/`, `div`, `mod` operators (16 cases). Native
  correctly returned empty per §6.6 (row-resilience wrapper). The
  `+`/`-` paths already raised FHIRPathError via fallthrough; `mul` was
  missing the `is_number` guard entirely, and `div`/`intdiv`/`mod` had
  no type check at all. Root cause: Python's `isinstance(True, int) ==
  True`. Surgical fix at `engine/invocations/math.py`: added explicit
  type guards to all 4 functions raising FHIRPathError when neither
  operand is a Number (per `util.is_number` which excludes bool) nor
  a Quantity. Spec: §6.6 + §5.5 conversion table (Boolean→Integer/
  Decimal is Explicit only).

  **(QA-003 MEDIUM §6.6.2 RESOLVED):** Both backends returned Integer
  form for division results that happened to be whole numbers (e.g.
  `1.5 'g' / 0.5` returned `"3 'g'"`). Per §6.6.2 "The result of a
  division is always Decimal, even if the inputs are both Integer"
  the result must be Decimal `"3.0 'g'"`. Surgical fix in both
  backends: native `evaluator.cpp` forces `preserve_decimal_point=true`
  for all 4 division paths (Quantity/Quantity same+diff unit,
  Quantity/scalar, scalar/Quantity); fallback `engine/invocations/
  math.py:div` + `engine/nodes.py:FP_Quantity.__truediv__` +
  `__rtruediv__` wrap whole-number Decimal results with
  `.quantize(Decimal("0.1"))`. 2 pre-existing test expectations
  updated to spec-correct Decimal form.

  **(QA-004 LOW §6.7.1 INTENDED):** DateTime Z vs +00:00 — carry-over
  re-confirmation from FP-18 SKEPTIC QA-005 INTENDED. Per §4.1.7 both
  forms are spec-equivalent UTC offset synonyms.

  **(QA-005 LOW §6.7.2 INTENDED):** DateTime - DateTime returns empty
  in BOTH backends. v2.0.0 §6.7.2 only specifies Date/DateTime/Time -
  Quantity. DateTime-DateTime subtraction producing a Quantity duration
  is a v3.0.0 addition (confirmed via FHIRPath build spec). Both
  backends spec-correct for v2.0.0.

  Native C++ extension rebuilt and copied to both package and user
  install paths (md5sum `36adce8398991bdb851b9121a9588ba0`). 23 new
  regression tests added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py`:
  `test_division_uses_shortest_roundtrip_text_fp18_historian` (7 cases),
  `test_division_result_is_always_decimal_fp18_historian` (6 cases),
  `test_boolean_operands_rejected_by_arithmetic_ops_fp18_historian`
  (10 cases). Post-fix: HISTORIAN probe 142 cases parity diffs 14 → 3
  (remaining 3 are spec-equivalent Z/+00:00 + 2 inherent Decimal-vs-
  binary64 precision differences documented as architect drift);
  FHIRPath integration 433/433 (was 410, +23 new tests); full
  conformance 2822/2822 unchanged. Probes:
  `/mnt/d/fhir4ds/.temp/qa/fp18_historian_2026_06_30/probe.py` (142
  cases / 9 spec-rule groups), `division_drift.py` (14 cases),
  `bool_coercion.py` (20 cases).

  **NOT A BUG Registry (FP-18 HISTORIAN additions):**
  - DateTime Z offset preservation vs +00:00 normalization: per §4.1.7
    both are spec-equivalent UTC offset synonyms (carry-over from
    FP-18 SKEPTIC).
  - DateTime-DateTime subtraction returning empty: v2.0.0 §6.7.2 scope
    limit. DateTime-DateTime→Quantity is a v3.0.0 addition.
  - `0.3/0.1` and `0.1/3` Decimal-vs-binary64 precision differences:
    fallback uses Python Decimal (28-digit precision); native uses
    IEEE-754 binary64 shortest-round-trip. Inherent limitation
    documented as architect drift; would require GMP or Python Decimal
    port to C++.

  **Architecture Drift Log (FP-18 HISTORIAN additions):**
  - The "native C++ uses IEEE-754 binary64 where Decimal arithmetic is
    required" pattern is now in its **8th documented instance** (FP-07
    toDecimal, FP-08 convertQuantityUnit, FP-11 SKEPTIC Quantity +/-/*,
    FP-11 HISTORIAN ln/exp/sqrt/log, FP-11 EXPLORER power/formatDecimal/
    rround, FP-14 EXPLORER Decimal +/-, FP-18 SKEPTIC Integer*Integer
    overflow, FP-18 HISTORIAN Decimal division). Division was deferred
    in the FP-14 EXPLORER comment at evaluator.cpp:8039 ("division
    always routes through binary64 because exact Decimal division is
    much more complex") — FP-18 HISTORIAN confirmed the binary64 result
    is the same IEEE 754 nearest-double as Python's
    `float.__truediv__`, so re-rendering via shortest-round-trip
    produces spec-compliant text WITHOUT needing arbitrary-precision
    Decimal division. Future native Decimal-producing paths should
    always populate `source_text` via `normalizeDecimalMathSourceText`.

- **FHIRPath FP-18 SKEPTIC iter 1 §6.6 Math Operations + §6.7 Date/Time
  Arithmetic (2026-06-30):** **4 ISSUES RESOLVED, 1 INTENDED.** A fresh
  SKEPTIC hypothesis-driven probe with 135 expressions across 8 hypothesis
  groups (H1-H8) + 15 deep-dive groups + 6 spec-anchor groups tested
  every orchestrator-briefed §6.6/§6.7 bug class at the public DuckDB UDF
  boundary comparing bundled native C++ extension vs forced Python
  fallback through all 5 UDF wrappers.

  **(QA-001 HIGH §4.1.4 RESOLVED):** Native C++ Integer*Integer
  overflow-to-Decimal at `extensions/fhirpath/src/fhirpath/evaluator.cpp`
  promoted to Decimal without source_text when the product exceeded
  INT32_MAX, falling through to `setprecision(17)` scientific notation
  in toString(). Reproducer: `2000000000 * 2000000000` returned native
  `'4e+18'` (scientific, 1 sig digit) vs fallback
  `'4000000000000000000.0'` (exact). Surgical fix routed Integer*Integer
  overflow through `tryIntegerArithmeticText` for exact magnitude via
  schoolbook multiplication on string digits. Same binary64-drift bug
  class as FP-14 EXPLORER QA-001 (Decimal +/-).

  **(QA-002 MEDIUM §4.1.4 RESOLVED):** Native Decimal*Decimal collapsed
  trailing-zero precision. `decimalWithScaleText` lambda at evaluator.cpp
  stripped trailing zeros past `dot + 2` via
  `while (text.size() > dot + 2 && text.back() == '0')`. Python's Decimal
  `__mul__` preserves operand scale. Reproducer: `2.5 * 4.0` returned
  native `'10.0'` vs fallback `'10.00'`. Surgical fix removed the
  trailing-zero strip AND extended `tryIntegerArithmeticText` to track
  operand fractional digit counts and produce scale-aware output
  (sum for `*`, max for `+`/`-`).

  **(QA-003 HIGH §4.1.8 / FP-11 SKEPTIC regression RESOLVED):** Native
  Quantity*scalar with `apply_integral_normalize=false` dropped the
  required `.0` decimal point for integer-valued products.
  `normalizeQuantityArithmeticSourceText` at evaluator.cpp:2289-2296
  fell through to `formatDecimalNumber` which returned source_text
  directly (e.g. `'5'` not `'5.0'`). FP-11 SKEPTIC comment at line
  7880-7883 documented the intent to preserve the `1.0` rendering for
  integer-valued products mirroring Python's `__mul__`, but the
  implementation didn't match. Reproducer: `5.0 'g' * 3` returned
  native `'15 \'g\''` vs fallback `'15.0 \'g\''`. Surgical fix added
  `preserve_decimal_point` parameter that appends `.0` when the
  Quantity operand's source_text contains a decimal point. Also
  propagated source_text through unary minus on Quantity.

  **(QA-004 LOW §5.5.8 RESOLVED):** Native fhirpath_json Quantity
  serialization used `%.15g` which produces scientific notation for
  tiny/large doubles. Python's fallback uses orjson.dumps with different
  thresholds (decimal for `1e-5 <= |v| < 1e16`, scientific otherwise)
  and `e-N` format. Reproducer: `3 'cm' * 12 'cm2'` returned native
  fhirpath_json `'[{"value":3.6e-05,"unit":"m.m2"}]'` vs fallback
  `'[{"value":0.000036,"unit":"m.m2"}]'`. Surgical fix added scientific-
  to-decimal conversion within orjson's range and normalized
  exponent format.

  **(QA-005 LOW §4.1.7 INTENDED):** Native DateTime arithmetic
  preserves input Z literal form; fallback normalizes to `+00:00`.
  `@2024-01-15T10:30:00Z + 60 minutes` returns native
  `'2024-01-15T11:30:00Z'` vs fallback
  `'2024-01-15T11:30:00+00:00'`. Per §4.1.7 "Z is allowed as a synonym
  for the zero (+00:00) UTC offset" — both forms are spec-equivalent.
  Classified INTENDED; native preserving input literal form is
  reasonable.

  Native C++ extension rebuilt and copied to both package and user
  install paths. 18 new regression tests added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_arithmetic_parity.py`:
  `test_multiplication_precision_preservation_fp18_skeptic` (15 cases)
  and `test_decimal_arithmetic_preserves_scale_fp18_skeptic` (3 cases).
  Post-fix: SKEPTIC probe round 1 + round 3 0 diffs; round 2 1 diff
  (QA-005 spec-equivalent); FHIRPath pytest 397/397 (was 379, +18 new
  tests); full conformance 2822/2822 unchanged. Probe artifacts:
  `/mnt/d/fhir4ds/.temp/qa/fp18_skeptic_2026_06_30/probe{,2,3}.py`.

  **NOT A BUG Registry (FP-18 SKEPTIC additions):**
  - DateTime Z offset preservation vs +00:00 normalization: per §4.1.7
    both are spec-equivalent UTC offset synonyms. Native preserves
    input literal; fallback normalizes. Reasonable divergence.
  - §6.5 Boolean logic on multi-item operands, type-mismatched operands,
    and incompatible UCUM dimensions correctly produce empty/error in
    both backends.

  **Architecture Drift Log (FP-18 SKEPTIC additions):**
  - (LOW, deferred) The Decimal scale preservation in
    `tryIntegerArithmeticText` currently only handles operands with
    all-zero fractional parts. For operands with non-zero fractional
    parts (e.g. `1.5 * 1.5 = 2.25`), the code defers to binary64
    arithmetic, which can still produce precision drift on very large
    or very small magnitudes. This is a known limitation of the
    text-arithmetic approach; full Decimal arithmetic would require
    porting Python's Decimal module or using GMP.

- **FHIRPath FP-17 EXPLORER iter 1 §6.5 Boolean Logic pathological-input
  fuzz (2026-06-30):** **VERIFIED CLEAN.** A fresh EXPLORER fuzz pass
  with 215 expressions across 3 rounds (109 + 61 + 45 validity + 6
  engine-level evals) tested every orchestrator-briefed §6.5 bug class
  at the public DuckDB UDF boundary comparing bundled native C++
  extension vs forced Python fallback through all 5 UDF wrappers
  (fhirpath/fhirpath_text/fhirpath_json/fhirpath_bool/fhirpath_number).
  Coverage: V1 extreme Boolean chains (5-deep and, 4-deep or, 10-deep
  and, 50-deep and, 50-deep or, 20-deep xor), V2 deeply nested implies
  chains (5-deep right-nested, 10-deep and 30-deep both left-recursive
  and right-nested parenthesized forms), V3 polymorphic choice-types
  (Observation.valueString/valueInteger/valueQuantity/valueDecimal/
  valueBoolean incl `valueInteger = 1 and valueInteger = 2` form), V4
  malformed expressions (14 cases — `and true`, `true and`, `or true`,
  `implies true`, `true implies`, `not true`, `not()`, `true.not(true)`,
  `active and and active` double-and, `(true and` unbalanced paren),
  V5 Unicode string truthy operands (Latin/CJK/emoji literals, 1000-char
  ASCII, 6-emoji, NUL-byte, `note.text` multi-byte field), V6
  multi-element collection operands (3-element `arr` Boolean field,
  2-element `name` collection, 3-element `name.family`, 2-element
  `identifier.value`, 3-element `name.use`), V7 composed with
  where/select/iif/exists/allTrue/anyTrue/$this, V8 ResourceNode unwrap
  (Patient.active, Patient.deceasedBoolean, primitive-extension
  shadowed `_active.extension.valueBoolean`), V9 empty propagation
  through long chains (14 variants × 5 operators incl missing-path),
  V10 operator precedence fuzz per §6.8 (#11 and < #12 xor/or < #13
  implies), V11 type-mismatched operands (Integer/Decimal/String/Date/
  Time/DateTime/Quantity truthy per §4.5), V12 Quantity/DateTime
  operands. Round 3 added a 45-case `fhirpath_is_valid` parity matrix
  (100% native↔fallback agreement) and 6 engine-level multi-item error
  verifications. **Zero native↔fallback parity diffs across all 215
  cases × 5 UDF wrappers.** All 5 "native spec mismatches" in the
  validity probe are expected spec-decision behaviors (already
  documented by prior FP-17 SKEPTIC + HISTORIAN runs): `not` is NOT in
  §8.5 reserved keywords table (only `and`/`or`/`xor`/`implies` are
  reserved), so `not()` empty parens and `true.not` (no parens) parse
  as valid grammar; `true.not(true)` is grammar-valid with runtime
  arity error; `TRUE`/`FALSE` uppercase parse as valid identifiers
  (case-sensitive grammar). Multi-item resource operands verified via
  direct engine evaluation (`fhir4ds.fhirpath.evaluate()`) to throw
  `FHIRPathError` at the engine level, proving the wrapper's "empty"
  return is the documented row-resilience pattern. **0 non-terminal
  CRITICAL/HIGH/MEDIUM issues.** Existing `test_boolean_logic_parity.py`
  53/53 pass; FHIRPath duckdb pytest unchanged; full conformance
  2822/2822 unchanged. No source changes, no new regression tests, no
  native rebuild. Recurring pattern reinforced (3rd instance for §6.5,
  1st EXPLORER on §6.5): when all 3 adversarial personalities (SKEPTIC
  hypothesis-driven, HISTORIAN systematic spec-walkthrough, EXPLORER
  pathological-input fuzz) each independently produce 0 issues on a
  surface with pre-existing comprehensive native↔fallback parity tests
  (6 named tests / 53 parametrized cases), that is the highest-
  confidence evidence the surface is spec-compliant.

- **FHIRPath FP-17 HISTORIAN iter 1 (run 2) §6.5 Boolean Logic systematic
  spec-walkthrough (2026-06-30):** **VERIFIED CLEAN.** A fresh HISTORIAN
  systematic spec-walkthrough independently confirming the prior FP-17
  SKEPTIC clean run. 146 cases across 3 fresh probe files in
  `/mnt/d/fhir4ds/.temp/qa/fp17_historian_iter1_run2_2026_06_30/`:
  (1) `probe.py` (40 cells) — literal §6.5.1-§6.5.5 truth tables
  transcribed cell-by-cell from the FHIRPath v2.0.0 spec text, including
  the absorbing rows (§6.5.1 false∧X=false, §6.5.2 true∨X=true, §6.5.5
  false→X=true) and all empty-propagation cells; (2) `probe2.py` (66
  cases / 8 normative groups) — short-circuit-absorbing rows with
  multi-item X operands per §6.5 paragraph 2, §4.5 singleton non-Boolean
  truthiness, §4.5 last-branch multi-item resource operand row-resilient
  error, §5.2.1 `not()` argument rejection, §6.8 operator precedence
  chains, ResourceNode unwrap on Patient.active, polymorphic choice-type
  Observation.valueString, composed where+iif+exists+implies usage;
  (3) `probe3.py` (37 cases + 10 engine-level) — §6.5.5 spec anchor
  example adapted to 3 fixtures, 27-case `fhirpath_is_valid` parity
  matrix (100% native↔fallback agreement), 10-case engine-level
  evaluation confirming runtime multi-item operands return `[]`
  consistently. **Zero native↔fallback parity diffs across all 146
  cases.** All 13 "value diffs" traced to incorrect test expectations
  in the probe (the engine's strict-evaluation interpretation of
  multi-item runtime operands is documented in the existing regression
  test `test_multi_item_boolean_operands_return_empty_in_native_and_fallback`;
  the bare `not(deceasedBoolean)` form is not in the FHIRPath grammar —
  canonical form is `deceasedBoolean.not()`; `not`/`not()` parse as
  valid grammar because `not` is NOT in §8.5 reserved keywords table —
  only `and`/`or`/`xor`/`implies` are reserved). **0 non-terminal
  CRITICAL/HIGH/MEDIUM issues.** Existing `test_boolean_logic_parity.py`
  53/53 pass; FHIRPath duckdb pytest 1329/1329 pass; full conformance
  2822/2822 unchanged. No source changes, no new regression tests, no
  native rebuild. Recurring pattern reinforced (2nd instance for §6.5,
  1st HISTORIAN on §6.5): when HISTORIAN produces 0 issues on a surface
  with pre-existing comprehensive native↔fallback parity tests (53
  cases) AND a prior SKEPTIC fresh-run also produced 0 issues, that is
  high-confidence evidence the surface is spec-compliant.

- **FHIRPath FP-17 SKEPTIC iter 1 §6.5 Boolean Logic hypothesis-driven
  probe (2026-06-30):** **VERIFIED CLEAN.** A fresh SKEPTIC hypothesis-
  driven probe with 104 expressions across 9 hypothesis groups (74 cases
  in round 1 + 30 deeper-edge cases in round 2 + 7 direct-engine multi-
  item error verifications + 20 `fhirpath_is_valid` parity checks in
  round 3) tested every orchestrator-briefed §6.5 bug class at the
  public DuckDB UDF boundary comparing bundled native C++ extension vs
  forced Python fallback through all 5 UDF wrappers
  (fhirpath/fhirpath_text/fhirpath_json/fhirpath_bool/fhirpath_number).
  Coverage: H1 `and` 9-cell three-valued truth table (true/false/empty
  × true/false/empty — including absorbing false∧X=false cells), H2
  `or` 9-cell table (including absorbing true∨X=true cells), H3
  `implies` 9-cell table — the most error-prone operator, covering
  false→X=true absorbing, empty→true=true, empty→false=empty,
  empty→empty=empty, true→empty=empty, H4 `not()` semantics (empty→
  empty, true→false, false→true, non-bool singleton truthy per §4.5,
  multi-item raises), H5 `xor` 9-cell symmetric-difference table,
  H6 singleton evaluation of non-Boolean operands (Integer/Decimal/
  String/Quantity/Date treated truthy; multi-item raises per §4.5
  last branch), H7 native↔fallback parity across all 5 UDF wrappers,
  H8 ResourceNode unwrap on FHIR Boolean primitive (`Patient.active`),
  H9 short-circuit note (§6.5 paragraph 2: "must not change semantics
  with SC"). Round 2 added Quantity/Date operands, operator precedence
  (#11 and < #12 xor/or < #13 implies per §6.8), type-mismatched
  operands (Integer/String truthy), Unicode/emoji string truthy,
  polymorphic choice-types (Observation.valueString), empty propagation
  through nested chains, `iif()` with empty criterion (§5.5.1),
  `allTrue()`/`anyTrue()` empty-collection semantics (§5.1.4/§5.1.5).
  Round 3 confirmed via direct Python engine evaluation (bypassing
  UDF row-resilience catch) that 7 multi-item operand cases really
  throw `FHIRPathError` at the engine level — proving the wrapper's
  "empty" return is the documented row-resilience pattern, not a
  silent-fallback defect. **0 non-terminal CRITICAL/HIGH/MEDIUM
  issues.** All 9 pre-test SKEPTIC hypotheses empirically REJECTED.
  Cumulative 104 cases × 5 UDF wrappers ≈ 520+ parity cells, all
  matching between native C++ and Python fallback. The §6.5 surface
  has pre-existing comprehensive coverage in 6 named tests in
  `test_boolean_logic_parity.py` (53 parametrized cases including
  truth tables, multi-item rejection, singleton precedence, short-
  circuit parity, `not()` argument rejection). No source changes, no
  new regression tests, no native rebuild. Full conformance 2822/2822
  unchanged (ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47). Probes:
  `/mnt/d/fhir4ds/.temp/qa/fp17_skeptic_2026_06_29/probe.py` (74 cases /
  9 groups), `probe2.py` (30 cases / 13 vector groups),
  `probe3.py` (7 engine-level errors + 20 validity checks).

- **FHIRPath FP-16 HISTORIAN iter 1 §6.4 Collections systematic
  spec-walkthrough (2026-06-29):** **VERIFIED CLEAN.** A fresh
  HISTORIAN systematic spec-walkthrough enumerated every normative
  rule from FHIRPath v2.0.0 §6.4.1 (`|`/`union()`), §6.4.2 (`in`
  membership), §6.4.3 (`contains` containership) at the public DuckDB
  UDF boundary comparing bundled native C++ extension vs forced
  Python fallback through all 5 UDF wrappers. 209 distinct cases ×
  5 wrappers = ~700+ parity cells across 9+ spec-rule groups.
  Coverage: §6.4.1 union dedup semantics (15 cases — Integer≡Decimal,
  UCUM commensurable `1 'g' | 1000 'mg'` count 1, Date≠DateTime,
  Time precision-mergeable, Boolean≠Integer, negative-zero, Decimal
  arithmetic equality intact, Unicode/emoji/NUL byte byte-for-byte
  dedup), §6.4.1 union form parity (`a.union(b)` ≡ `a | b`),
  §6.4.1 ResourceNode unwrap, §6.4.1 nested/chained unions, §6.4.2
  in basics (18 cases), §6.4.2 in empty propagation (LHS empty→empty,
  RHS empty→false, missing-path variants), §6.4.2 singleton LHS
  enforcement, §6.4.3 contains basics (18 cases mirroring in),
  §6.4.3 contains empty propagation (RHS empty→empty, LHS empty→false),
  §6.4.3 singleton RHS enforcement, converse property `(a in b) =
  (b contains a)` exhaustive verification (9 cases), Quantity edge
  cases (FP-13 cross-unit temperature carry-over verified intact:
  `0 'Cel' in (32 '[degF]' | 100 '[degF]')` returns false in both
  backends because equality returns empty per offset-temperature
  guard, and "empty equality" means "not a member" per §6.4.2),
  composed usage (where+iif+select), deep resource traversal,
  type-strict membership (Integer vs String returns false not
  coercion), polymorphic choice-types, object identity, pathological
  inputs (Unicode/emoji/1000-element collections/nested unions/NUL
  bytes). Separate 25-pair `fhirpath_is_valid` parity probe showed
  100% agreement on malformed-expression rejection (including
  statically-known multi-item LHS/RHS for `in`/`contains` which both
  backends reject as invalid). 15 spec-anchor value verifications
  proved every documented spec example produces its spec-defined
  output. 11 singleton-validity probes confirmed static rejection
  parity. 9×5=45 evaluation singleton probes confirmed row-resilient
  error parity for runtime-multi-item resource paths. **0 non-terminal
  CRITICAL/HIGH/MEDIUM issues.** Independently confirms the prior
  FP-16 SKEPTIC fresh-run CLEAN exit. The §6.4 surface is spec-
  compliant across all 5 public DuckDB UDF wrappers in both the
  native C++ extension and forced Python fallback paths. No source
  changes, no new regression tests (surface already has comprehensive
  coverage in 11 named tests in `test_collection_operator_parity.py`
  covering 100+ parametrized cases), no native rebuild. Full
  conformance 2822/2822 unchanged (ViewDefinition 134/134, FHIRPath
  935/935, CQL 1706/1706, DQM 47/47). Probes:
  `/mnt/d/fhir4ds/.temp/qa/fp16_historian_2026_06_29/probe.py`
  (79 cases / 9 groups), `probe2.py` (57 cases / 11 groups deep
  edges), `probe3.py` (30 eval + 30 validity), `probe_spec.py`
  (15 spec anchors + 25 validity pairs), `probe_singleton.py`
  (11 validity singleton + 9×5=45 eval singleton cells).

- **FHIRPath FP-15 EXPLORER iter 1 §6.3 Types pathological-input
  parity (2026-06-29):** **2 ISSUES RESOLVED, 1 INTENDED, 1 DEFERRED,
  1 INTENDED.** A fresh EXPLORER pathological-input fuzz pass threw
  648 expressions across 12 vector groups (V1 polymorphic choice-type
  chains, V2 deeply nested is/as, V3 malformed type specifiers,
  V4 Unicode type names, V5 composed with where/select, V6 polymorphic
  dispatch on every FHIR R4 resource type, V7 choice primitives,
  V8 ResourceNode unwrap, V9 multi-element, V10 empty/singleton,
  V11 case-sensitivity, V12 primitive permutations) at the public
  DuckDB UDF boundary comparing bundled native C++ extension vs forced
  Python fallback through all 5 UDF wrappers.

  **(QA-001 HIGH §6.3.1 / FHIR R4 resource hierarchy RESOLVED):**
  Python fallback `Account is Resource`, `Account is DomainResource`,
  and the same for ~125 of 148 concrete FHIR R4 resource types
  incorrectly returned `false` while native correctly returned `true`.
  Root cause: `fhir4ds/fhirpath/duckdb/fhir_model.py:build_fhir_model()`
  constructed `model["type2Parent"]` using only the generated
  `TYPE_HIERARCHY` from `fhir_types_generated.py` (57 entries from a
  hand-curated ~22-resource subset in `scripts/build_fhir_types.py`).
  The complete canonical R4 hierarchy in
  `fhir4ds/fhirpath/models/r4/type2Parent.json` (209 entries) was
  loaded into `TypeInfo.FHIR_TYPE_HIERARCHY` at `engine/nodes.py:1689`
  but was NOT propagated into the ctx.model passed to `is_fn`. When
  `is_fn` called `TypeInfo.from_value(val).is_(type_info, model=ctx_model)`,
  it preferred the incomplete 4-key ctx model. `Patient`/`Observation`/
  `Bundle` happened to work because they were in the hand-curated
  subset. Surgical fix at `fhir_model.py`: added module-level constant
  `_CANONICAL_R4_TYPE_PARENT = _engine_load_json("type2Parent.json")`
  and merged it UNDER the generated hierarchy in `build_fhir_model`:

  ```python
  model["type2Parent"] = {
      **_CANONICAL_R4_TYPE_PARENT,    # 209 entries (canonical R4)
      **TYPE_HIERARCHY,                # 57 entries (generated)
      **_FHIRPATH_PRIMITIVE_PARENTS,   # uri -> string
  }
  ```

  1 new regression test (592 assertions covering all 148 FHIR R4
  resources × 4 is-checks) added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py::
  test_full_fhir_r4_resource_hierarchy_is_resource_domainresource_fp15_explorer`.

  **(QA-002 HIGH §6.3.1 / FHIR R4 Observation.value[x] INTENDED):**
  `valueBase64Binary` access on Observation returns `[]` in fallback
  vs `['aGVsbG8=']` in native. Reclassified INTENDED after verifying
  https://hl7.org/fhir/R4/observation-definitions.html#Observation.value_x_:
  the FHIR R4 `Observation.value[x]` choice list is exactly
  (Quantity, CodeableConcept, string, boolean, integer, Range, Ratio,
  SampledData, time, dateTime, Period). `base64Binary` is NOT in R4
  (added in R5). `choiceTypePaths.json` correctly excludes it; native
  C++ `infer_fhir_type()` heuristic at `evaluator.cpp:2811-2831`
  over-accepts based on suffix. Python fallback is spec-correct.
  Same NOT-A-BUG pattern documented in FP-08 HISTORIAN archive for
  `Observation.valueDecimal`.

  **(QA-003 MEDIUM §6.3.1 / Identifier.value RESOLVED):** Python
  fallback `Patient.identifier.first().value is FHIR.string` returned
  `['false']` while native returned `['true']`. Root cause:
  `fhir4ds/fhirpath/duckdb/udf.py:_resolve_trailing_choice_type_assertion`
  wraps the engine to handle cases where fhirpathpy loses FHIR choice
  field names. Its broad `_TRAILING_CHOICE_ASSERTION_INFIX_RE` regex
  matched any `.value is X` form, treating `Identifier.value` (plain
  FHIR string field) as if it were `Observation.value[x]` (choice).
  The lookup `_get_choice_type_lookup().get("value")` returns a flat
  global list of all valueX choice field names. For an Identifier
  parent, none of those exist; the function reached
  `if not concrete_values: return [False]` which overrode the engine's
  correct `[True]`. Surgical fix: when `concrete_values` is empty
  (no choice-type field populated), return `None` to defer to the
  engine. 2 new regression tests added:
  `test_identifier_value_non_choice_field_fp15_explorer` (5 cases) and
  `test_choice_type_assertion_unchanged_for_populated_choice_field_fp15_explorer`
  (5 cases, regression guard).

  **(QA-004 LOW §6.3 INTENDED):** `(Patient as Patient is Patient)`
  parses differently in native (empty) vs fallback (true). Spec grammar
  makes `is`/`as` non-associative at the same precedence level; chained
  is/as without parentheses is ambiguous. Both backends defensible.

  **(QA-005 LOW carry-over):** `Bundle.entry.first() is BackboneElement`
  returns true in native vs false in fallback. Same metadata-completeness
  gap as FP-15 SKEPTIC QA-003 (DEFERRED). Not re-attributed.

  Post-fix: 648-case EXPLORER probe 3 diffs (all defensible); FHIRPath
  pytest 1507/1507 (was 1501, +6 from 3 new tests); full conformance
  2822/2822 unchanged. No native C++ rebuild required (all fixes are
  Python-fallback-only). Probe artifact:
  `/mnt/d/fhir4ds/.temp/qa/fp15_explorer_2026_06_29/probe.py` (648
  cases / 12 vectors), `analyze.py` (V6 categorization),
  `diag_v7_v8.py` (root-cause isolation), `focused.py`.

  **NOT A BUG Registry (FP-15 EXPLORER additions):**
  - FHIR R4 `Observation.value[x]` choice type list does NOT include
    `base64Binary` or `Attachment` (R5 additions). Native C++
    `infer_fhir_type()` heuristic is over-permissive on invalid R4
    data. Python fallback strict behavior is spec-correct.
  - FHIRPath §6.3 grammar is ambiguous on chained `is`/`as` without
    parentheses. Both backends implement a defensible parse.
  - Malformed type specifiers (`is 123`, `is true`, `is 'Patient'`,
    `is @2024`, `is FHIR`, `is FHIR.`, `is FHIR..Patient`, `is .Patient`,
    `is FHIR.Patient.Extra`, etc.) are correctly rejected by both
    backends (29 cases).
  - Unicode type names (`is `PatientÀ``, `is `PatientΣ``, `is `Patient中``,
    `is `Patient😀``) correctly produce invalid in both backends (9 cases).
  - Case-sensitivity rules consistent: `Patient is Boolean` returns
    false (System type), `Patient is FHIR.Boolean` returns false
    (Capitalized = System namespace), `Patient is FHIR.boolean` would
    match if Patient had a boolean field (17 cases).

  **Architecture Drift Log (FP-15 EXPLORER additions):**
  - **(LOW, deferred)** `scripts/build_fhir_types.py:FHIR_RESOURCES`
    contains a hand-curated ~22-resource subset. The generated
    `fhir_types_generated.py:TYPE_HIERARCHY` therefore has only 57
    entries. The build script should be regenerated from FHIR R4
    StructureDefinitions to bring it in sync with the canonical
    `models/r4/type2Parent.json` (209 entries). Until then, the
    layered-merge workaround in `fhir_model.py:build_fhir_model` is
    required.

- **FHIRPath FP-15 HISTORIAN iter 1 §6.3 Types systematic spec-walkthrough
  (2026-06-29):** **3 ISSUES RESOLVED, 1 INTENDED, 1 DEFERRED.** A fresh
  HISTORIAN systematic spec-walkthrough probe with 334 cases across all 4
  §6.3 forms (`is TypeSpecifier`, `is(type)`, `as TypeSpecifier`,
  `as(type)`) compared bundled native C++ extension vs forced Python
  fallback through all 5 public DuckDB UDF wrappers. Coverage: System
  types (8), FHIR resources (14), FHIR primitives (15), choice-type
  fields (value[x] for Quantity/String/Boolean/Integer/Decimal/DateTime),
  profile subtypes (Age/Distance/Duration/Count/Money/SimpleQuantity),
  subtype matching (Patient→Resource, Observation→DomainResource, Any),
  unknown type specifiers, multi-item input errors, empty input
  propagation, composed usage (`ofType`+`is`, spec canonical examples),
  form parity (`is X` vs `is(X)`).

  **(QA-001 HIGH §6.3.1 / FHIR R4 primitive hierarchy RESOLVED):**
  Native C++ `Patient.birthDate is FHIR.string` returned `[true]` while
  the Python fallback returned `[false]`. Per FHIR R4
  (https://hl7.org/fhir/R4/datatypes.html) all primitive datatypes
  (date, dateTime, time, instant, boolean, integer, decimal, string)
  inherit DIRECTLY from Element, NOT from each other. `date` is NOT a
  subtype of `string`. Native C++ at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:8775-8794`
  (specifically line 8793 `return {FPValue::FromBoolean(true)};` in the
  non-exact `target == "string"` branch) treated ANY JSON-string-encoded
  FHIR primitive as a subtype of `string`. The valid string-subtypes
  (`id`/`code`/`uri`/`url`/`canonical`/`oid`/`uuid`/`markdown`) are
  already in the `fhirTypeIsA` table at line 1051-1061. Surgical fix at
  evaluator.cpp:8775-8819 replaced the unconditional true with logic
  that consults `fhirFieldType(val.field_name)` (or `fhir_type` for
  choice-type resolution) and only returns true if the field type IS
  `string` or `fhirTypeIsA(actual_type, "string")`. Preserves legacy
  behavior for synthetic inputs without FHIR metadata. 1 regression
  test (10 cases) added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py::
  test_fhir_primitive_string_subtype_hierarchy_fp15_historian`.

  **(QA-002 MEDIUM §6.3.1 empty-input propagation RESOLVED):** Forced
  Python fallback `Observation.value is Quantity` against a resource
  missing `value` returned `[false]`; native correctly returned empty.
  Per §6.3.1 normative text: "In all other cases this operator returns
  the empty collection." Empty input collection is "all other cases" →
  must return empty. The Python engine `is_fn` correctly returned `[]`
  for empty input, but the UDF wrapper at
  `fhir4ds/fhirpath/duckdb/udf.py:_resolve_choice_type_assertion`
  (lines 1545-1562) overrode the engine's correct empty result with
  `[False]` when no choice-type field was populated. Surgical fix at
  udf.py:1540-1580 added an `has_any_choice_value` early-return guard
  before both `is` loops: when no choice-type field has a non-None
  value, returns `[]` to propagate empty per §6.3.1. 1 regression test
  (12 cases) added to
  `test_type_parity.py::test_choice_value_empty_input_is_returns_empty_fp15_historian`.

  **(QA-003 LOW §6.3.1 / FHIR R4 SimpleQuantity RESOLVED):** Native C++
  rejected `SimpleQuantity` as a type specifier (`fhirpath_is_valid=False`);
  fallback accepted it (`[False]`). `SimpleQuantity` is a valid FHIR R4
  profile on Quantity. Root cause: missing from the C++ `fhirTypeIsA`
  hierarchy table. Surgical fix at evaluator.cpp:1028-1032 added
  `{"SimpleQuantity", "Quantity"}` to the hierarchy map.
  `isKnownFHIRType` now resolves SimpleQuantity via
  SimpleQuantity→Quantity→Element. 1 regression test (6 cases) added to
  `test_type_parity.py::test_simplequantity_type_specifier_valid_in_native_fp15_historian`.
  Already flagged as a "side discovery" in the FP-15 SKEPTIC archive;
  formally logged and resolved here.

  **(QA-004 LOW §6.3.1 / §4.1.8 INTENDED):** Carry-over from FP-15
  SKEPTIC QA-002. `(5 'mg') is FHIR.Quantity` returns true native vs
  false fallback. Spec ambiguity on System.Quantity vs FHIR.Quantity.
  Both backends defensible. No fix required.

  **(QA-005 LOW §6.6 / §5.2 DEFERRED):** Canonical where-clause
  `Observation.component.where((value as Quantity).value > 30 'mg').count()`
  produces wrong result in BOTH backends. Root cause is in the
  comparison-after-as chain (`(value as Quantity).value > 30 'mg'`
  returns empty in both backends — should return `[true, false]`).
  This is a §6.6 / §5.2.2 cross-product issue, not §6.3. Deferred to
  a future chunk.

  Native C++ extension rebuilt (md5sum `e71c25424b22072e831d386fc5e477ec`)
  and copied to both package and user install paths. Post-fix: HISTORIAN
  probe 0 native↔fallback diffs for the 3 resolved issue categories;
  FHIRPath pytest 376/376 (was 373, +3 new tests); full conformance
  2822/2822 unchanged. Probe artifact:
  `/mnt/d/fhir4ds/.temp/qa/fp15_historian_2026_06_29/probe.py` (334 cases).

  **NOT A BUG Registry (FP-15 HISTORIAN additions):**
  - Form parity (`is TypeSpecifier` vs `is(type)` and `as TypeSpecifier`
    vs `as(type)`) is clean across all 34 paired cases — confirms the
    FP-15 SKEPTIC archive finding.
  - FHIR R4 primitive hierarchy: `date`/`dateTime`/`instant`/`time` are
    JSON-string-encoded but are sibling primitives under Element (NOT
    subtypes of `string`). Only `id`/`code`/`uri`/`url`/`canonical`/
    `oid`/`uuid`/`markdown` are valid string-subtypes.
  - Per §6.3.1, empty input collection to `is` MUST propagate as empty,
    not `false`. Both backends now correctly return empty for
    `Observation.value is Quantity` when value is absent.

- **FHIRPath FP-15 SKEPTIC iter 1 §6.3 Types Quantity-profile subtype
  rejection (2026-06-29):** **1 ISSUE RESOLVED, 2 DEFERRED, 1 INTENDED.**
  A fresh SKEPTIC hypothesis-driven probe with 202 expressions across
  9+ hypothesis groups tested every orchestrator-briefed §6.3 bug class
  at the public DuckDB UDF boundary comparing bundled native C++
  extension vs forced Python fallback through all 5 UDF wrappers.
  Coverage: H1 form parity (`is TypeSpecifier` vs `is(type)` — REJECTED,
  both forms produce identical results across 34 paired cases), H2 FHIR
  resource types, H3 System types vs FHIR primitives, H4 FHIR primitive
  types, H5 choice-type fields (value[x]), H6 subtype matching (Resource,
  DomainResource, Element, Any), H7 unknown type specifiers, H8 multi-item
  input, H9 empty propagation.

  **(QA-001 HIGH §6.3.1/§4.1.8 RESOLVED):** Native C++ at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:8845` short-circuited
  `target == Age || target == Duration` to true for ANY Quantity literal,
  conflating FHIR R4 profiles on Quantity (Age/Distance/Duration/Count/
  Money/SimpleQuantity) with the base Quantity type. Reproducer:
  `5 'mg' is Age` returned `true` native vs `false` fallback (must be
  `false` — `mg` is mass, not Age); same for `5 'mg' is Duration`.
  Inconsistently, `5 'mg' is Distance/Count/Money` already correctly
  returned `false`. Spec citation: §6.3.1 "is returns true if the type
  of the left operand is the type specified, or a subclass thereof";
  Age/Distance/Duration are FHIR R4 profiles that require specific UCUM
  unit categories (Age uses calendar units `a`/`yr`, Duration uses
  `s`/`min`/`h`/`d`/`wk`). A bare Quantity literal has no FHIR profile
  metadata. Surgical fix at evaluator.cpp:8845-8851: removed `Age` and
  `Duration` from the over-permissive branch; only `target == "Quantity"`
  now matches a literal Quantity. 2 new regression tests added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`:
  `test_quantity_literal_fhir_profile_subtypes_reject_in_both_backends_fp15_skeptic`
  (10 cases) and `test_is_as_type_specifier_form_parity_fp15_skeptic`
  (15 paired cases). Native C++ extension rebuilt (md5sum
  `dcce79e6eb9352964f7f02809f43fd7c`) and copied to both package and
  user install paths. Post-fix: SKEPTIC probe 0 native↔fallback diffs
  for Quantity subtype matrix; FHIRPath pytest 1501/1501 (was 1499,
  +2 new tests); full conformance 2822/2822 unchanged.

  **(QA-002 LOW §6.3.1/§10.1/§4.1.8 INTENDED):** `5 'mg' is FHIR.Quantity`
  returns `true` native vs `false` fallback. Quantity literal is
  `System.Quantity` per §4.1.8; native treats System.Quantity ==
  FHIR.Quantity (reasonable since Quantity is conceptually shared);
  fallback enforces strict namespace-distinct rule (also reasonable).
  Spec is ambiguous about whether System.Quantity and FHIR.Quantity
  are identical or distinct. No official R4 conformance test exercises
  this case. Both backends' behavior is defensible. Classified INTENDED.

  **(QA-003 MEDIUM §6.3.1 DEFERRED):** `Bundle.entry.first() is
  BackboneElement` returns `true` native vs `false` fallback. Root
  cause: Python fallback's `fhir_path_to_type.json` does not include
  `Bundle.entry` (or any Bundle.* path). When the value's path metadata
  cannot resolve, the fallback falls through to value-based inference
  returning "object". Native C++ uses a hardcoded heuristic at
  `evaluator.cpp:8749` that classifies any anonymous dict with a
  non-empty `field_name` as `BackboneElement` (over-broad). Native is
  more spec-correct for the specific Bundle.entry case (BackboneElement
  IS the FHIR R4 type of Bundle.entry). Deferred to a metadata-completeness
  task — both backends have correctness gaps; complete fix requires
  adding Bundle.entry and other BackboneElement paths to
  `fhir_path_to_type.json` AND removing the over-broad C++ heuristic.

  **(QA-004 LOW §6.3.1 DEFERRED):** Same root cause as QA-003.
  `Patient.meta.profile.first() is FHIR.uri` returns `true` native vs
  `false` fallback. The field is `List<canonical>` per FHIR R4; canonical
  is subtype of uri. Native correctly identifies canonical via field
  metadata; fallback lacks the metadata, falls through to value-based
  inference returning "string" (which is NOT subtype of uri). Deferred
  to the same metadata-completeness task as QA-003.

  **NOT A BUG Registry (FP-15 SKEPTIC additions):**
  - Form parity (`is TypeSpecifier` vs `is(type)`) is clean across all
    34 paired cases. Same for `as TypeSpecifier` vs `as(type)`. The C++
    parser at `parser.cpp:230-252` (unparenthesized) and `parser.cpp:4320-4330`
    (parenthesized) both feed into the same `fn_isType`/`fn_asType`
    evaluators.
  - `is FHIR.Boolean` (Capitalized) returns invalid in both backends.
    FHIR primitive types are lowercase per FHIR R4 (`boolean`, `string`,
    `integer`, etc.). Capitalized names are System types. Correct
    case-sensitivity enforcement per §8.7.
  - System vs FHIR primitive distinction (`Patient.active is System.Boolean`
    correctly returns `false` per official R4 testType14). Both backends
    agree.
  - `as FHIR.string` on subtype (`Patient.id as FHIR.string`,
    `Patient.gender as FHIR.string`) returns empty even though `is
    FHIR.string` returns true. This is the documented "FHIR R4 primitive
    conformance treats primitive casts as exact" design choice in
    `fhir4ds/fhirpath/engine/invocations/types.py:84-94`. While spec
    §6.3.3 says `as` should mirror `is` (which uses subtype matching),
    no official R4 conformance test exercises this case, and the existing
    source comment justifies the strict behavior. Both backends agree.
    Classified INTENDED.

  **Side discovery (out of scope):** `5 'mg' is SimpleQuantity` returns
  invalid in native (SimpleQuantity missing from C++ `fhirTypeIsA`
  hierarchy table at evaluator.cpp:874-1083) but valid `false` in
  fallback. Could be addressed by adding SimpleQuantity to the C++
  hierarchy table in a future iteration.

  Probe artifacts:
  `/mnt/d/fhir4ds/.temp/qa/fp15_skeptic_2026_06_29/probe.py` (145 cases,
  9 hypothesis groups), `probe_round2.py` (57 cases, extended edge cases).

- **FHIRPath FP-14 EXPLORER iter 1 §6.2 Comparison Decimal arithmetic
  adjacent-integer parity (2026-06-29):** **1 ISSUE RESOLVED.** A fresh
  EXPLORER pathological-input fuzz pass threw 261 expressions across 3
  rounds (152 + 53 + 56 cases) at the public DuckDB UDF boundary
  comparing bundled native C++ extension vs forced Python fallback
  through all 5 UDF wrappers. Coverage: extreme Decimal magnitudes
  (V1), 15+ digit Decimal precision (V2), NaN/Infinity edges (V3),
  integer overflow in comparison (V4), multi-byte Unicode strings
  (V5), very large strings 10000+ chars (V6), polymorphic choice-types
  (V7), deeply nested comparison chains (V8), timezone edges (V9),
  composed with iif/where/implies (V10), empty propagation (V11),
  mixed-type comparison edges (V12), Quantity extreme magnitudes (V13),
  datetime precision mismatch (V14), calendar vs UCUM duration (V15).
  Round 2 added focused precision probes (adjacent-decimals 1-ULP
  boundary, subnormal-range decimals, Quantity arithmetic precision,
  cross-timezone near-midnight, resource-backed quantity precision,
  arithmetic chain feeding comparison). Round 3 added deep-stress
  probes (Long Decimal magnitude, long string lexicographic, composed
  where() with comparison, polymorphic Quantity choice, IDL timezone,
  empty propagation through composed chains, **large Decimal arithmetic
  feeding comparison** — where the diff was found).

  **(QA-001 HIGH §5.7.1/§4.1.4/§6.2 RESOLVED):** Native C++ Decimal
  +/- at `evaluator.cpp` ~7800+ used binary64 `double` via
  `getNumericValue(lv) + getNumericValue(rv)`; at the 2^53 boundary,
  `9007199254740992.0 + 1.0` rounded back to `9007199254740992.0`
  because binary64 cannot represent `9007199254740993`. Reproducer
  (3 forms): `(2).power(53) < (2).power(53) + 1` returned `false`
  native vs `true` fallback; same for `(2).power(63)` and other
  adjacent-integer arithmetic cases above 2^53. Surgical fix: added
  `tryIntegerArithmeticText` helper at evaluator.cpp (after
  `multiplyIntegerMagnitudes` near line 5907) plus supporting
  schoolbook helpers `addIntegerMagnitudes` and
  `subtractIntegerMagnitudes`. The helper performs exact text-based
  integer arithmetic on operands whose source_text represents a pure
  integer (fractional part is empty or all-zeros), returns Decimal-
  shaped source text (e.g. "9007199254740993.0"), and is capped at
  10000 digits to prevent OOM. Mirrors the FP-11 EXPLORER
  `powerIntegerExactText` pattern. Wired into the Decimal arithmetic
  path before the binary64 fallback, gated on at least one operand
  being non-Integer type to preserve int32-promote-on-overflow
  semantics. 1 new regression test (17 cases) added to
  `test_comparison_parity.py::
  test_decimal_arithmetic_feeding_comparison_preserves_adjacent_integers_fp14_explorer`.
  Native C++ extension rebuilt and copied to package + user install
  paths (md5sum `24f083eac762b21ddaefc396805842e4`). Post-fix:
  EXPLORER probe round 3 56/56 (was 53/56); rounds 1+2 unchanged;
  full FHIRPath integration 371/371 (was 370 + 1 new test); FP-14
  SKEPTIC fix intact; FP-13 HISTORIAN fix intact; full conformance
  2822/2822 unchanged.

  **NOT A BUG Registry (FP-14 EXPLORER additions):**
  - valueDecimal on Observation is invalid R4 (choice type list excludes
    decimal); both backends agree.
  - `1 < 2 < 3` parses as `(1 < 2) < 3`; Boolean not orderable per §6.2;
    both backends error.
  - `true < false`, `true <= true`: Boolean not orderable; both error.
  - `1 < '1'`, `1 < true`, `@2024 < 1`: cross-type returns empty; both
    agree.
  - Calendar-vs-UCUM above-second boundary: returns empty per §4.1.8;
    both agree.
  - Cross-unit temperature: FP-13 HISTORIAN QA-002 carry-over and
    FP-14 SKEPTIC fixes verified intact.

  Probe artifacts: `/mnt/d/fhir4ds/.temp/qa/fp14_explorer_2026_06_29/probe.py`
  (152 cases / 15 groups), `probe_round2.py` (53 cases / 7 groups),
  `probe_round3.py` (56 cases / 7 groups), `diag_power_arith.py`
  (root-cause diagnostic).

- **FHIRPath FP-14 HISTORIAN iter 1 §6.2 Comparison systematic
  spec-walkthrough (2026-06-29):** **0 NEW ISSUES — VERIFIED CLEAN.**
  A fresh HISTORIAN systematic spec-walkthrough enumerated every
  normative rule from FHIRPath v2.0.0 §6.2.1-§6.2.4 across all 4
  comparison operators (`>`, `<`, `<=`, `>=`) at the public DuckDB
  UDF boundary, comparing bundled native C++ extension vs forced
  Python fallback through all 5 UDF wrappers
  (fhirpath/fhirpath_text/fhirpath_json/fhirpath_bool/fhirpath_number).
  Probe composition: 267 native↔fallback parity cases across 16
  groups (every §6.2 spec paragraph and example) + 36 spec-anchor
  value-verification cases (every documented spec example asserted
  against its expected output). Coverage by group: §6.2.1 `>` spec
  examples (12), §6.2.2 `<` spec examples (12), §6.2.3 `<=` spec
  examples (16, including def-sanity cases for spec typos),
  §6.2.4 `>=` spec examples (14, same typo class), empty propagation
  (14), singleton requirement (5), type strictness (13 — int/str,
  bool-not-orderable per §6.2 paragraph 1, date-vs-time),
  Integer/Decimal implicit conversion (18 incl. Decimal precision
  drift `0.1+0.2 vs 0.3`), String Unicode-codepoint lexicographic
  (15), Quantity unit conversion (20 — m/cm, g/mg, dimension-mismatch
  cm vs cm2 returns empty), Calendar-vs-UCUM duration (32 —
  `1 year > 1 'a' // empty`, `10 seconds > 1 's' // true`, plus
  minute/hour/day/week/month boundary), Cross-unit temperature
  FP-13 carry-over (22 — Cel/[degF]/K both arg orders all 4 operators
  + same-unit passthrough), Date/Time precision mismatch (30),
  DateTime timezone-aware (16 incl. cross-timezone near-midnight UTC
  vs EST previous-day), Resource-backed valueQuantity/effectiveDateTime
  (22), Operator precedence #08 vs #09 (6). All 267 cases parity
  across all 5 UDF wrappers. All 36 spec anchors produce exact
  documented output.

  **NOT A BUG Registry (FP-14 HISTORIAN additions):**
  - **Spec §6.2.3 example typos:** The published v2.0.0 spec example
    list for `<=` contains obvious typos: `10 <= 5 // true`,
    `10 <= 5.0 // true`, `'abc' <= 'ABC' // true`. Per the operator
    definition "returns true if the first operand is less than or
    equal to the second", these should be `false`. The engine
    correctly returns `false` per the definition (not the typo).
  - **Spec §6.2.4 example typos:** Same class of typos in the `>=`
    example list: `10 >= 5 // false`, `10 >= 5.0 // false`,
    `'abc' >= 'ABC' // false`. Per the operator definition these
    should be `true`. The engine correctly returns `true`.
  - **Calendar-vs-UCUM above-second boundary correctly implemented:**
    Spec rule "calendar durations and definite quantity durations
    above seconds are considered un-comparable" is correctly enforced.
    `10 seconds > 1 's'` returns `true` (second boundary allowed);
    `1 minute > 1 'min'`, `1 hour > 1 'h'`, `1 day > 1 'd'`,
    `1 week > 1 'wk'`, `1 month > 1 'mo'`, `1 year > 1 'a'` all
    return empty.
  - **Cross-unit temperature fix intact:** FP-13 HISTORIAN QA-002
    (deferred to FP-14) and FP-14 SKEPTIC fixes both verified intact
    via 22-case parity probe. `1 'Cel' < 33.8 '[degF]'` returns
    empty in both backends (was `False` in native pre-FP-14-SKEPTIC).
  - **Seconds/milliseconds unified-precision rule:** Spec §6.1.1
    "seconds and milliseconds are considered a single precision using
    a decimal" correctly applied in §6.2. `@T10:30:00 > @T10:30:00.0`
    returns `false` (equal value), `>=` returns `true`.

  Probe artifacts:
  `/mnt/d/fhir4ds/.temp/qa/fp14_historian_2026_06_29/probe.py`
  (267 cases / 16 groups / 5 UDF wrappers),
  `probe_spec.py` (36 spec anchors). Full conformance 2822/2822
  unchanged (ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47). No source changes, no new tests, no native rebuild.
  The §6.2 surface is well-hardened; HISTORIAN methodology produces
  zero false positives on a clean surface and adds independent
  verification value via spec-anchor assertion (proves the agreed
  value matches the spec, not just native↔fallback agreement).

- **FHIRPath FP-14 SKEPTIC iter 1 §6.2 Comparison cross-unit
  temperature parity (2026-06-29):** **1 ISSUE RESOLVED.** A fresh
  SKEPTIC hypothesis-driven probe with 89 expressions across 9
  hypothesis groups tested every orchestrator-briefed §6.2 bug class
  at the public DuckDB UDF boundary comparing bundled native C++
  extension vs forced Python fallback. Coverage: H1 cross-unit
  temperature (Cel/[degF]/K, both arg orders, all 4 operators), H2
  Decimal precision drift through binary64 (0.1+0.2 vs 0.3, etc.),
  H3 cross-timezone DateTime comparison (near-midnight UTC boundary
  cases), H4 empty-collection propagation ({} < 1, missing < 1),
  H5 type-mismatched comparison (5 < '5', 5 < true, @2024 < 1),
  H6 mixed Integer/Decimal comparison (5 < 5.5, 5 < 5.0), H7 Boolean
  not orderable (true < false — spec §6.2 excludes Boolean), H8 large
  Long/Decimal magnitude (FP-14 SKEPTIC archive regression check),
  H9 String lexicographic (Unicode codepoint ordering).

  **(QA-001 HIGH §6.2/§4.1.8 RESOLVED):** Native C++ §6.2 comparison
  operator path at `extensions/fhirpath/src/fhirpath/evaluator.cpp:7539-7559`
  lacked the `isOffsetTemperatureUnit` guard that FP-13 HISTORIAN added
  to the §6.1 equality path at 5 sites. The UCUM table at
  `extensions/fhirpath/src/include/shared/ucum_units.hpp:108-109` marks
  `[degF]` with sentinel factor -1.0 ("sentinel: handled specially by
  caller") but the §6.2 path computed
  `(val * from_base_factor) / to_base_factor` without offset handling,
  producing arithmetically wrong Boolean results. Reproducer (all 4 §6.2
  operators, both arg orders): `1 'Cel' < 33.8 '[degF]'` returned
  `False` native vs `NULL` fallback (must be `NULL`); same for `>`,
  `<=`, `>=`, and reverse-argument forms. Spec citation: §6.2
  "Attempting to operate on quantities with invalid units will result
  in empty (`{ }`)." + "Implementations are not required to fully
  support operations on units, but they must at least respect units,
  recognizing when units differ." + §4.1.8 "Implementations that do not
  support complete UCUM functionality may return empty (`{ }`) for
  calculations involving quantities with units where the units are
  different." UCUM defines temperature conversions with affine offsets
  (degF = degC × 9/5 + 32), not multiplicative factors. Surgical fix
  at evaluator.cpp:7540-7558: added the same `isOffsetTemperatureUnit`
  guard right after `isMixedCalendarUcumDurationAboveSeconds` and
  before the same-unit fast-path, mirroring the FP-13 HISTORIAN fix
  pattern at line 7290-7294. The unit-difference gate
  (`lv.quantity_unit != rv.quantity_unit && ...`) preserves same-unit
  passthrough (1 'Cel' < 2 'Cel') via the existing decimal-text
  fast-path. 1 new regression test added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py`:
  `test_cross_unit_temperature_comparison_returns_empty_in_both_backends_fp14_skeptic`
  (15 cases). Native C++ extension rebuilt and copied to both package
  and user install paths (md5sum 1f856dd79fc5c5731eeb171e3d131f34).
  Post-fix: SKEPTIC probe 89/89 (was 81/89); FP-13 HISTORIAN equality
  fix intact; FHIRPath pytest 1498/1498 (was 1497, +1 new test); full
  conformance 2822/2822 unchanged.

  **NOT A BUG Registry (FP-14 SKEPTIC additions):**
  - H2-H9 hypotheses all REJECTED: the §6.2 surface is otherwise
    well-hardened. Decimal precision drift does not leak (uses
    `numericTextForComparison` + `compareDecimalText`); cross-timezone
    DateTime handles +00:00/-05:00 etc correctly; empty-collection
    propagation works; type-mismatched comparisons return empty;
    Integer/Decimal mix preserves magnitude; Boolean ordering is
    correctly rejected per §6.2; large Long/Decimal magnitude is
    preserved via source_text (FP-14 SKEPTIC archive fix intact);
    String lexicographic ordering matches between paths.
  - Same-unit offset-temperature comparison (`1 'Cel' < 2 'Cel'`)
    remains correct via the decimal-text fast-path at line 7559-7567,
    which does not invoke `convertQuantityToBase`. The
    `isOffsetTemperatureUnit` guard only triggers when units differ.

  Probe artifacts: `/mnt/d/fhir4ds/.temp/qa/fp14_skeptic_2026_06_29/probe.py`
  (89 cases, 9 hypothesis groups).

- **FHIRPath FP-13 HISTORIAN iter 1 §6.1 Equality cross-unit
  temperature parity (2026-06-29):** **1 ISSUE RESOLVED, 1 DEFERRED
  to FP-14.** A fresh HISTORIAN systematic spec-walkthrough probe
  with 231 cases (154 parity + 37 spec-value + 40 deep edge) across
  3 rounds enumerated every normative rule from FHIRPath v2.0.0
  §6.1.1-§6.1.4 at the public DuckDB UDF boundary comparing bundled
  native C++ extension vs forced Python fallback.

  **(QA-001 HIGH §6.1.1/§6.1.2 RESOLVED):** Native C++ equality
  operator path produced wrong Boolean results for cross-unit
  temperature comparisons. `1 'Cel' = 33.8 '[degF]'` returned
  `False` in native vs `NULL` in fallback; same asymmetry on `~`,
  `!=`, `!~`. Root cause: FP-08 EXPLORER added `isOffsetTemperatureUnit`
  guard to `convertQuantityUnit` (the `toQuantity(unit)` conversion
  path at evaluator.cpp:2010) but the equality operator path was
  missed. The UCUM table at ucum_units.hpp:108-109 marks `[degF]`
  with sentinel factor -1.0; without an offset guard, the equality
  path computed wrong arithmetic on the sentinel factor. Surgical
  fix at 4 native sites: forward declaration at evaluator.cpp:653;
  `quantityEqualState` at line 1598 (returns -1/empty); 
  `quantityEquivalentState` at line 1622 (returns -1/empty);
  `quantityValuesEqual` at line 1867 (returns false for distinct/
  isDistinct/subsetOf/supersetOf — matches Python fallback's
  distinct() behavior); `valuesEqualState` lambda at line 7240
  (returns -1/empty). The `valuesEquivalentState` lambda at line
  7166 already calls `quantityEquivalentState` so is automatically
  covered. Native extension rebuilt and copied to both package and
  user install paths. 1 new regression test added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`:
  `test_cross_unit_temperature_equality_returns_empty_in_both_backends_fp13_historian`
  (10 cases). Post-fix: HISTORIAN probe 231/231 (was 230/231);
  FHIRPath pytest 369/369; full conformance 2822/2822 unchanged.

  **(QA-002 MEDIUM §6.2 NEW — DEFERRED to FP-14):** Same cross-unit
  temperature parity defect exists on §6.2 comparison operators
  (`<`, `>`, `<=`, `>=`) because they have their own dedicated code
  path at evaluator.cpp:7460-7480 that does NOT call
  quantityEqualState/quantityEquivalentState. Reproducer:
  `1 'Cel' < 33.8 '[degF]'` returns `False` in native vs `NULL` in
  fallback. Out of FP-13 §6.1 scope; logged for FP-14 §6.2.

  **NOT A BUG Registry (FP-13 HISTORIAN additions):**
  - Cross-type single-item equality returns empty (not false):
    `5 = '5'`, `5 = true`, `'abc' = true` return NULL in both
    backends. Spec §6.1.1 "Otherwise, equals returns false" is
    structurally ambiguous on whether it covers single-item type
    mismatches. Official R4 conformance suite does not test these
    cases. Both backends agree.
  - Confirms FP-13 SKEPTIC archive findings: string equivalence
    whitespace "replace not collapse", calendar-vs-UCUM year/month
    equality returns empty.

  Probe artifacts: `/mnt/d/fhir4ds/.temp/qa/fp13_historian_2026_06_29/probe.py`
  (154 cases), `probe2.py` (37 cases), `probe3.py` (40 cases).

- **FHIRPath FP-13 SKEPTIC iter 1 §6.1 Equality verification
  (2026-06-29):** **0 NEW ISSUES — VERIFIED CLEAN.** A fresh
  SKEPTIC hypothesis-driven probe with 127 expressions across 3
  rounds tested every orchestrator-briefed §6.1 bug class at the
  public DuckDB UDF boundary comparing bundled native C++
  extension vs forced Python fallback. Coverage: UCUM Quantity
  equality (`1 'g' = 1000 'mg'`, `1 'cm' = 10 'mm'`, `5 'mg' = 6 'mg'`),
  cross-timezone DateTime equality
  (`@2024-01-01T00:00:00+00:00 = @2023-12-31T19:00:00-05:00`),
  empty propagation (`{} = {}`, `{} != {}`, `{} ~ {}`, `{} !~ {}`),
  type-mismatched equality (`5 = '5'`, `5 = true`, `'abc' = true`),
  String equivalence case+whitespace normalization
  (`'abc' ~ 'ABC'`, `'hello world' ~ 'hello   world'`),
  Decimal precision drift (`0.1 + 0.2 = 0.3`, `1.1 + 2.2 = 3.3`),
  `!~` semantics (`5 !~ '5'`, `5 !~ 6`), Boolean equality,
  multi-item collections (`(1 | 2) = (1 | 2)`), DateTime precision
  (`@2012-01 = @2012`, `@T10:30 = @T10:30:00`), Integer-vs-Decimal
  (`5 = 5.0`), calendar-vs-UCUM durations
  (`1 year ~ 1 'a'`, `1 second = 1 's'`), ResourceNode unwrap
  (`Patient.id = 'probe'`), resource Quantity equality
  (`Observation.valueQuantity = 5 'mg'`), Decimal precision
  boundaries (`1.00000001 = 1.0`), large integers
  (`2147483647 = 2147483647`), nested equality
  (`(((1 = 1)) = true) = true`). Result: 0 native↔fallback diffs
  across 127 cases. 3 NOT A BUG entries (whitespace normalization
  "replace not collapse" matching v2.0.0 spec literal text —
  documented in
  `test_string_equivalence_normalizes_case_and_whitespace_without_collapse`;
  calendar-vs-UCUM year/month equality returns `empty` not `false`
  due to implementation-defined conversion factor — documented in
  `test_calendar_duration_equality_shape_in_forced_python_fallback`;
  Date vs Time equality returns `false` per spec silence on
  non-convertible temporal types). The §6.1 surface is well-hardened:
  pre-existing `test_equality_parity.py` covers 14 named test
  functions including 100+ parametrized cases. No source changes,
  no new tests. Full conformance 2822/2822 unchanged (ViewDefinition
  134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47). Probe
  artifacts: `/mnt/d/fhir4ds/.temp/qa/fp13_skeptic_2026_06_29/probe{,2,3}.py`.

  **NOT A BUG Registry (FP-13):**
  - String equivalence whitespace handling: implementation uses
    "replace each whitespace char with single space" semantics
    (NOT "collapse sequences to single space"). `'hello   world' ~ 'hello world'`
    → `False`. This matches v2.0.0 spec text's literal reading
    ("all whitespace characters are treated as equivalent"). The
    v3.0.0 build spec clarifies as collapse, but no R4 conformance
    test enforces either behavior. The existing test
    `test_string_equivalence_normalizes_case_and_whitespace_without_collapse`
    documents this as INTENTIONAL.
  - Calendar-vs-UCUM year/month equality: spec §4.1.8 says
    `1 year = 1 'a'` is `false`, but both backends return `empty`
    because the conversion factor (year = 365 vs 365.25 days) is
    implementation-defined. Both backends agree. Existing test
    `test_calendar_duration_equality_shape_in_forced_python_fallback`
    documents this as INTENTIONAL.
  - Date vs Time equality: spec is silent on exact behavior for
    incompatible temporal types. Both backends return `false` (not
    `empty`). Reasonable interpretation of non-convertible types
    per §5.5 conversion table.

- **FHIRPath FP-12 EXPLORER iter 1 §5.8.2/§4.1.4/§5.5.8 Tree Navigation
  + decimal-primitive text rendering (2026-06-29):**
  **2 ISSUES RESOLVED.** A fresh EXPLORER pathological-input fuzz pass
  threw 150 expressions across 14 vector groups at all 6 §5.8-§5.9
  functions (`children`, `descendants`, `trace`, `now`, `today`,
  `timeOfDay`), comparing bundled native C++ extension vs forced Python
  fallback through all 5 public UDF wrappers. Coverage: deeply nested
  resources (10-5000 deep contained chains), polymorphic choice-type
  fields, theoretical circular references (duplicate-content structures),
  extension shadowing primitives (split-representation `_id`/`_birthDate`/
  `_given` arrays), leap-second/leap-year boundaries, malformed trace
  names (empty/dash/dot/space/Unicode/emoji/1000-char), deeply composed
  trace projections, ResourceNode unwrap edges, empty-collection
  propagation, very large resources (10-1000 extension entries), trace
  arity & projection scoping, datetime shape divergence, composition
  matrix.

  **(QA-001 HIGH §5.8.2 RESOLVED):** Python fallback `descendants()` at
  `fhir4ds/fhirpath/engine/invocations/navigation.py:192` silently
  crashed with RecursionError on resources nested >= ~490 deep.
  Reproducer: Patient with 500-deep contained chain. Native returned
  `descendants().count() = [1501]`; fallback returned `[]` (UDF wrapper
  caught exception and returned empty per row-resilience pattern). Root
  cause traced via monkey-patched `do_eval` instrumentation to
  `_descendant_repeat_key` at `navigation.py:215-225` calling
  `json.dumps(data, sort_keys=True, separators=(",",":"), default=str)`
  on each item — `json.dumps` recursively serializes nested structures
  and consumes one Python stack frame per nesting level. Combined with
  the evaluator's own frame overhead, depths >= ~490 push past Python's
  default 1000-frame recursion limit. Native C++ `fn_descendants` at
  `evaluator.cpp:9083` uses an iterative work-queue with a 50000-
  descendant safety cap; the Python fallback must mirror that capacity.
  Surgical fix: replaced the recursive `json.dumps` call with a new
  iterative serializer `_iterative_canonical_json` at
  `navigation.py:243-340` that uses an explicit stack of frames (each
  frame is a dict with `kind`/`obj`/`slot` keys, allocating child slots
  in a flat `out` list). Produces byte-identical output to the prior
  `json.dumps` for shallow inputs (validated by 15-case round-trip
  test including null/bool/int/float/string/Decimal/unicode/emoji/
  empty dict/list/list-of-dicts) and handles arbitrary depth (tested
  to depth 5000 with recursion limit artificially lowered to 100).

  **(QA-002 MEDIUM §4.1.4/§5.5.8 RESOLVED):** Native C++ FastText and
  FastList paths rendered JSON decimal primitives at 6-digit fixed
  precision. Reproducer: `{...,"valueDecimal":12.5}` accessed via
  `fhirpath_text` or `fhirpath` returned `'12.500000'` native vs
  `'12.5'` fallback. Affects every direct member access of a JSON
  decimal primitive (Observation.valueDecimal, Observation.valueQuantity
  .value, extension.valueDecimal, etc.). Root cause: `std::to_string
  (double)` uses `setprecision(6) << std::fixed` by C++ standard
  ([string.conversions]); this diverges from both the Python fallback's
  `str(float)` shortest-round-trip rendering AND the non-fast-path
  `Evaluator::jsonValToString` which correctly uses
  `formatDecimalNumber(yyjson_get_real(val), jsonNumberText(val))`.
  Surgical fix at 2 native sites: (a) `FastPathLookup` at
  `fhirpath_extension.cpp:513-514` — replaced
  `std::to_string(yyjson_get_real(current))` with
  `yyjson_val_write(current, 0, nullptr)` which extracts the original
  JSON text. (b) `JsonValueToOwnedString` at
  `fhirpath_extension.cpp:757-760` — same replacement. Both sites now
  match the fhirpath_json UDF wrapper (which already used
  `yyjson_val_write` directly) and the Python fallback. Native
  extension rebuilt and copied to both package and user install paths.

  3 new regression tests added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`:
  `test_descendants_handles_deeply_nested_resources_fp12_explorer`
  (5 depths: 10/100/500/1000/2000),
  `test_descendants_dedup_correctness_after_iterative_serializer_fp12_explorer`
  (3 cases verifying dedup behavior unchanged for shallow resources),
  `test_json_decimal_primitive_text_rendering_fp12_explorer` (7 decimal
  values + Observation.valueQuantity.value composition).
  Post-fix: EXPLORER probe 150/150 (was 148/150); FP-12 SKEPTIC and
  HISTORIAN fixes intact; FHIRPath pytest 1496/1496 (was 1493, +3 new
  tests); full conformance 2822/2822 unchanged. Native C++ rebuilt and
  copied to both package and user install paths.
  Probe artifact: `/mnt/d/fhir4ds/.temp/qa/fp12_explorer_2026_06_29/probe.py`.

- **FHIRPath FP-12 HISTORIAN iter 1 §5.8.1/§5.9.2/§5.9.3 Tree Navigation
  + Utility Functions native↔fallback parity (2026-06-29):**
  **3 ISSUES RESOLVED.** A fresh HISTORIAN systematic spec-walkthrough
  probe with 113 normative-rule cases across all 6 §5.8-§5.9 functions
  (`children`, `descendants`, `trace`, `now`, `today`, `timeOfDay`),
  comparing bundled native C++ extension vs forced Python fallback
  through all 5 public UDF wrappers. Coverage: §5.8.1 children() 18
  cases (primitive/complex/null children, resourceType skipping,
  primitive extensions, multi-item flattening, arity), §5.8.2
  descendants() 13 cases (recursive depth, dedup, primitive input,
  Bundle traversal, missing-path, arity), §5.9.1 trace() 15 cases
  (input unchanged, projection scoping, arity validation, name-type
  validation, composed trace), §5.9.2 now() 9 cases (DateTime shape,
  deterministic, comparison, arity, type, composition), §5.9.3
  timeOfDay() 7 cases, §5.9.4 today() 7 cases, plus 44 cross-backend
  × wrapper cases.

  **(QA-001 HIGH §5.8.1 RESOLVED):** Python fallback `visit()` in
  `fhir4ds/fhirpath/__init__.py:84-105` filtered dicts whose only key
  was `'extension'` AT ANY DEPTH in the result tree, not just top-
  level ResourceNode items. This dropped the inner contents of FHIR
  split-representation primitive-extension arrays (e.g.
  `_given:[null,{extension:...}]`) during normal path traversal.
  Native C++ `fn_children` zips shadow arrays correctly via
  `yyjson_arr_get(shadow, idx2)` and preserves the full content.
  Reproducer: `children()` on Patient with split `_given` array —
  native returned `{"given":["Mary"],"_given":[null,{"extension":[...]}]}`,
  fallback returned truncated `{"given":["Mary"],"_given":[null]}`.
  Surgical fix: mirrored the `returnRawData` branch's ResourceNode
  guard in `visit()` — only filter items that are ResourceNodes whose
  `.data` is extension-only. Plain dict items inside the tree now pass
  through unchanged.

  **(QA-002 MEDIUM §5.9.2 RESOLVED):** Python fallback `now()` at
  `fhir4ds/fhirpath/engine/invocations/datetime.py:434-441` returned
  `FP_DateTime(datetime.now(timezone.utc).isoformat())` which renders
  microseconds (6 fractional digits) when present. Native C++ `fn_now`
  uses `snprintf("%04d-%02d-%02dT%02d:%02d:%02d+00:00", ...)` — no
  fractional. Reproducer: `now()` native `2026-06-29T12:57:59+00:00`
  vs fallback `2026-06-29T12:57:59.125972+00:00`. Surgical fix at
  line 444: strip microseconds via `.replace(microsecond=0)` before
  isoformat, matching native's seconds-precision shape. Per §5.9.2
  the timestamp is implementation-defined; native↔fallback parity is
  the contract.

  **(QA-003 MEDIUM §5.9.3 RESOLVED):** Python fallback `timeOfDay()`
  at `fhir4ds/fhirpath/engine/invocations/datetime.py:453-459` used
  `_now.time().replace(tzinfo=None).isoformat()` which renders
  microseconds (6 fractional digits). Native C++ `fn_timeOfDay` uses
  `snprintf("%02d:%02d:%02d.000", ...)` — 3-digit zero-padded
  milliseconds per spec §5.5.8 canonical Time format `hh:mm:ss.fff`.
  Reproducer: `timeOfDay()` native `12:57:59.000` vs fallback
  `12:57:59.144123`. Surgical fix at line 468-469: replace isoformat
  with explicit `strftime("%H:%M:%S.000")` to produce exactly the
  3-digit millisecond shape matching native.

  3 new regression tests added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`:
  `test_children_preserves_split_primitive_extension_metadata_fp12_historian`,
  `test_now_timeoday_today_match_native_rendering_shape_fp12_historian`,
  `test_now_and_timeoday_rendering_parity_fp12_historian`. Native C++
  unchanged (all 3 fixes were Python-fallback-only); no native rebuild
  required. Post-fix: HISTORIAN probe 113/113 (was 108/113); FP-12
  SKEPTIC fix intact (trace projection scoped per item); FP-12 EXPLORER
  fix intact (primitive shadow metadata visible); FHIRPath pytest
  1493/1493 (was 1490, +3); full conformance 2822/2822 unchanged.
  Probe artifact: `/mnt/d/fhir4ds/.temp/qa/fp12_historian_2026_06_29/probe.py`.

- **FHIRPath FP-11 EXPLORER iter 1 §5.7.7/§5.7.10/§5.7.3/§5.7.8 Math
  pathological-input parity (2026-06-29):** **4 ISSUES RESOLVED, 1
  INTENDED, 1 DEFERRED.** A fresh EXPLORER fuzz pass threw 127
  pathological expressions across 12 vector groups (extreme magnitudes,
  NaN/Infinity edges, Decimal precision boundaries, Integer overflow in
  power, Quantity arithmetic on extreme values, polymorphic choice-type
  math, deeply nested math, ResourceNode unwrap, empty-collection
  propagation, type-mismatch rejection) at the public DuckDB UDF
  boundary comparing bundled native C++ extension vs forced Python
  fallback.

  **(QA-001 HIGH §5.7.7/§4.1.4/§5.5.8 RESOLVED):** Native C++ `fn_power`
  at `extensions/fhirpath/src/fhirpath/evaluator.cpp:5817` (now 5816)
  used `std::pow(base, exp)` which is IEEE-754 binary64. For exact
  integer results above ~2^53 the rendering fell back to scientific
  notation, and for results above ~1.8e308 std::pow returned +inf and
  native returned EMPTY. The Python fallback uses `Decimal.pow()`
  preserving exact digits. Reproducers: `(2).power(64)` native
  `'1.8446744073709552e+19'` vs fallback `'18446744073709551616.0'`;
  `(2).power(1024)` native `<EMPTY>` vs fallback `'179769...4137216.0'`;
  `(10).power(400)` native `<EMPTY>` vs fallback `'10000...0000.0'`.
  Surgical fix: added `multiplyIntegerMagnitudes()` helper at line 5818
  and `powerIntegerExactText()` helper at line 5853. For non-negative
  integer exponents on integer base values, compute the exact Decimal-
  shaped result via schoolbook multiplication on string digit magnitudes
  (capped at 10000 digits to prevent OOM). Applied in `fn_power` at line
  5926. Native extension rebuilt and copied. Same binary64-drift bug
  class as FP-07 SKEPTIC/HISTORIAN/EXPLORER (fn_toDecimal), FP-08
  SKEPTIC (convertQuantityUnit), FP-11 SKEPTIC (Quantity +/-/*),
  FP-11 HISTORIAN (fn_ln/exp/sqrt/log source_text).

  **(QA-002 MEDIUM §5.7.10/§4.1.8 RESOLVED):** Native C++ `fn_truncate`
  Quantity branch at `evaluator.cpp:5851-5856` rejected large-magnitude
  Quantity values (> INT64_MAX) via an int64 overflow guard. Per
  §4.1.8 Quantity value is Decimal — Decimal can represent these
  exactly. Reproducer: `(100000000000000000000 'g').truncate()` native
  `<EMPTY>` vs fallback `"100000000000000000000 'g'"`. Surgical fix at
  `evaluator.cpp:5971-5990`: routes Quantity truncate through
  `integralTextFromDecimalSource` + `makeQuantityMathResult` when
  source_text is available. Preserves int64 overflow guard for legacy
  non-source-text Quantity values.

  **(QA-003 MEDIUM §5.5.8 INTENDED):** Native C++ `fn_ceiling` and
  `fn_truncate` Quantity branches use `std::ceil`/`std::trunc` on the
  double `quantity_value`, losing the negative-zero sign. For
  `(-0.5 'g').ceiling()` native returns `"0 'g'"` while fallback returns
  `"-0 'g'"`. Per §5.5.8 the leading `-` in `(-)?#0.0#` is OPTIONAL;
  both `0` and `-0` are valid Decimal renderings. Native normalizes to
  `0` (more conservative); Python preserves `-0` from Decimal arithmetic
  (Decimal(-0.5).to_integral_value(ROUND_CEILING) returns Decimal('-0')).
  Both are mathematically equal. Classified INTENDED — no fix required.

  **(QA-004 MEDIUM §5.7.3 RESOLVED):** Native C++ `std::exp(-710)`
  returns a subnormal `4.47e-309` but `formatDecimalNumber`'s fallback
  path collapsed it to `'0.0'` via `setprecision(15) << std::fixed`.
  Python fallback `exp()` returned the raw subnormal float but the
  upstream fhirpathpy engine wrapped it in Decimal, producing a
  300+-character zero-padded string. Surgical fix at 3 layers: (a)
  Native `formatDecimalNumber` subnormal branch at `evaluator.cpp:7885`
  checks `abs(value) < 1e-300` (true subnormal range, well below smallest
  normal ~2.225e-308) and returns the source_text (shortest-round-trip
  from `normalizeDecimalMathSourceText`) when it round-trips. Uses
  `strtod` instead of `std::stod` because `std::stod` throws
  `std::out_of_range` for subnormals even when representable. (b) Native
  `normalizeDecimalMathSourceText` at `evaluator.cpp:2304-2336` re-
  renders integer-valued doubles via `snprintf("%.0f")` to convert
  `"-1e+01"` to `"-10"` so source_text passes formatDecimalNumber's
  "no scientific notation" fast path. (c) Python fallback `_to_str` at
  `fhir4ds/fhirpath/duckdb/udf.py:1947` and `:2547` (Decimal/float
  branches) checks `abs(item) < 1e-300` and uses `str(float(item))` to
  produce the shortest-round-trip scientific notation. Initial over-
  broad check (triggered for normal small values like `1e-6`) was
  caught by `test_quantity_to_string_uses_plain_decimal_not_scientific_
  notation` regression and tightened to `< 1e-300`.

  **(QA-005 MEDIUM §5.7.8 RESOLVED):** Python fallback `rround` at
  `fhir4ds/fhirpath/engine/invocations/math.py:387` used
  `degree = 10 ** Decimal(num2)` which overflowed the default Decimal
  context for precision >= ~28, raising `InvalidInputException`. Native
  C++ `roundDecimalSourceText` handled arbitrary precision correctly.
  Reproducer: `(1.5).round(50)` native `'1.5'` fallback EXCEPTION. Fix:
  replaced Decimal-power approach with text-based rounding algorithm at
  `math.py:392-470` that mirrors native `roundDecimalSourceText`. Uses
  `Decimal.as_tuple()` for canonical decomposition. Effective-precision
  cap at input's fractional digit count prevents OOM on malicious
  INT_MAX precision values. Strips trailing zeros per §5.5.8 (-)?#0.0#.

  **(QA-006 LOW §5.7.7 DEFERRED):** Native C++ `fn_power` uses `std::pow`
  returning double, losing Decimal precision on fractional-exponent
  inputs. Python fallback uses Decimal pow() preserving 28+ significant
  digits. `(2).power(0.5).power(2)` native `'2.0000000000000004'` vs
  fallback `'1.999999999999999999999999999'`. Deferred because
  implementing exact Decimal power for fractional exponents would
  require implementing arbitrary-precision Decimal arithmetic in C++
  (e.g. via GMP or porting Python's Decimal module), which is net-new
  functionality rather than a surgical fix. Integer-exponent case
  (QA-001) was the higher-impact subset and is now fixed.

  4 new regression tests (32 cases) added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_math_parity.py`:
  `test_power_integer_overflow_and_decimal_shape_fp11_explorer` (10
  cases),
  `test_truncate_quantity_large_magnitude_fp11_explorer` (4 cases),
  `test_round_large_precision_no_crash_fp11_explorer` (15 cases),
  `test_exp_subnormal_rendering_fp11_explorer` (3 cases). Native C++
  extension rebuilt and copied. Post-fix: EXPLORER probe 125/127 (was
  113/127); FHIRPath pytest 1490/1490 (was 1486, +4 new tests); full
  conformance 2822/2822 unchanged. Probe:
  `/mnt/d/fhir4ds/.temp/qa/fp11_explorer_2026_06_29/probe.py`.

- **FHIRPath FP-11 HISTORIAN iter 1 §5.7.3/§5.7.5/§5.7.6/§5.7.9 Math
  text-rendering parity (2026-06-28):** **1 ISSUE RESOLVED.** A fresh
  HISTORIAN systematic spec-walkthrough probe with 193 normative-rule
  cases across all 10 §5.7 functions (`abs`, `ceiling`, `exp`, `floor`,
  `ln`, `log`, `power`, `round`, `sqrt`, `truncate`), comparing bundled
  native C++ extension vs forced Python fallback through all 5 public
  UDFs. Coverage: §5.7.1 abs 25 cases (Integer/Decimal/Quantity,
  negative-zero), §5.7.2 ceiling 20 cases (toward +inf), §5.7.3 exp 12
  cases (e^x, integer/decimal input), §5.7.4 floor 19 cases (toward -inf),
  §5.7.5 ln 14 cases (ln(0)/ln(negative)→empty), §5.7.6 log 18 cases
  (base 0/1/negative rejection), §5.7.7 power 22 cases (Integer^Integer,
  0^0, negative^fractional→empty), §5.7.8 round 28 cases (default prec 0,
  half-up vs banker's, precision>0, Quantity), §5.7.9 sqrt 16 cases
  (sqrt(negative)→empty), §5.7.10 truncate 19 cases (toward zero).

  **(QA-001 MEDIUM §5.7.5/§5.7.3/§5.7.9/§5.7.6 RESOLVED):** Native C++
  `fn_ln`/`fn_exp`/`fn_sqrt`/`fn_log` (both inline `if (name == ...)` at
  `evaluator.cpp:3950/3967/3983` AND standalone
  `Evaluator::fn_ln`/`fn_log`/`fn_sqrt` at
  `evaluator.cpp:5721/5736/5806`) returned `FPValue::FromDecimal(<double>)`
  with empty `source_text`. The `toString` path at
  `evaluator.cpp:7596-7610` fell back to `std::setprecision(17)` rendering,
  producing 17-sig-digit binary64 expansions like `"2.3025850929940459"`.
  Python fallback `ln`/`log`/`sqrt` returned raw `float` (16 sig digits
  via `str()`); `exp` used `Decimal(format(result, ".17g"))` (17 sig digits).
  Numerical value identical between paths; divergence observable only via
  `fhirpath_text`. Root cause: same binary64-drift bug class as FP-07
  SKEPTIC/HISTORIAN/EXPLORER (`fn_toDecimal`), FP-08 EXPLORER/HISTORIAN/
  SKEPTIC (`convertQuantityUnit`), and FP-11 SKEPTIC (Quantity `+`/`-`/`*`).

  Surgical fix at 3 layers: (1) Added new reusable helper
  `normalizeDecimalMathSourceText(double&)` at `evaluator.cpp:2235` that
  produces shortest-round-trip text via precision 1..17 search (mirrors
  Python `str(float)` David Gay algorithm), appends `.0` for integer-
  valued results per §5.5.8 `(-)?#0.0#`, and does NOT re-parse the double
  (unlike `normalizeQuantityArithmeticSourceText`) because `std::log`/
  `exp`/`sqrt` already produce the same IEEE 754 nearest-double as Python
  `math.log`/`exp`/`sqrt`. (2) Applied at 6 native C++ call sites:
  `evaluator.cpp:3959/3980/4003/5734/5758/5824`. (3) Normalized Python
  fallback `exp()` at `fhir4ds/fhirpath/engine/invocations/math.py:288`
  to return raw `result` (matching `ln`/`log`/`sqrt`) instead of
  `Decimal(format(result, ".17g"))`. Native C++ extension rebuilt and
  copied to package + user install paths. Post-fix: HISTORIAN probe
  193/193 (was 192/193); FP-11 SKEPTIC probe 92/92 (unchanged);
  FHIRPath pytest 1486/1486 (was 1485, +1 new regression test
  `test_math_ln_exp_sqrt_log_text_parity_fp11_historian` with 15 cases);
  full conformance 2822/2822 unchanged. Probe:
  `/mnt/d/fhir4ds/.temp/qa/fp11_historian_2026_06_28/probe.py`.

- **FHIRPath FP-10 HISTORIAN iter 1 §5.6.6-§5.6.12 String Manipulation
  (Transform) (2026-06-28):** **0 NEW ISSUES — VERIFIED CLEAN.** A fresh
  HISTORIAN systematic spec-walkthrough probe with 129 normative-rule
  cases across all 7 functions (`upper`, `lower`, `replace`, `matches`,
  `replaceMatches`, `length`, `toChars`), comparing bundled native C++
  extension vs forced Python fallback through all 5 public UDFs.
  Coverage: §5.6.6 upper() 15 cases (ASCII/Unicode/German ß/Turkish İ/
  emoji/ligature decomposition), §5.6.7 lower() 15 cases, §5.6.8
  replace() 20 cases (literal substring, empty-pattern surrounds each
  char, empty substitution removes pattern, empty args, wrong types),
  §5.6.9 matches() 28 cases (search semantics, case-sensitivity,
  anchors, char classes, quantifiers, DOTALL single-line mode, Unicode,
  ReDoS protection, i/m flags), §5.6.10 replaceMatches() 25 cases
  (basic, $N/$0/$$ references, ${name} for both named-group matches and
  unknown-name literal passthrough, i/m flags, spec canonical numeric
  example), §5.6.11 length() 14 cases (code-point count not byte count),
  §5.6.12 toChars() 12 cases (Unicode code points not UTF-16 code units).
  Result: 129/129 native↔fallback parity; all canonical spec examples
  produce documented outputs; FP-10 SKEPTIC fix intact (spec canonical
  named-group example returns '30-11-1972' in fallback, empty {} in
  native — documented platform limitation per spec §5.6.10 note). Full
  conformance 2822/2822 unchanged. HISTORIAN methodology confirmed
  high-confidence verification on a surface that prior SKEPTIC pass had
  already hardened. Probe: `/mnt/d/fhir4ds/.temp/qa/fp10_historian_2026_06_28/probe.py`.

- **FHIRPath FP-10 SKEPTIC iter 1 §5.6.6-§5.6.12 String Manipulation
  (Transform) (2026-06-28):** **3 ISSUES RESOLVED.** A fresh SKEPTIC
  hypothesis-driven probe with 108 parity expressions across 7
  functions (`upper`, `lower`, `replace`, `matches`, `replaceMatches`,
  `length`, `toChars`) at the public DuckDB UDF boundary comparing
  bundled native C++ extension vs forced Python fallback. Coverage:
  Unicode case mapping (Greek final sigma Σ/σ, Turkish İ/ı, German ß/ẞ,
  Latin Ext ČŽŠ, ligature ﬃ), NFC vs NFD combining marks, supplementary
  plane emoji, embedded NUL byte, regex anchors/classes/case-sensitivity/
  multiline/i-flag, capture groups, empty-pattern character surrounding,
  non-overlapping literal replace, empty collection args, arity/type
  validation, ReDoS rejection, composed chains. Result: 107/108
  native↔fallback parity; 1 intentional platform-diff after fix.

  **(QA-001 HIGH §5.6.10 RESOLVED):** Spec canonical example with named
  groups `(?<name>...)` and named substitution `${name}` failed in
  BOTH backends, returning `{}` instead of `'30-11-1972'`. Root cause:
  Python `re` does NOT support ECMAScript-style `(?<name>...)` named
  groups (only Python-specific `(?P<name>...)`); the substitution
  conversion only handled numeric `$N` references. Native C++
  `std::regex` (ECMAScript syntax) also does NOT support named groups.
  Surgical fix in Python fallback `replace_matches` at
  `fhir4ds/fhirpath/engine/invocations/strings.py`: translates
  `(?<name>...)` → `(?P<name>...)` in the regex pattern (only when
  char after `(?<` is identifier start, skipping `(?<=`/`(?<!`
  lookbehind), and translates `${name}` → `\g<name>` only when the
  named group exists in the compiled pattern. Native C++ remains a
  documented platform limitation per spec note "FHIRPath does not
  prescribe a particular dialect, but recommends PCRE".

  **(QA-002 MEDIUM §5.6.10 RESOLVED):** Native↔fallback parity defect
  on out-of-range `$N` reference. Native returned `[]` (empty);
  Python fallback raised uncaught `re.error: invalid group reference N`
  → DuckDB surfaced as `InvalidInputException: Python exception
  occurred while executing the UDF`. Reproducer:
  `'abc'.replaceMatches('(b)', '$5')` → native `'ac'`, fallback
  EXCEPTION. Root cause: Python `re.sub` validates group references
  at substitution time; native `std::regex_replace` silently substitutes
  empty. Surgical fix: Python fallback's translator now consults the
  compiled pattern's `groups` attribute and only translates `$N` when
  N is in range `[0, num_groups]`; out-of-range references translate
  to empty string. Final `re.sub` wrapped in try/except as defensive
  guard.

  **(QA-003 MEDIUM §5.6.10 RESOLVED):** Native↔fallback parity defect
  on literal `$$`/`$$$`/`$<letter>` substitutions. Native treated
  them as literal `$`; fallback raised `re.error`. Root cause: the
  previous `$N → \g<N>` conversion left bare `$<other>` patterns for
  Python's parser to choke on. Surgical fix: single-pass regex
  translator now handles `$$` → literal `$` first, then `${name}`
  (only if name exists), then `$N` (only if N in range); everything
  else passes through as literal. The remaining unreachable cases
  (`'$$'` literal inside FHIRPath string literals) are blocked by
  the parser-level precheck at `udf.py:_INVALID_EXPR_PATTERNS` which
  matches `\$\$` anywhere in the expression including inside strings
  — documented as a separate parser-level issue out of FP-10 §5.6.10
  scope.

  3 new regression tests added to
  `fhir4ds/fhirpath/duckdb/tests/integration/test_string_transform_parity.py`:
  `test_string_transform_replace_matches_substitution_edge_cases_fp10_skeptic`
  (6 cases) and
  `test_string_transform_replace_matches_named_group_spec_example_fp10_skeptic`
  (2 cases). Full conformance 2822/2822 unchanged (ViewDefinition
  134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47). FHIRPath
  pytest 1482/1482 (was 1480). Probe artifacts:
  `.temp/qa/fp10_skeptic_2026_06_28/probe.py` (108 cases),
  `probe_spec.py`, `probe_round2.py`, `probe_round3.py`,
  `probe_native_named.py`.

  **NOT A BUG Registry (FP-10):**
  - Native C++ `std::regex` (ECMAScript syntax) does not support
    named groups `(?<name>...)`. This is a documented platform-level
    limitation per FHIRPath §5.6.10 note. The Python fallback now
    supports them via `(?<name>...)` → `(?P<name>...)` translation.
    The 1 remaining parity diff (named-group spec example) is
    intentional platform flexibility, not a regression.
  - `'$$'` inside FHIRPath string literals is rejected by the
    parser-level precheck `\$\$` pattern at
    `fhir4ds/fhirpath/duckdb/udf.py:_INVALID_EXPR_PATTERNS`. This
    is a separate parser-level issue and out of FP-10 §5.6.10 scope.

- **FHIRPath FP-09 HISTORIAN iter 1 fresh spec walkthrough §5.6.1-§5.6.5
  String Search (2026-06-28):** **VERIFIED CLEAN.** A systematic
  HISTORIAN spec-walkthrough enumerated every normative rule from
  FHIRPath v2.0.0 §5.6.1-§5.6.5 across all five functions
  (`indexOf`, `substring`, `startsWith`, `endsWith`, `contains`) with
  68 targeted test cases at the public DuckDB UDF boundary comparing
  bundled native C++ extension vs forced Python fallback. Coverage
  included the canonical trap for this surface — the empty-STRING vs
  empty-COLLECTION distinction: per spec `indexOf('')→0`,
  `startsWith('')→true`, `endsWith('')→true`, `contains('')→true`
  (empty string arguments produce defined behavior), while
  `s.indexOf(missing)→{}`, `s.startsWith(missing)→{}` (empty collection
  arguments propagate empty). Both paths handle this correctly because
  `arg.empty()` (C++) and `util.is_empty(...)` (Python) check
  FHIRPath-collection emptiness, and the FHIRPath literal `''`
  evaluates to a 1-item collection containing an empty string, not an
  empty collection. Additional coverage: 0-based indexOf + -1 not-found,
  substring 1-arg/2-arg forms, out-of-range/negative start, partial-
  remaining length, length<=0 → empty string (FP-09 EXPLORER fix
  intact), Unicode scalar positions (é/😀), case-sensitivity per §8.7,
  multi-element input row-resilience. Result: 0 native↔fallback diffs
  across `scalar`/`text`/`json`/`bool`/`number` UDF wrappers. Full
  conformance 2822/2822 unchanged. Independently confirms prior FP-09
  SKEPTIC archive (60+ cases, 0 issues). The HISTORIAN methodology is
  the right tool for spec-conformance verification after a SKEPTIC
  first-pass; produces zero false positives when the surface is already
  clean. Probe artifact: `.temp/qa/fp09_historian_2026_06_28/probe.py`.
- **FHIRPath FP-08 EXPLORER iter 1 fresh pathological fuzz §5.5.7-§5.5.9
  (2026-06-28):** **2 ISSUES RESOLVED.** A fresh EXPLORER fuzz pass threw
  241 pathological expressions across 10 vector groups at all 6 normative
  §5.5.7-§5.5.9 functions (toQuantity/convertsToQuantity/toString/
  convertsToString/toTime/convertsToTime) at the public DuckDB UDF
  boundary comparing bundled native C++ extension vs forced Python
  fallback. Vector coverage: extreme Quantity values, UCUM unit conversion
  edges, calendar-duration conversion factors, composed round-trip
  (`'1.5'.toQuantity().toString().toQuantity().toString()`), leap-second
  Time values, polymorphic choice-type conversions, malformed inputs,
  ResourceNode unwrap edges, decimal precision preservation across
  composed conversions. Found 2 native↔fallback parity defects at the
  §5.5.7 toQuantity(unit) boundary, both in native
  `convertQuantityUnit` at `extensions/fhirpath/src/fhirpath/evaluator.cpp`:

  **(QA-001 HIGH §5.5.7):** Native `(1 'Cel').toQuantity('[degF]')`
  returned `"-1 '[degF]'"` (arithmetic nonsense) while the Python
  fallback returned empty. Root cause: the UCUM table at
  `extensions/fhirpath/src/include/shared/ucum_units.hpp:108-109`
  marks `[degF]` with a sentinel factor of -1.0 ("sentinel: handled
  specially by caller") but no offset-handling branch existed in
  `convertQuantityUnit`. Native thus computed `(1 * 1.0) / -1.0 = -1`
  instead of either the correct `33.8 '[degF]'` (applying
  `°F = °C × 9/5 + 32`) or empty. Spec citations: §5.5.7 toQuantity
  unit conversion "according to the unit conversion rules specified
  by UCUM"; §5.5.7 MAY clause "may return empty when the unit argument
  is used and it is different than the input quantity unit." Surgical
  fix added `isOffsetTemperatureUnit()` helper (recognizes Cel,
  [degF], degF, K, degC, [degC], degRe, [degRe]) and an early-return
  guard in `convertQuantityUnit` that rejects any cross-unit
  temperature conversion when either operand is in this set.
  Same-unit passthrough still works via the earlier identity check.

  **(QA-002 MEDIUM §4.1.8/§6.1/§6.7):** Native `(1 year).toQuantity('s')`
  returned `"31556952 's'"` (correct arithmetic but spec-category-wrong)
  while the Python fallback returned empty. Root cause: native
  `convertQuantityUnit` used a flat UCUM table where `year` (factor
  31556952, base 's') and `'s'` (factor 1, base 's') shared the same
  base. The Python fallback's `conv_unit_to` at
  `fhir4ds/fhirpath/engine/nodes.py:520-553` separates time-valued
  units into discrete groups (`_year_month_conversion_factor` for
  years/months; `_weeks_days_and_time` for weeks/days/hours/minutes/
  seconds/milliseconds) and rejects cross-group conversions. Per
  FHIRPath §4.1.8 and §6.1.1, calendar durations and UCUM definite
  durations are distinct categories above the second precision
  (`1 year = 1 'a'` is false); cross-category conversion must fail.
  Surgical fix added `isYearMonthDurationUnit()` and
  `isWeeksDaysTimeDurationUnit()` helpers and an early-return guard
  that rejects cross-group conversions.

  Both fixes verified by 2 new regression tests (21 cases total) in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`:
  `test_offset_temperature_cross_conversion_rejects_in_both_backends_fp08_explorer`
  and `test_calendar_vs_ucum_duration_group_separation_fp08_explorer`.
  Native C++ extension rebuilt and copied to both package
  (`fhir4ds/fhirpath/duckdb/extensions/`) and user install
  (`~/.duckdb/extensions/v1.5.2/linux_amd64/`) paths. Full conformance
  2822/2822 unchanged (ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47). Conversion parity 39/39 (37 existing + 2 new).
  Probe artifacts: `.temp/qa/fp08_explorer_2026_06_28/probe.py` (241
  cases) and `verify_diffs.py` (10-case focused verification).

  **Same native-over-permissive bug class as FP-08 SKEPTIC** (calendar
  keyword trailing junk) — the lesson is unchanged: any cross-unit
  conversion edge requires explicit category/dimension validation, not
  just base-unit equality. The flat `ucum_units.hpp` table cannot
  represent offset-based conversions (temperature) or category-distinct
  semantics (calendar vs UCUM); the new guards are surgical workarounds.
  Deeper redesign to group units by dimension/category explicitly is
  documented design debt, not a bug. Probe hygiene: root-pin
  `sys.path.insert(0, "/mnt/d/fhir4ds")` plus `assert fhir4ds.__file__`
  guard, per FP-08 HISTORIAN archive.

  The 6 remaining probe "diffs" are all `Observation.valueDecimal.*`
  paths where the FHIR data uses `valueDecimal` (NOT a valid R4 choice
  type — choice type list at
  `fhir4ds/fhirpath/models/r4/choiceTypePaths.json` is
  `['Quantity', 'CodeableConcept', 'String', 'Boolean', 'Integer',
  'Range', 'Ratio', 'SampledData', 'Time', 'DateTime', 'Period']`).
  These are parity drift on invalid FHIR R4 data, not in scope for
  FP-08 §5.5.7. Documented in FP-08 HISTORIAN archive.

- **FHIRPath FP-08 HISTORIAN iter 1 fresh run §5.5.7-§5.5.9 spec
  walkthrough (2026-06-28):** **VERIFIED CLEAN.** A 139-case
  systematic HISTORIAN spec-walkthrough enumerated every normative
  rule across all six functions (toQuantity/convertsToQuantity/
  toString/convertsToString/toTime/convertsToTime) at the public
  DuckDB UDF boundary, comparing bundled native C++ extension vs
  forced Python fallback. Found **zero new non-terminal
  CRITICAL/HIGH/MEDIUM issues** on valid FHIR data. The probe
  correctly distinguished in-scope FP-08 defects from the
  pre-existing FP-04 choice-type navigation asymmetry: an apparent
  diff on `Observation.valueDecimal.toQuantity()` was diagnosed as
  invalid FHIR R4 data (`decimal` is not in the `Observation.value[x]`
  choice type list per `fhir_model.choiceTypePaths`), not an FP-08
  §5.5.7 defect. On every valid FHIR choice type
  (`valueInteger`/`valueString`/`valueBoolean`/`valueQuantity`) both
  paths agree. No source changes, no new tests. Full conformance
  2822/2822 unchanged. The HISTORIAN methodology is the right tool
  for spec-conformance verification after prior SKEPTIC/HISTORIAN/
  EXPLORER passes have hardened the surface; produces zero false
  positives when the surface is already clean.
- **FHIRPath FP-08 SKEPTIC iteration 1 fresh rerun §5.5.7
  toQuantity(unit) binary64 noise propagation (2026-06-28):**
  **VERIFIED CLEAN (after surgical mask in native evaluator):**
  Native `(0.1 'g' + 0.2 'g').toQuantity('mg')` returned
  `"300.00000000000006 'mg'"` while the Python fallback returned
  `"300 'mg'"`. Root cause spans two layers: native Quantity
  arithmetic at `extensions/fhirpath/src/fhirpath/evaluator.cpp:6940-6998`
  uses `double` not `Decimal` (FP-11 §5.7 scope), and the FP-08
  EXPLORER `convertQuantityUnit` fix at `evaluator.cpp:1883-1955`
  only normalized the final rendered value at precision 17 (which
  is the shortest round-trip for noisy doubles). Surgical fix at
  `evaluator.cpp:1920` caps the shortest-round-trip search at
  precision 15 (IEEE 754 double's guaranteed-unique significant
  digits) and adds a `%.15g` fallback render. The Python fallback
  in this subproject (`fhir4ds/fhirpath/engine/invocations/misc.py`)
  was already correct — it uses `Decimal` arithmetic via
  `_quantity_add_or_sub` and `conv_unit_to`, so no Python changes
  were needed. The native vs fallback parity at the §5.5.7 boundary
  is now clean. The §5.7 root cause (native `+`/`-`/`*` Quantity
  arithmetic using `double`) is deferred to FP-11 SKEPTIC. 1 new
  regression test in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`.
  Methodology note for future agents: default DuckDB connection
  silently falls back to Python UDFs because the dev extension is
  unsigned — must use `config={"allow_unsigned_extensions": True}`
  and verify `fhirpath_predicate` UDF presence to confirm native.

- **FHIRPath FP-08 HISTORIAN §5.5.7/§5.5.9 toQuantity precision + toTime
  dot separator (2026-06-28):**
  **VERIFIED CLEAN (after surgical fixes):** A HISTORIAN systematic
  spec-walkthrough probe of 148 expressions enumerated every normative
  rule from FHIRPath v2.0.0 §5.5.7-§5.5.9 (toQuantity/convertsToQuantity/
  toString/convertsToString/toTime/convertsToTime) at the public DuckDB
  UDF boundary comparing bundled native C++ extension vs forced Python
  fallback. Found and fixed 2 MEDIUM-severity defects:

  **(QA-001 MEDIUM §5.5.7/§4.1.4/§5.5.8):** Native C++ `fn_toQuantity`
  String-decimal branch at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:fn_toQuantity` (around
  line 4935-5007) lost precision for `'0.0'.toQuantity().toString()`:
  returned `"0 '1'"` (strips trailing `.0`) instead of `"0.0 '1'"`.
  Root cause: the String-decimal branch constructed the output `FPValue`
  without setting `source_text`. Downstream `toString()` then used
  `formatDecimalNumber` default branch which uses
  `std::ostringstream << std::setprecision(17)` — this strips trailing
  `.0` from integral-valued decimals. Fix: capture the parsed numeric
  substring into `num_text` BEFORE the unit-parse loop advances `idx`;
  apply the same Python-`Decimal(str)` normalization that FP-07 SKEPTIC
  established for `fn_toDecimal` (drop leading `+`, collapse leading
  zeros); assign `v.source_text = num_text`. Same binary64-drift bug
  class as FP-07 SKEPTIC/HISTORIAN/EXPLORER (toDecimal branches) —
  String-decimal branch was the missed sibling for the Quantity path.

  **(QA-002 MEDIUM §5.5.9):** Python fallback `FP_Time('10.30')`
  returned a partial time `'10'` instead of rejecting the input
  entirely. `'10.30'.toTime()` returned `['10']` in fallback vs `[]`
  in native C++. Root cause: `FP_Time.__new__` at
  `fhir4ds/fhirpath/engine/nodes.py:1152-1167` validated hour/minute/
  second ranges but did not check that a fraction (millisecond)
  component is permitted only when preceded by hour, minute, AND
  second. The regex `timeRE` `^T?([0-9]{2})(?::([0-9]{2}))?(?::([0-9]{2}))?(?:\.([0-9]+))?$`
  matched `'10.30'` with hour=`'10'`, fraction=`'30'`, minute=None,
  second=None. The `__str__` method then returned just `'10'`. Fix:
  added `if fraction is not None and (minute is None or second is None):
  return None` in `FP_Time.__new__`. Same audit pattern as the FP-08
  SKEPTIC `to_time` Time-literal passthrough fix — any Python fallback
  temporal constructor that accepts partial precision must validate
  component ordering.

  Both fixes verified by 2 new regression tests in
  `test_conversion_parity.py::test_string_decimal_to_quantity_preserves_precision_fp08_historian`
  (6 parametrized cases) and
  `test_string_to_time_rejects_dot_separator_fp08_historian` (4 cases).
  148-case post-fix probe shows 0 native↔fallback diffs. Native C++
  extension rebuilt and copied to both package and user install paths.
  Full conformance 2822/2822 unchanged. Probe artifacts:
  `.temp/qa/fp08_historian_2026_06_28/probe.py`.

  **Probe hygiene note:** The initial probe inadvertently imported a
  stale globally-installed `fhir4ds` wheel from
  `~/.local/lib/python3.10/site-packages/fhir4ds/` because
  `sys.path[0]` resolved to `/tmp` when the probe was launched from
  there. This produced 11 phantom diffs (the prior SKEPTIC fixes were
  absent from the older installed wheel). The fix was a one-line
  `sys.path.insert(0, "/mnt/d/fhir4ds")` at the top of the probe plus
  an `assert fhir4ds.__file__.startswith(...)` guard. The same root-
  pinning discipline is already documented for prior probes
  (`.temp/qa/fp14_explorer_fresh_probe.py` etc.); this iteration
  reinforces it as a universal rule for any probe that runs from
  outside the workspace root.

- **FHIRPath FP-08 SKEPTIC §5.5.7-§5.5.9 Quantity/String/Time conversion
  native↔fallback parity (2026-06-28):**
  **VERIFIED CLEAN (after surgical fixes):** A SKEPTIC hypothesis-driven probe
  of 151 expressions across all 6 normative §5.5.7-§5.5.9 functions
  (toQuantity/convertsToQuantity/toString/convertsToString/toTime/
  convertsToTime) found 4 native↔fallback parity defects at the public DuckDB
  UDF boundary. All 4 are spec-grounded §5.5.7-§5.5.9 violations; all 4 are
  now fixed and covered by regression tests. Pre-test SKEPTIC hypotheses
  H1-H8: H1 (JsonVal-Integer/Decimal effectiveType dispatch) REJECTED;
  H2 (Boolean→Quantity value materialization — true→1.0 '1' vs 1 '1')
  REJECTED — works correctly via existing source_text path; H3 (Integer
  →Quantity source_text precision above 2^53) REJECTED; H4 (String parsing
  per spec regex) CONFIRMED-AND-FIXED as QA-002+QA-004; H5 (Time toString
  format) REJECTED; H6 (DateTime partial precision) REJECTED; H7
  (String/literal Time handling) CONFIRMED-AND-FIXED as QA-001+QA-003; H8
  (native↔fallback parity) CONFIRMED — 4 distinct diffs found and fixed.

  **(QA-001 HIGH §5.5.9):** Forced Python fallback `to_time()` at
  `fhir4ds/fhirpath/engine/invocations/misc.py:528-549` failed Time-literal
  passthrough. `@T10:30.toTime()` returned `[]` in fallback vs `['10:30']`
  in native; `@T10:30.convertsToTime()` returned `false` vs `true`. Root
  cause: `to_time()` unconditionally wrapped value in `nodes.FP_Time(value)`
  which returns None for non-str inputs. Fix: added explicit
  `isinstance(value, nodes.FP_Time)` branch before constructor call.

  **(QA-002 MEDIUM §5.5.7):** Native `fn_toQuantity` String-bare-keyword
  path at `extensions/fhirpath/src/fhirpath/evaluator.cpp:4974-4986`
  accepted trailing junk after a calendar duration keyword. Reproducer:
  `'4 days extra'.toQuantity()` returned `[\"4 'days extra'\"]` in native vs
  `[]` in fallback. Root cause: bare-keyword path took `s.substr(idx)` as
  unit, trimmed trailing whitespace, then only rejected via
  `isBareDurationCode` — fall-through kept non-keyword strings as unit. Fix:
  removed trailing-whitespace trim; added
  `if (!isBareDurationKeyword(unit_str)) return {};` after existing
  bare-code check.

  **(QA-003 MEDIUM §5.5.9):** Native `fn_toTime` and `fn_convertsToTime`
  accepted malformed time strings with trailing colon. Reproducer:
  `'10:'.toTime()` returned `['10:']` in native vs `[]` in fallback. Root
  cause: lenient `if (check_pos+2 <= s.size()) check_pos += 2;` advanced
  past `:` even when 2 digits weren't present. Fix: replaced with strict
  digit-presence verification at each step; also added dangling-`.` rejection.
  Applied to BOTH fn_toTime (evaluator.cpp:7856-7886) and fn_convertsToTime
  (evaluator.cpp:7540-7568).

  **(QA-004 LOW §5.5.7):** Forced Python fallback `to_quantity()` at
  `fhir4ds/fhirpath/engine/invocations/misc.py:413-419` (original line
  numbers) accepted ANY bare alpha sequence as a unit via the final elif
  branch. Reproducer: `'0xFF'.toQuantity()` returned `0 'xFF'` in fallback
  vs `[]` in native. Root cause: final elif wrapped any unmatched alpha
  token as quoted unit. Fix: removed the over-permissive elif branch. Bare
  non-keyword alpha sequences now fall through to empty result.

  All 4 fixes verified by 4 new regression tests in
  `test_conversion_parity.py` (31/31 conversion parity tests pass) and a
  68-case post-fix probe (0 native↔fallback diffs). Native C++ extension
  rebuilt; copied to both package and user install paths. Full conformance
  2822/2822 unchanged. Probe artifact: `.temp/qa/fp08_skeptic/probe.py`.
  Same Python-fallback-vs-native parity bug class as FP-07 EXPLORER
  (Unicode-digit regex), FP-04 SKEPTIC (ofType primitive subtypes), and
  FP-02 EXPLORER (UDF row-resilience) — the lesson is unchanged: any
  Python fallback function that wraps values in `nodes.FP_*(value)`
  constructors must explicitly passthrough same-type inputs per spec
  passthrough rules, because FP_* constructors return None for non-str
  inputs. The same audit pattern applies to `to_date`, `to_date_time`,
  and any future Python fallback `to_*` function — each must check
  `isinstance(value, FP_*)` BEFORE the constructor call.

- **FHIRPath FP-07 EXPLORER §5.5.6 toDecimal/convertsToDecimal Unicode-digit
  regex drift (2026-06-28):**
  **VERIFIED CLEAN (after Python-fallback fix):** An EXPLORER fuzz pass
  threw 177 pathological expressions at all 6 normative §5.5.4-§5.5.6
  functions in 18 vector groups (extreme-precision Decimals, leap-year
  boundaries, timezone edges, leap-second, Unicode in date strings,
  polymorphic choice-type, malformed inputs, negative years, ResourceNode
  unwrap edges, decimal precision round-trip) at the public DuckDB UDF
  boundary comparing bundled native C++ extension vs forced Python
  fallback. Found 1 HIGH-severity defect: the Python fallback regexes at
  `fhir4ds/fhirpath/engine/invocations/misc.py:15-17`
  (`intRegex`/`numRegex`/`longDecimalStringRegex`) used `\d` which is
  Unicode-aware in Python's `re` module, matching full-width digits
  U+FF10-U+FF19, Arabic-Indic U+0660-U+0669, Devanagari U+0966-U+096F,
  etc. Native C++ `isFHIRPathDecimalString` at evaluator.cpp:656-680
  correctly uses `std::isdigit(static_cast<unsigned char>(...))` which is
  ASCII-only. The asymmetry produced `'1.５'.toDecimal()` returning empty
  in native C++ vs `[1.5]` in the Python fallback. Spec citation:
  FHIRPath §5.5.6 toDecimal()/convertsToDecimal() regex
  `(\\+|-)?\\d+(\\.\\d+)?`; the ANTLR grammar DIGIT fragment is `[0-9]`
  (ASCII only), so the spec-text `\d` means ASCII digits, not Unicode
  digits. Surgical single-character-each fix: replace `\d` with `[0-9]`
  in three regex literals (the `numRegex` and `longDecimalStringRegex`
  are §5.5.6 / FP-07 Long support; the `intRegex` fix is the same one-
  character bug class in the same source file for §5.5.3 toInteger —
  fixing all three together restored native↔fallback parity without
  touching out-of-scope `quantity_regex` §5.5.7). 1 regression test
  added in `test_conversion_parity.py::test_unicode_digit_string_to_decimal_rejects_non_ascii_fp07_explorer`.
  Native C++ unchanged (already correct); no rebuild required. Same
  Python-re-Unicode-default bug class as the FP-10 Unicode case-table
  drift, now surfacing in the §5.5.6 conversion regex path. The general
  lesson: any Python `re.compile(r"...\\d...")` regex that validates
  FHIRPath lexical syntax (Integer, Decimal, Quantity, Long) MUST use
  `[0-9]` to match the ANTLR grammar DIGIT fragment `[0-9]` — Python's
  Unicode-aware `\d` is a parity trap. Probe artifacts:
  `.temp/qa/fp07_explorer_pathological/probe.py` (177 cases) +
  `results.json`.

- **FHIRPath FP-07 HISTORIAN §5.5.6 toDecimal Integer-effective-type
  precision drift (2026-06-28):**
  **VERIFIED CLEAN (after native fix):** A systematic HISTORIAN
  spec-walkthrough pass ran 184 probe cases (116 basic + 68 deep)
  across all 6 normative §5.5.4-§5.5.6 functions
  (toDate/convertsToDate/toDateTime/convertsToDateTime/toDecimal/
  convertsToDecimal); every normative rule from the FHIRPath v2.0.0
  spec was enumerated as a discrete test case at the public DuckDB
  UDF boundary comparing bundled native C++ extension vs forced
  Python fallback. Found 1 HIGH-severity defect in native C++
  `fn_toDecimal` Integer effective-type branch at
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:4669-4671`:
  JsonVal-wrapped FHIR integer primitives above 2^53 lost precision
  through binary double conversion AND produced scientific notation in
  `toString()`. Reproducers: `9223372036854775807.toDecimal().toString()`
  returned `['9.2233720368547758e+18']` native vs
  `['9223372036854775807.0']` fallback; `9007199254740993.toDecimal()
  .toString()` returned `['9007199254740992.0']` native (rounded down)
  vs `['9007199254740993.0']` fallback (exact). Spec violations:
  §5.5.6 Integer/Long promotion to Decimal, §4.1.4 fixed-precision
  decimal formats, §5.5.8 Decimal toString uses decimal digit notation.
  Single-branch surgical fix sets `source_text` from canonical JSON
  integer text via existing `jsonNumberText()` helper, appending `.0`
  for Decimal surface per §4.1.8. The Python fallback
  `fhir4ds/fhirpath/engine/invocations/misc.py::to_decimal` was already
  correct via `Decimal(int_value)` which preserves exact digits
  natively. 1 regression test added in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py::
  test_fhir_integer_primitive_to_decimal_preserves_exact_text_fp07_historian`.
  Native C++ ext loaded with duckdb 1.5.2 + `allow_unsigned_extensions=True`;
  forced Python fallback via `evaluate_fhirpath()` direct and
  `fhirpath_json_udf` UDF layer (`duckdb.__version__="0.0.0-forced-python-fallback"`
  trick). 0 result/validity/parity diffs on 184 cases after fix.
  Independently confirms prior FP-07 SKEPTIC archive (2 bugs, 122
  expressions), FP-07 EXPLORER archive (Long boundary issues fixed),
  FP-07 HISTORIAN archive (string Long Decimal conversion fixed), and
  FP-07 SKEPTIC archive (Date/DateTime format + Long Decimal conversion
  fixed). Probe artifacts: `.temp/qa/fp07_historian_2026_06_28/probe.py`
  (116 cases) + `deep_probe.py` (68 cases). Full conformance 2822/2822
  unchanged (ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47).
- **FHIRPath FP-06 EXPLORER §5.5.1-§5.5.3 iif/Boolean/Integer conversion
  pathological-input fuzz (2026-06-28):**
  **VERIFIED CLEAN:** A fuzz pass threw 195 pathological expressions at all
  5 normative §5.5.1-§5.5.3 functions (iif/toBoolean/convertsToBoolean/
  toInteger/convertsToInteger) in 20 vector groups covering deeply nested
  iif (3-deep + 10-deep), iif with empty criterion (`iif({}, ...)` returns
  otherwise-result), criterion error propagation, lazy branch evaluation
  (errors in unselected branches are suppressed), `and`/`or` short-circuit
  (`&&`/`||` correctly rejected — not FHIRPath grammar), Unicode/case/padded
  strings in toBoolean (`TrUe`, `T/t`, `YES/Yes`, `Y/N/F`, `1.0/0.0`,
  `'true '/ false'`, `Vrai` rejected, `2` rejected), extreme integer strings
  (max-int32 `2147483647`, overflow `2147483648`, min-int32 `-2147483648`,
  underflow `-2147483649`, `0`/`00`/`+5`/`-0`/`9999999999`/`1.5` rejected/
  `''` rejected), type-mixed conversions (Date/DateTime/Quantity/Code→
  Integer/Boolean all return empty per §5.5 conversion table — no silent
  coercion through `toString()`/`toNumber()`), polymorphic choice-type
  conversions (`value[x].toInteger()`/`.toBoolean()`), ResourceNode unwrap
  edges, empty-collection propagation, multi-element input → error per
  §5.5 intro (row-resilient in public UDF wrapper), invalid arity (0/1/4-arg
  iif, conversion functions with extra args), iif criterion as non-Boolean
  singleton (per §4.5 non-empty singleton→true — prior FP-06 SKEPTIC fix
  intact), chained iif+conversions, iif in where/select/count, `$index`/
  `$this` preservation, `otherwise={}` form. Native C++ ext loaded with
  duckdb 1.5.2 + `allow_unsigned_extensions=True`; forced Python fallback
  via `evaluate_fhirpath()` direct and `fhirpath_json_udf` UDF layer
  (`duckdb.__version__="0.0.0-forced-python-fallback"` trick from
  `test_conversion_parity.py`). 0 result/validity/parity diffs on 195 cases
  at the public DuckDB UDF boundary. Independently confirms prior FP-06
  SKEPTIC archive (0 bugs, 130 expressions) and FP-06 HISTORIAN archive
  (0 bugs, 183 expressions). Probe artifacts:
  `.temp/qa/fp06_explorer_pathological/probe.py` (126 cases) + 3 ad-hoc
  probe batches (69 more). Full conformance 2822/2822 unchanged
  (ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47).
- **FHIRPath FP-06 SKEPTIC §5.5.1-§5.5.3 iif/Boolean/Integer conversion
  hypothesis-driven audit (2026-06-28):**
  **VERIFIED CLEAN:** A SKEPTIC predict-then-probe pass ran 130
  hypothesis-driven expressions across all 5 normative §5.5.1-§5.5.3
  functions (`iif`, `toBoolean`, `convertsToBoolean`, `toInteger`,
  `convertsToInteger`) comparing native C++ (loaded with
  `allow_unsigned_extensions=True` on duckdb 1.5.2) vs forced Python
  fallback (`evaluate_fhirpath()` direct + `fhirpath_json_udf` UDF
  layer). All 8 pre-test SKEPTIC hypotheses were empirically REJECTED:
  (H1) iif empty-criterion-otherwise routing is correct; (H2) iif
  short-circuit lazy evaluation is correct — `iif(true, 'live',
  nonexistentFunction())` returns `['live']` with no raise; (H3) iif
  multi-element input — C++ evaluator throws `FHIRPathSpecError` per
  §5.5 intro and UDF wrapper suppresses to empty (documented row-
  resilience mandate at `fhirpath_extension.cpp:865-868`); Python UDF
  wrapper mirrors via `_STRICT_MODE` pattern in `udf.py`; both paths
  produce identical observable behavior at UDF boundary; (H4) iif
  multi-element criterion — same resolution as H3; (H5) `iif(0, ...)`
  singleton non-Boolean criterion returns true-result per §4.5
  singleton-Boolean conversion (regression-verified prior FP-06
  SKEPTIC fix from 2026-06-12 intact); (H6) toBoolean String
  acceptance — correct per spec §5.5.2 table
  (`'true','t','yes','y','1','1.0'`→true, `'false','f','no','n','0',
  '0.0'`→false, case-insensitive); (H7) toInteger Decimal coercion —
  correct per §5.5 conversion table (Decimal→Integer is `-` no
  conversion, both paths return empty); (H8) toInteger Int32-range
  overflow — correct, both paths reject `'2147483648'`/
  `'-2147483649'`. Spec text fetched and verified normatively from
  http://hl7.org/fhirpath/N1/index.html §5.5.1-§5.5.3. Result: 0
  result/validity/parity diffs on 130 cases. Fhirpath integration
  tests 334/334. NOT A BUG Registry additions: (a) the spec §5.5.2
  toBoolean String table DOES include `'t'/'f'/'yes'/'no'/'y'/'n'/
  '1.0'/'0.0'` — initially appeared suspect but is normative; (b)
  per §5.5 conversion table, Decimal→Integer has no conversion
  defined, so `1.0.toInteger()` → empty is spec-correct; (c) iif
  short-circuit semantics are correctly implemented in both paths;
  (d) multi-element input/conversion errors at the UDF layer
  intentionally return empty/NULL (row-resilience mandate) — both
  paths implement this consistently with `FHIRPATH_STRICT_MODE=1`
  opt-in. Probe artifacts: `.temp/qa/fp06_skeptic/probe{,2,3,4,5}.py`
  (130 cases). Full conformance 2822/2822 unchanged.
- **FHIRPath FP-05 EXPLORER §5.3/§5.4 pathological-input fuzz (2026-06-28):**
  **VERIFIED CLEAN:** A fuzz pass threw 108 pathological expressions at
  all 11 §5.3/§5.4 functions across 8 vector groups (extreme indices
  including INT_MAX-ish and Decimal/Boolean-typed; pathological sizes
  from empty/single/1200-element; mixed-type collections through set
  ops; ResourceNode unwrap on Quantity/Decimal/DateTime; polymorphic
  Quantity equality 1 'cm' vs 10 'mm'; Unicode strings with combining
  forms; deeply chained skip/take/first/last; empty-other args). 0
  native/fallback parity divergences, 0 validity errors, 0 crashes.
  Spec-verification catches worth recording in the NOT A BUG Registry:
  (a) `1 'cm' = 10 'mm'` returns `true` per FHIRPath §6.1 UCUM
  canonical conversion (NOT a bug — verified against FHIRPath v3.0.0
  build spec which clarifies the long-standing intent of v2.0.0);
  (b) `combine(other, false)` does NOT dedup despite the `false` flag,
  because the v2.0.0-spec `combine` has no `preserveOrder` parameter
  (it is a v3.0.0 tech-correction addition) — the engine accepts the
  optional Boolean for forward-compat type-validation but ignores it
  for behavior, which is the correct v2.0.0 conformance stance;
  (c) FHIRPath string equality is codepoint-sensitive and
  case-sensitive — `names.distinct()` on `['abc','abc','Ábc','ábc']`
  yields `['abc','Ábc','ábc']` with NO Unicode normalization;
  (d) Integer-vs-Decimal equality is type-strict —
  `ints.intersect(decs)` on `[1,2,3]` and `[1.5,2.5,3.5]` yields `[]`
  even though both are numeric. Probe artifacts:
  `.temp/qa/fp05_explorer_pathological_probe.py`,
  `.temp/qa/fp05_explorer_inspect_values.py`,
  `.temp/qa/fp05_explorer_edge2.py`. Full conformance 2822/2822
  unchanged.
- **FHIRPath FP-05 HISTORIAN §5.3 nested-array indexer parity drift
  (2026-06-28):**
  **DEFERRED:** Native C++ `Evaluator::evalMemberAccess` recursively
  flattens nested JSON arrays via the `add_flattened` lambda in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp:2324-2345`, so a
  resource with a non-FHIR nested-array field such as
  `{"resourceType":"Observation","matrix":[["x","y"],["z"]]}` yields
  divergent results between native and forced Python fallback:
  `matrix[0]` → native `['x']` (recurses into inner array), fallback
  `['["x","y"]']` (treats inner array as a single element);
  `matrix.count()` → native `[3]`, fallback `[2]`; same divergence on
  `matrix.first()`, `matrix.last()`, `matrix.tail()`, and the `[index]`
  operator on the result. The recursion is load-bearing for FHIR R4
  `array<primitive>` flattening (e.g. `Patient.name.given` from
  `[{given:["John","Q"]}]` to `["John","Q"]`) and cannot be removed
  without regressing conformant FHIR data. Deferred because FHIRPath
  §2.1.1 mandates flat collections (the spec is silent on
  collections-of-collections), FHIR R4 forbids nested-array resource
  JSON, and aligning native with fallback would require coordinated
  native+fallback changes plus new parity tests for a case that cannot
  occur with conformant FHIR resources. Probe artifacts:
  `.temp/qa/fp05_historian_iteration_probe.py`,
  `.temp/qa/fp05_historian_edge_probe.py`. Full conformance 2822/2822
  unchanged; revisit only if FHIR R5 introduces nested-array primitives
  or the engine is repurposed for non-FHIR JSON.
- **FHIRPath FP-05 HISTORIAN §5.3/§5.4 exhaustive verification
  (2026-06-28):**
  **VERIFIED CLEAN:** A systematic section-by-section HISTORIAN pass
  across all 11 §5.3/§5.4 functions (`[index]`, `single`, `first`,
  `last`, `tail`, `skip`, `take`, `intersect`, `exclude`, `union`/`|`,
  `combine`) verified every normative rule from the FHIRPath spec
  (http://hl7.org/fhirpath §5.3, §5.4) with 115+ targeted test cases
  comparing native C++ vs forced Python fallback. Coverage: in-range /
  out-of-range / negative / non-integer index types for `[index]`,
  0/1/N-element `single()` row-resilience vs literal-union static
  invalidity, empty/singleton `first`/`last`/`tail`, integer-only
  `skip`/`take` with negative/zero/extreme/empty/non-integer arguments,
  dedup-vs-preserve-duplicates semantics across `intersect`/`exclude`/
  `union`/`combine`, Quantity semantic equality (`1 'cm' ≡ 10 'mm'`),
  temporal equality, numeric Integer≡Decimal equality, complex-object
  equality through `union`, 2-arg `combine(other, preserveOrder)`
  extension with Boolean/empty/non-Boolean/multi-arg validation, scoped
  `select()` chains for all subsetting/combining functions, and
  resource-backed `Patient.name`/`identifier` with duplicates plus
  `Observation.valueQuantity` cross-`component.valueQuantity`. Result:
  0 parity diffs, 0 validity diffs, 0 native/fallback exceptions on
  FHIR-conformant inputs. The prior FP-05 SKEPTIC `combine(other,
  preserveOrder)` fix remains intact. Existing 8 collection-operator
  parity tests pass. Full conformance 2822/2822 unchanged. Probe
  artifacts: `.temp/qa/fp05_historian_iteration_probe.py` (76 cases)
  and `.temp/qa/fp05_historian_edge_probe.py` (39 cases).
- **FHIRPath FP-04 SKEPTIC §5.2 ofType primitive-subtype parity gap
  (2026-06-28):**
  **OPEN:** Python fallback returns wrong results for `ofType` on FHIR
  primitive fields whose name is also a primitive subtype (e.g., `id`,
  `code`). The native C++ extension is correct. Three confirmed defects:
  (1) `Patient.id.ofType(string)` → native `[]`, fallback `['example']`
  (id is NOT a subtype of string for ofType per R4 test
  `testFHIRPathAsFunction16` analogue); (2) `Patient.id.ofType(id)` →
  native `['example']`, fallback `[]` (exact-type match fails); (3)
  `Observation.valueDecimal.ofType(FHIR.decimal)` → native `['1.5']`,
  fallback `[]` (qualified FHIR namespace fails). Root cause #1+#2:
  `fhir4ds/fhirpath/engine/nodes.py::ResourceNode.get_type_info()` lacks
  FHIR_PATH_TO_TYPE entries for `Patient.id` and `.id`, so it falls
  through to `create_by_value_in_namespace` which returns `FHIR.string`
  for any str-typed value. Root cause #3:
  `fhir4ds/fhirpath/duckdb/udf.py::_resolve_choice_oftype()` passes
  raw values (not ResourceNodes) into `of_type_fn`; raw values get
  typed with `System` namespace by `TypeInfo.from_value`, so the
  qualified `FHIR.decimal` namespace-distinct check in `is_exact_type`
  rejects them. Probe artifacts: `.temp/qa/fp04_skeptic/probe.py`,
  `.temp/qa/fp04_skeptic/probe2.py`.
- **FHIRPath FP-03 HISTORIAN §5.1 Existence exhaustive verification
  (2026-06-28):**
  **VERIFIED CLEAN:** A systematic section-by-section HISTORIAN pass
  across all 12 §5.1 functions (`empty`, `exists`, `all`, `allTrue`,
  `anyTrue`, `allFalse`, `anyFalse`, `subsetOf`, `supersetOf`, `count`,
  `distinct`, `isDistinct`) verified every normative rule from the
  FHIRPath spec (http://hl7.org/fhirpath §5.1) with 148 targeted test
  cases comparing native C++ vs forced Python fallback. Coverage:
  bare/method/no-arg/1-arg/criteria forms, vacuous truth on
  `all`/`allTrue`/`allFalse` empty inputs, false-on-empty for
  `anyTrue`/`anyFalse`, `subsetOf`/`supersetOf` empty-input asymmetry
  per spec, Boolean-aggregate non-Boolean-item errors, `$index`/`$this`
  scope preservation in `all()`/`exists()` criteria, resource-backed
  paths (Patient.name, Patient.identifier, Patient.bools,
  Patient.obs.valueQuantity), composed select/where/distinct/count
  chains, mixed-type collections in distinct, Quantity `=` vs `~`
  distinction (`1 'g'` and `1000 'mg'` must remain distinct under `=`),
  empty-of-empty edge cases, and 9 invalid arity cases. Result:
  0 parity diffs, 0 validity diffs, 0 native/fallback exceptions. The
  prior FP-03 SKEPTIC fix (bare no-arg `exists()` dispatch in
  `evaluator.cpp::evalFunction()`) remains intact across 5 exists()
  bare/no-arg probe cases. Existing 14/14 existence parity tests pass.
  Full conformance 2822/2822 unchanged. Probe artifacts:
  `.temp/qa/fp03_historian_iteration_probe.py` (77 cases) and
  `.temp/qa/fp03_historian_deep_probe.py` (71 cases).
- **FHIRPath FP-03 SKEPTIC fresh §5.1.2 bare `exists()` silent failure
  (2026-06-27):**
  **FIXED:** Native C++ bundled DuckDB extension silently returned an
  empty collection `[]` for the bare no-source no-arg form `exists()`,
  while the forced Python fallback correctly returned `[true]` on a
  non-empty focus. Per FHIRPath §5.1.2, the no-arg form is equivalent
  to `count() > 0` and must return `true` for non-empty input, `false`
  for empty input (never the empty collection). Root cause:
  `extensions/fhirpath/src/fhirpath/parser.cpp:456-468` parses bare
  `exists()` (without `source.exists(...)`) as `NodeType::FunctionCall`,
  not `NodeType::ExistsCall`; the latter is reserved for the method
  form at parser.cpp:323-331. Native `Evaluator::evalFunction()` had
  no dispatch branch for `name == "exists"` and fell through to the
  unknown-function return-empty `{}` at evaluator.cpp:4117, while
  `fhirpath_is_valid()` returned True. The single-line fix in
  `evaluator.cpp::evalFunction()` adds `if (name == "exists") { return
  evalExists(node, input, doc); }` right after the existing `where`
  dispatch. `evalExists` already handles both no-arg (`count() > 0`)
  and 1-arg (`where(criteria).exists()`) cases correctly. Guard with
  `.temp/qa/fp03_skeptic_fresh_probe.py` (77 expressions, 0 native vs
  fallback diffs after fix),
  `test_existence_parity.py::test_bare_exists_no_arg_matches_count_gt_zero_in_native_and_fallback`,
  native sqllogictest `exists()` assertions, and full conformance
  2822/2822; rebuild/copy `fhirpath.duckdb_extension` after future
  `evalFunction` dispatch changes.
- **FHIRPath FP-02 EXPLORER fresh §4.3 malformed-syntax row resilience
  in forced Python fallback (2026-06-27):**
  **FIXED:** Six of the seven forced-Python-fallback public DuckDB
  result UDF wrappers in `fhir4ds/fhirpath/duckdb/udf.py`
  (`fhirpath_scalar`, `fhirpath_bool_udf`, `fhirpath_number_udf`,
  `fhirpath_json_udf`, `fhirpath_quantity_udf`, `fhirpath_timestamp_udf`)
  had explicit `except FHIRPathSyntaxError: raise` clauses that bypassed
  the standard `_STRICT_MODE` row-resilience pattern. `fhirpath_date_udf`
  inherited the propagation by calling `fhirpath_scalar` without its own
  catch. Only `fhirpath_text_udf` caught the exception at its boundary.
  As a result, malformed trailing-token expressions such as
  `(1 | 2) where`, `(1 | 2 | {}) where $this > 0`, `(1 | 2) foo`, and
  `1 where` raised `duckdb.InvalidInputException` (Python exception
  propagating as `FHIRPathSyntaxError: Unexpected trailing token`)
  through DuckDB in fallback mode, crashing the entire query, while the
  native C++ path returned empty/NULL (FP-06 HISTORIAN established this
  for native `EvaluateFhirpath`). Fix applied the standard `_STRICT_MODE`
  pattern to all six handlers: log a warning, raise only when
  `FHIRPATH_STRICT_MODE=1`, return the type-appropriate empty value
  (`None` or `[]`) otherwise. Guard with
  `.temp/qa/fp02_explorer_drill_probe.py`,
  `.temp/qa/fp02_explorer_fresh_probe2.py`, and full conformance; the
  pattern applies to any future public FHIRPath result wrapper added to
  `udf.py`.
- **FHIRPath FP-02 HISTORIAN fresh §6.8 comparison-vs-equality precedence
  parity (2026-06-27):**
  **FIXED:** Native C++ recursive-descent parser at
  `extensions/fhirpath/src/fhirpath/parser.cpp:168-199` previously nested
  `parseEqualityExpression` INSIDE `parseInequalityExpression`, placing
  equality (`=`, `~`, `!=`, `!~`) at HIGHER precedence than comparison
  (`>`, `<`, `>=`, `<=`). Per §6.8 the order is INVERTED: comparison
  (#08) binds tighter than equality (#09). Concrete trace of
  `5 > 3 = true` through the old parser:
  `parseInequalityExpression` -> `parseEqualityExpression` returned just
  `5` (since `>` is not an equality operator), then the outer parser
  saw `>`, advanced, and parsed right = `parseEqualityExpression` which
  consumed `3 = true` and built `(3 = true)`. Result: `5 > (3 = true)`,
  which evaluates to empty per §6.2 (Integer-vs-Boolean type mismatch).
  Native returned empty while forced Python fallback correctly returned
  `[true]`. The R4 FHIRPath conformance suite has zero mixed
  comparison+equality expressions, which is why this defect survived
  935/935 passing. Fix rewired the call graph in parser.cpp:152-214 so
  the composition is now `parseMembershipExpression` ->
  `parseEqualityExpression` -> `parseInequalityExpression` ->
  `parseUnionExpression`, matching §6.8 (#10 in/contains < #09 = ~ != !~
  < #08 > < >= <= < #07 |). Function bodies unchanged; only the nesting
  is rewired. Guard with
  `test_comparison_parity.py::test_equality_vs_comparison_precedence_matches_backends`
  (16 parametrized cases) and full conformance; rebuild and copy
  `fhirpath.duckdb_extension` after future native parser.cpp changes in
  the equality/comparison region.
- **FHIRPath FP-02 HISTORIAN fresh §6.8 unary-minus on resource path
  parity (2026-06-27):**
  **FIXED:** Forced Python fallback `polarity_expression` in
  `fhir4ds/fhirpath/engine/evaluators/__init__.py:615-658` previously
  tested `util.is_number(value)` directly on the `ResourceNode` wrapper,
  but `util.is_number` only recognizes Python `int`/`Decimal`/`complex`,
  not `ResourceNode`. As a result `-a` (where `a:5` is an integer FHIR
  primitive) raised `FHIRPathError: Unary - cannot be applied to
  non-numeric value: ResourceNode('Patient.a', 5)` while native C++
  returned `[-5]`. Also affected: `-c` (decimal path), `-a + b`,
  `-a * b`, `5 + -a`, `a + -b`, `-q.value`. Fix added a
  `util.get_data(value)` unwrap before the `is_number` check, so the
  underlying numeric value (with float-to-Decimal materialization) is
  tested and negated. The sort-expression marker paths
  (`DescendingSortMarker` for non-numeric sort contexts) and the
  strict-mode boolean-polarity error are preserved. Native already
  unwrapped correctly; no C++ change required. Guard with
  `test_arithmetic_parity.py::test_unary_minus_on_resource_path_matches_backends`
  (8 parametrized cases) and full conformance.
- **FHIRPath FP-01 EXPLORER fresh §4.1.8 Quantity literal member access
  parity (2026-06-27):**
  **FIXED:** Quantity literals (`5 'mg'`, `4 days`, `1 year`) previously lost
  member access in native C++ and produced wrong values in the forced Python
  fallback. Native `Evaluator::evalMemberAccess` in
  `extensions/fhirpath/src/fhirpath/evaluator.cpp` only processed items of type
  `FPValue::Type::JsonVal`, silently skipping `Type::Quantity` items at the
  type guard, so `5 'mg'.value`, `5 'mg'.unit`, `5 'mg'.code`, and
  `5 'mg'.system` all returned empty. Resource-backed `Observation.valueQuantity`
  member access worked correctly because the FHIR JSON `{value,unit,code,system}`
  is a JsonVal. Python fallback `create_reduce_member_invocation` in
  `fhir4ds/fhirpath/engine/evaluators/__init__.py` set `toAdd = res.data.value`
  unconditionally for any `FP_Quantity` item regardless of the requested key,
  so `.value` returned the value (correct shape) but `.unit`/`.code`/`.system`
  also returned the value (wrong). Fix: native adds an explicit
  `Type::Quantity` branch at the top of the per-item loop that materializes
  `.value` as `Type::Decimal` (normalizing source_text so the Decimal surface
  always carries a fractional digit per §4.1.8) and `.unit` as `Type::String`
  (the bare UCUM code or calendar duration keyword, matching §5.5.8 Quantity
  toString shape); `.code`/`.system` return empty for literals because literals
  carry no UCUM/namespace URI metadata. Python fallback dispatches on `key`:
  `.value` materializes as Decimal (Integer→Decimal per §4.1.8), `.unit`
  returns the quote-stripped unit text via `FP_Quantity._strip_unit_quotes()`,
  other keys return empty. Guard with
  `.temp/qa/fp01_explorer_rerun_probe.py`,
  `test_literal_parity.py::test_quantity_literal_member_access_matches_backends`,
  and
  `test_literal_parity.py::test_quantity_literal_value_and_unit_member_equality`;
  rebuild and copy `fhirpath.duckdb_extension` after future native
  `evalMemberAccess` changes.
- **FHIRPath FP-01 EXPLORER fresh §4.1.2 unclosed string literal leniency
  (2026-06-27):**
  **DEFERRED:** Both native C++ and forced Python fallback accept unclosed
  string literals where the last character before EOF is an escape sequence
  (`'abc\'`, `'abc\\'`). Per §4.1.2 and the formal grammar in §12.1, an escape
  sequence does not terminate a string literal; the literal must be closed by
  a non-escaped single-quote. Both paths agree (no parity drift), the lenient
  parse is deterministic, and there is no data corruption. Deferred because
  the fix would require coordinated native+fallback lexer changes for a
  cross-path-consistent behavior that is not currently causing any conformance
  failure.
- **FHIRPath FP-01 HISTORIAN fresh §4.1.5 ISO 8601 week-date validity
  parity (2026-06-27):**
  **FIXED:** Forced Python fallback `fhirpath_is_valid_udf` previously
  returned `True` for ISO 8601 week-date literals such as `@2015-W01-1`,
  `@2015-W01`, `@2015-W53-7`, `@2015-W`, and `@2015-W00`, while native C++
  `fhirpath_is_valid` returned `False` per FHIRPath §4.1.5 ("Week dates and
  ordinal dates are not allowed"). Both paths returned empty `[]` for the
  result UDFs (no data corruption), but the validity signal disagreed. Root
  cause was two-part: (1) `_scan_temporal_token()` in
  `fhir4ds/fhirpath/duckdb/evaluator.py:108` scanned only
  `"0123456789T:.-+Z"` characters after `@`, so it stopped before the `W`
  marker; (2) the Python fallback had no static precheck for the week-date
  form, so `fhirpathpy` accepted it. Fix: extended the scanner character set
  to include `W`, added `_has_invalid_week_date_literal()` precheck (regex
  `@\d{4}-W\d{0,2}(?:-\d)?`) following the existing timezone/partial-DT
  precheck pattern, and wired it into `FHIRPathEvaluator.compile()` (raises
  `FHIRPathSyntaxError`), `fhirpath_is_valid_udf()` (returns `False`), and
  `_is_row_resilient_invalid_literal()` (returns empty `[]`). The fix is
  general across the class of week-date literals, not the reproducer only.
  Guard with `.temp/qa/fp01_historian_probe.py`,
  `test_literal_parity.py::test_iso8601_week_date_literals_are_invalid_in_both_backends`,
  and
  `test_literal_parity.py::test_valid_calendar_duration_keywords_remain_valid_after_week_date_fix`
  (the latter guards against the `W` scanner extension accidentally
  rejecting `week`/`weeks` Quantity literals). No native rebuild required.
- **FHIRPath FP-01 SKEPTIC fresh §4.1/§6.1 FHIR decimal primitive path equality (2026-06-27):**
  **FIXED:** Forced Python fallback `equality()` in
  `fhir4ds/fhirpath/engine/invocations/equality.py` previously returned
  `a == b` (the original ResourceNode-wrapped operands) instead of the already
  computed `a_raw == b_raw` (unwrapped via `util.get_data()`). For any FHIR
  `decimal` primitive path (e.g. `RiskAssessment.prediction.probabilityDecimal`,
  `Observation.referenceRange.high.value`, `Observation.valueQuantity.value`),
  the raw JSON-decoded Python float inside `ResourceNode.data` flowed into
  `ResourceNode.__eq__` and then into a cross-type `float == Decimal`
  comparison that silently returned False for §6.1.1-equal values such as
  `probabilityDecimal = 123.45` (because the binary float
  `123.45000000000000284217...` differs digit-wise from `Decimal('123.45')`).
  Native C++ already returned True. The single-line fix compares the unwrapped
  values so the existing `util.get_data()` float→`Decimal(str(float))`
  materialization survives to the final comparison. The same defect did not
  affect `<`/`>`/`<=`/`>=` operators (which already route through
  `_get_comparison_data` and `util.get_data`) nor `~` (which already unwraps
  at the top of `equivalence()`). Guard with
  `.temp/qa/fp01_skeptic_fresh_probe.py`, `.temp/qa/fp01_skeptic_edge_probe.py`,
  `test_equality_parity.py::test_fhir_decimal_primitive_path_equal_to_decimal_literal`,
  and the full conformance suite. No native rebuild required.
- **FHIRPath FP-01 SKEPTIC fresh §4.1 negative-zero Decimal source text (2026-06-27):**
  **DEFERRED:** Expression `-0.0` returns `[-0.0]` from native C++ (preserves
  authored sign via `source_text`) but `[0.0]` from forced Python fallback
  because Python's `Decimal.__neg__` strips the sign:
  `-Decimal('0.0')` is `Decimal('0.0')`. FHIRPath §4.1.4 is silent on signed
  zero and the two representations are mathematically equal
  (`Decimal('0.0') == Decimal('-0.0')` is True in Python), so the drift is
  observable only via stringification. A spec-grounded fix would require
  preserving authored text through Decimal negation in the Python fallback,
  which is net-new functionality rather than a minimal repair.
- **FHIRPath FP-15 HISTORIAN fresh §6.3 empty `is` inputs (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §6.3 says ordinary empty `is` inputs are
  non-matching and should return false rather than empty. Python
  `types.is_fn()` and native `Evaluator::fn_isType()` now return false for
  arbitrary missing paths such as `missing is Integer` and `missing.is(Integer)`
  after type-specifier validation, while preserving R4 fixture behavior where
  absent FHIR primitive paths such as `Observation.issued is instant` remain
  empty. DuckDB Python fallback value[x] assertion helpers now use FHIR
  hierarchy matching for `is` (`uri` satisfies `string`) while preserving exact
  primitive choice behavior for `as`. Guard with
  `.temp/qa/fp15_historian_fresh_probe.py`, `test_type_parity.py`,
  `test_environment_type_parity.py`, native `fhirpath.test`, FHIRPath R4
  conformance, and full conformance; rebuild/copy the bundled native extension
  after touching native type code.
- **FHIRPath FP-15 SKEPTIC fresh §6.3 type operators (2026-06-12):**
  **FIXED:** Type-specifier validation must derive from the complete R4 model
  hierarchy, not the legacy short valid-type list. Fresh probing found
  `CodeSystem`, `QuestionnaireResponse`, `Binary`, and `Parameters` rejected as
  unknown in `ofType()`/`is`/`as` chains even though they are valid R4 resource
  types in `type2Parent.json`. Python `TypeInfo.VALID_FHIR_TYPES` now widens
  from the R4 hierarchy metadata, and native `isKnownFHIRType()` reuses
  `fhirTypeIsA()` for resource/datatype names while keeping a primitive-name
  root set. The same pass fixed the DuckDB Python fallback wrapper losing
  choice-type semantics after source expressions such as
  `entry.resource.ofType(Observation).value.is(Integer)` and
  `.value.as(Integer)`. Guard with `.temp/qa/fp15_skeptic_fresh_probe.py`,
  `test_type_parity.py`, native `fhirpath.test`, and full conformance; rebuild
  and copy `fhirpath.duckdb_extension` after native type changes.
- **FHIRPath FP-14 EXPLORER fresh §6.2 comparison verification (2026-06-12):**
  **VERIFIED CLEAN:** A fresh 37-expression native C++ vs forced Python
  fallback probe matched current source behavior for `>`, `<`, `<=`, and `>=`
  over exact large Long/Decimal/JSON numeric values, same-unit and converted
  FHIR Quantity paths, resource-backed Date/DateTime paths with timezone
  offsets, lexical Unicode String ordering, empty propagation, multi-item
  row resilience, and statically invalid Boolean/literal-multi-item
  comparisons. Keep `.temp/qa/fp14_explorer_fresh_probe.py` pinned to the
  repository root on `sys.path`; otherwise a stale installed `fhir4ds` package
  can mimic pre-fix FP-14 native/fallback drift.
- **FHIRPath FP-14 HISTORIAN fresh §6.2 resource-backed DateTime comparison (2026-06-12):**
  **FIXED:** Forced Python fallback comparison over FHIR `dateTime` resource
  paths must normalize both operands when both carry timezone offsets. Fresh
  native-vs-fallback probing found `effectiveDateTime > issued` over
  `2015-02-04T10:00:00+01:00` and `2015-02-04T09:30:00Z` returned true in
  fallback but false natively. Correct ordering is false because the left
  instant is 09:00Z and the right instant is 09:30Z. Fallback comparison now
  materializes typed FHIR `dateTime`/`instant`/`date`/`time` resource strings
  as `FP_DateTime`/`FP_Date`/`FP_Time` before typechecking, so same-type
  resource temporal paths reach `FP_TimeBase.compare()` instead of Python
  string ordering. Guard with `.temp/qa/fp14_historian_fresh_probe.py` and
  `test_comparison_parity.py` when changing `FP_TimeBase.compare()` or
  resource-backed temporal type materialization.
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
  `.temp/qa/fp14_skeptic_fresh_probe.py`, `test_comparison_parity.py`, and
  native `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the
  bundled extension after future native comparison changes.
- **FHIRPath FP-13 EXPLORER fresh §6.1 equality/equivalence (2026-06-12):**
  **FIXED:** Forced Python fallback Quantity equivalence must compare
  converted quantities using tolerance derived from each operand's original
  precision, not the precision of already-converted base values. Otherwise
  `Observation.value ~ 83.9 'kg'` for `185 '[lb_av]'` drifts from native and
  the §6.1 least-granular Quantity equivalence rule. Native C++ JSON numeric
  equality/equivalence must also avoid `yyjson_get_num()`/`double` for exact
  Integer/Long-sized JSON values: `9007199254740992` and
  `9007199254740993` are distinct for `=`, `!=`, `~`, and `!~`, including
  inside complex objects and arrays. Guard with
  `.temp/qa/fp13_explorer_fresh_probe.py`, `test_equality_parity.py`, and
  native `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the
  bundled extension after future native equality changes.
- **FHIRPath FP-13 HISTORIAN fresh §6.1 equality/equivalence (2026-06-12):**
  **FIXED:** Numeric primitives compare as implicit Quantity unit `1` for §6.1
  examples such as `23 = 23 '1'` and `23 ~ 23 '1'`, including resource-backed
  FHIR Quantity values with UCUM code `1` and ordered multi-item collections.
  Quantity equivalence over non-commensurable dimensions such as
  `1 'cm' ~ 1 's'` returns empty/NULL, while supported commensurable UCUM
  units such as `[lb_av]` versus `kg` route through the canonical Quantity base
  conversion table. Guard with `.temp/qa/fp13_historian_fresh_probe.py`,
  `test_equality_parity.py`, native `fhirpath.test`, and the official R4
  `Observation.value !~ 185 'kg'` sentinel; rebuild and copy the bundled
  extension after native equality changes.
- **FHIRPath FP-13 SKEPTIC fresh §6.1 equality/equivalence (2026-06-12):**
  **FIXED:** String equivalence now maps Unicode White_Space code points
  one-for-one to ASCII spaces without collapsing or trimming and uses Unicode
  case folding/case mapping in both fallback and native paths. Quantity
  equality now returns empty only for mixed calendar-vs-UCUM year/month
  equality, while definite week/day/hour/minute/second/millisecond durations
  compare through normal unit conversion. Guard with
  `.temp/qa/fp13_skeptic_fresh_probe.py`,
  `test_equality_parity.py`, and native `fhirpath.test`; rebuild and copy the
  bundled native extension after C++ equality changes.
- **FHIRPath FP-12 EXPLORER primitive metadata tree navigation (2026-06-12):**
  **FIXED:** Fresh §5.8 probing found `children()` / `descendants()` did not
  expose FHIR primitive sibling metadata such as `_birthDate.extension` or
  `_given.extension` when evaluating the primitive element itself. This means
  `birthDate.children().where(url = ...).valueString` and
  `name.given.children().where(url = ...).valueString` returned empty even though
  §5.8 notes primitive datatype children can include extensions. Native C++
  additionally missed nested primitive `name.given.extension(url)` because it
  only checked root-level shadow fields. Python now carries primitive `_data`
  through `children()` and primitive member navigation. Native now carries a
  primitive shadow pointer on `FPValue`, zips child arrays with `_field` arrays,
  and uses that shadow for primitive `children()` and nested `extension(url)`.
  Guard with `.temp/qa/fp12_explorer_fresh_probe.py`,
  `test_tree_utility_parity.py`, and native `fhirpath.test`; rebuild/copy the
  bundled extension after native primitive-navigation changes.
- **FHIRPath FP-12 SKEPTIC fresh trace projection scoping (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.9 defines `trace(name, projection)` as a
  scoped function whose projection is evaluated for each input item with
  `$this` and `$index`, while returning the original input collection. Fresh
  native-vs-forced-fallback probing found both paths evaluated the projection
  once over the whole input collection, so
  `name.trace('names', given.single()).given.count() = 2` failed for two name
  elements that each had one `given`. Python `trace_fn` now evaluates the
  projection per item, restores `$index`/vars/chain scope, and flattens the
  diagnostic projection only for trace logging. Native C++ mirrors that
  per-item projection validation and restores evaluator scope before returning
  the unchanged input. Guard with `.temp/qa/fp12_skeptic_fresh_probe.py` and
  `test_tree_utility_parity.py`; rebuild/copy the bundled extension after
  native trace changes.
- **FHIRPath FP-11 EXPLORER fresh native large Long/Decimal math (2026-06-12):**
  **FIXED:** Fresh §5.7 Math probing found native C++ still routed
  Long-sized inputs for `ceiling()`, `floor()`, `truncate()`, `round()`, and
  `power()` through binary `double` conversion. This corrupts values around
  max Long, e.g. `9223372036854775807L.ceiling()` returns
  `-9223372036854775808`, `9223372036854774785L.ceiling()` returns
  `9223372036854774784`, and `9223372036854775807L.power(1).toString()`
  renders scientific notation instead of exact Decimal-shaped text. Native now
  derives integral math results from preserved numeric `source_text`, returns
  exact `Integer` values when they fit, and preserves Decimal-shaped source
  text for `power(..., 0)` / `power(..., 1)`. Guard with
  `.temp/qa/fp11_explorer_fresh_probe.py`, native/fallback
  `test_math_parity.py`, and native `fhirpath.test` coverage.
- **FHIRPath FP-11 HISTORIAN fresh §5.7 Math boundary issues (2026-06-12):**
  **FIXED:** Fresh native-vs-forced-fallback probing found three current Math
  compliance defects: native C++ `9223372036854775807L.abs()` returns
  `-9223372036854775808` due to integer absolute-value overflow/rounding;
  forced Python fallback does not treat resource-backed FHIR Quantity JSON as
  Quantity for `abs()`, `ceiling()`, `floor()`, `round()`, and `truncate()`;
  and forced fallback `2.power(3).toString()` returns `"8"` instead of the
  Decimal-shaped `"8.0"`. Native now handles Integer/Long `abs()` and unary
  negation without `double` conversion for representable values, fallback
  Quantity detection routes through `util.parse_value(...)`, and fallback
  Decimal `toString()` appends `.0` when needed. Guard with
  `.temp/qa/fp11_historian_fresh_probe.py` plus `test_math_parity.py`,
  `test_math.py`, conversion parity, and native sqllogictest coverage.
- **FHIRPath FP-11 SKEPTIC fresh current §5.7 Math Quantity/power semantics (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.7 says `ceiling()`, `floor()`,
  `round([precision])`, and `truncate()` accept Quantity and return Quantity
  with the same unit, and `power()` always returns Decimal. Native C++,
  forced Python fallback, and direct math helpers now preserve Quantity units
  for the Quantity-capable functions and return Decimal-shaped results for
  `power()` integer powers such as `2.power(3)`. Guard with
  `.temp/qa/fp11_skeptic_fresh_probe.py`, `test_math_parity.py`,
  `test_math.py`, and native `fhirpath.test`; rebuild/copy the bundled
  extension after future native math changes.
- **Milestone code review after FP-01 through FP-10 (2026-06-12):**
  **OPEN REVIEW FINDINGS:** Native regex class range normalization expands
  mixed ASCII-to-Unicode ranges such as `[a-😀]` into huge alternations, making
  a short valid user regex slow and invalid natively while forced fallback
  returns a valid match. Native delimited identifiers still ignore failed
  surrogate escape validation in `readDelimitedIdentifier()`, unlike string
  literals. Native direct FHIR type specifier coverage remains split between
  `fhirTypeIsA()` and `isKnownFHIRType()`, leaving resource types such as
  `CodeSystem`, `QuestionnaireResponse`, `Binary`, and `Parameters` invalid
  for direct `ofType(<resource>)` filters. The lower-level
  `duckdb.functions.string.substring()` API still returns empty collection for
  negative in-range lengths while the engine/UDF path now returns `""`.
  Track details in `.ai_loop/code_review_findings.md` as `REV-001` through
  `REV-004`.
- **FHIRPath FP-10 ARCHITECT Unicode regex `i` flag (2026-06-12):**
  **FIXED:** Native `std::regex_constants::icase` is byte/locale-oriented for
  UTF-8 and does not match forced Python fallback on ordinary Unicode
  case-insensitive regex behavior. Architect probing found
  `upper.matches('é', 'i')`, `upper.matches('[é]', 'i')`, and
  `upper.matches('^[é-ë]$', 'i')` over `É` false natively while fallback
  returns true. Native regex normalization now adds grouped original,
  uppercase, and lowercase variants for non-ASCII literals/classes/ranges when
  the FHIRPath `i` flag is present, while keeping `std::regex` `icase` for
  ASCII behavior.
- **FHIRPath FP-10 ARCHITECT Unicode regex class ranges (2026-06-12):**
  **FIXED:** The first FP-10 EXPLORER remediation made native regex character
  classes scalar-aware for non-ASCII literals and negated classes, but
  architect probing found Unicode ranges still split incorrectly:
  `ecirc.matches('^[é-ë]$')` returns false natively while forced fallback
  returns true, and `ecirc.replaceMatches('[é-ë]', 'x')` leaves `ê`
  unchanged. The native class normalizer must treat non-ASCII range endpoints
  as scalar ranges; it now parses class atoms and expands ranges with any
  non-ASCII endpoint into grouped whole-codepoint alternatives while preserving
  compact pure-ASCII ranges.
- **FHIRPath FP-10 EXPLORER fresh Unicode regex character classes (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.6 String Manipulation says regex
  functions operate on strings that are sequences of Unicode scalar values and
  allow Unicode characters. Fresh native-vs-forced-fallback probing found the
  native C++ `std::regex` path still interprets non-ASCII literals inside
  character classes as UTF-8 bytes: `accent.matches('^[é]$')` and
  `emoji.matches('^[😀]$')` return false natively while fallback returns true;
  `replaceMatches('[é]', 'x')` returns `xx` and
  `replaceMatches('[😀]', 'x')` returns `xxxx` natively while fallback returns
  `x`. Guard/fix with `.temp/qa/fp10_explorer_fresh_probe.py` and
  `test_string_transform_parity.py`; native `normalizeFHIRPathRegex()` now
  rewrites character classes into codepoint-aware regex fragments, including
  whole-codepoint alternatives for positive non-ASCII literals and a negative
  lookahead plus the shared UTF-8 codepoint matcher for negated classes.
- **FHIRPath FP-10 HISTORIAN fresh Unicode upper/lower case mapping (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.6.6/§5.6.7 says `upper()` and
  `lower()` convert all characters in a singleton string to upper/lower case.
  Fresh native-vs-forced-fallback probing found native C++ still relied on a
  limited hand-written Unicode range table: `ẞ.lower()`, `ﬃ.upper()`,
  `𐐨.upper()`, `ա.upper()`, `ა.upper()`, and `ƀ.upper()` were left unchanged
  while the Python fallback returned Unicode case mappings. Native now decodes
  UTF-8 scalar values, uses DuckDB's vendored `utf8proc` for one-to-one Unicode
  case mappings, and keeps explicit full-case uppercase expansions such as
  ligatures and `ß -> SS`. Guard with `.temp/qa/fp10_historian_fresh_probe.py`,
  `test_string_transform_parity.py`, and native sqllogictest assertions;
  rebuild/copy the bundled extension after future native `fn_upper()` /
  `fn_lower()` edits.
- **FHIRPath FP-10 SKEPTIC fresh regex transform semantics and flags (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath String Manipulation defines
  `matches(regex, [flags])` as regex search behavior and allows optional
  `i`/`m` flags for both `matches()` and `replaceMatches()`. Fresh native
  DuckDB/C++ and forced Python fallback probing found both paths using
  obsolete full-string `matches()` semantics and rejecting valid flagged calls
  such as `url.matches('library', 'i')`, `line.matches('^second', 'm')`, and
  `s.replaceMatches('abc', 'X', 'i')`. Python fallback now uses regex search,
  validates only `i`/`m` flag characters, and threads flags through sparse
  `fhirpath_is_valid()` checks. Native C++ mirrors that behavior, including
  multiline anchor handling for `replaceMatches()` without consuming line
  separators. Guard with `.temp/qa/fp10_skeptic_fresh_probe.py`,
  `test_string_transform_parity.py`, Python unit string tests, and native
  `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the bundled
  extension after native regex edits.
- **FHIRPath FP-09 EXPLORER fresh Python fallback negative substring length (2026-06-12):**
  **FIXED:** HL7 FHIRPath §5.6.2 says `substring(start, length)` returns the
  empty string when `length` is zero or negative, provided `start` itself is
  in range. Fresh native-vs-forced-fallback probing found the Python fallback
  leaking Python negative-slice semantics for sufficiently negative lengths:
  `s.substring(1, -4)` over `abcdef` returns `bc` in fallback while native
  returns `''`. Python fallback now returns `""` before slicing whenever the
  validated `length <= 0`. Guard with `.temp/qa/fp09_explorer_fresh_probe.py`
  and focused cases in `test_string_search_parity.py` when changing
  `fhir4ds/fhirpath/engine/invocations/strings.py::substring`.
- **FHIRPath FP-08 EXPLORER fresh resource-backed Decimal `toString()` (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.5.8 Decimal `toString()` uses decimal
  digit notation, not scientific notation. Fresh native DuckDB/C++ and forced
  Python fallback probing found resource-backed JSON Decimal values emitting
  `1e-06` through both paths, with native also emitting `1e+15` for a large
  JSON decimal. Python fallback now converts float primitives through
  `Decimal(str(value))` and formats Decimals with fixed notation; native C++
  uses `formatDecimalNumber()` for JSON real/Decimal stringification. The same
  pass fixed native max-Long `toQuantity().toString()` precision by preserving
  integer source text before Quantity stringification. Guard with
  `.temp/qa/fp08_explorer_fresh_probe.py` and
  `test_conversion_parity.py::test_json_decimal_to_string_uses_plain_decimal_not_scientific_notation`
  when changing JSON numeric stringification, Decimal `toString()`,
  Integer/Long `toQuantity()`, or public DuckDB wrapper serialization.
- **FHIRPath FP-08 HISTORIAN fresh Quantity string formatting (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.5.8 Quantity `toString()` uses a
  decimal digit representation, not scientific notation. Fresh native and
  forced Python fallback probing found converted quantities rendering as
  `1e-06 'kg'`, `1e+15 'g'`, or `2E+2 'cm'` depending on path. Python
  `FP_Quantity.__str__` now formats `Decimal` values with fixed notation
  while preserving trailing Decimal scale for official conformance cases, and
  native C++ Quantity `toString()` falls back to fixed notation when default
  double streaming would emit an exponent. Guard with
  `.temp/qa/fp08_historian_fresh_probe.py`,
  `test_conversion_parity.py::test_quantity_to_string_uses_plain_decimal_not_scientific_notation`,
  and native `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the
  bundled extension after native formatting edits.
- **FHIRPath FP-07 EXPLORER fresh dynamic format and Long boundary issues (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.5.4/§5.5.5 optional `format : string`
  arguments are ordinary FHIRPath argument expressions. Fresh native DuckDB/C++
  probing found `rawDate.toDate(dateFmt)`,
  `rawDateTime.toDateTime(dateTimeFmt)`, and scoped
  `items.select(rawDate.toDate(dateFmt))` returning empty because native
  evaluates the format argument against the source string instead of the outer
  invocation focus. Native now evaluates format arguments against the outer
  focus for sourced String inputs and ignores the format argument for
  non-String Date/DateTime inputs. The same pass found §4.1/§5.5.6 Long
  boundary drift: fallback accepted positive out-of-range
  `9223372036854775808L`, native rejected valid signed-minimum
  `-9223372036854775808L`, and native max-Long `toDecimal()` text lost exact
  decimal surface through binary double formatting. Fallback now rejects
  out-of-range Long literals, native accepts unary signed-minimum Long through
  a parser sentinel, and Long literal `toDecimal()` preserves exact text via
  `source_text`. Guard with `.temp/qa/fp07_explorer_fresh_probe.py` and
  focused native/fallback conversion parity tests.
- **FHIRPath FP-07 HISTORIAN fresh string Long Decimal conversion (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.5.6 examples explicitly include
  `'42L'.toDecimal()` and `'42L'.convertsToDecimal()` as successful string
  Decimal conversions, distinct from the Long literal `42L`. Fresh native
  DuckDB/C++ and forced Python fallback probing found both paths returning
  empty/false for the string form while accepting the literal form. Python
  fallback and native C++ now recognize optional sign + digits + uppercase `L`
  for String inputs to `toDecimal()` / `convertsToDecimal()`, strip the suffix
  before Decimal parsing, and preserve rejection for malformed forms such as
  `1LL`, `1.0L`, lowercase `1l`, exponent notation, and whitespace-padded
  strings. Guard with `.temp/qa/fp07_historian_fresh_probe.py` and focused
  native/fallback parity tests when changing Decimal conversion.
- **FHIRPath FP-07 SKEPTIC fresh Date/DateTime format and Long Decimal conversion (2026-06-12):**
  **FIXED:** Current HL7 FHIRPath §5.5.4 and §5.5.5 define optional
  `format : string` parameters for `toDate()`, `convertsToDate()`,
  `toDateTime()`, and `convertsToDateTime()`. Python fallback now accepts
  one optional String format argument, parses required current format tokens
  such as `yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`, `S`, `a`, and `Z`, and ignores
  the format for non-string Date/DateTime inputs. Current §5.5.6 also includes
  Long inputs for Decimal conversion and examples such as `42L.toDecimal()`;
  the Python parser now recognizes uppercase Long literals, the fallback
  Integer range precheck skips valid uppercase Long suffixes before applying
  int32 bounds, and malformed suffixes such as `1LL`, `1.0L`, and `1l` remain
  row-resilient invalid expressions. Guard with
  `.temp/qa/fp07_skeptic_fresh_probe.py` and native/fallback parity tests in
  `test_conversion_parity.py`.
- **FHIRPath FP-06 EXPLORER fresh iif/Boolean/Integer conversion rerun (2026-06-12):**
  **VERIFIED CLEAN:** Fresh §5.5.1-§5.5.3 probing matched native DuckDB/C++
  and forced Python fallback public UDFs across 46 composed expressions. The
  matrix covered lazy `iif()` branches, singleton non-Boolean criteria such as
  `0`/`0.0`/strings, `$index` preservation through `select(iif(...))`,
  Boolean string/integer/decimal representations, strict Integer string
  grammar and int32 bounds, resource-backed multi-item row resilience, invalid
  conversion arity, unary precedence for `-1.convertsToInteger()`, and the
  FP-06 SKEPTIC/HISTORIAN result-wrapper fixes. Keep
  `.temp/qa/fp06_explorer_fresh_probe.py` and
  `test_conversion_parity.py` aligned when touching `iif()`, `toBoolean()`,
  `convertsToBoolean()`, `toInteger()`, `convertsToInteger()`, or public
  DuckDB wrapper row-resilience.
- **FHIRPath FP-06 HISTORIAN fresh fallback out-of-range Integer literal row resilience (2026-06-12):**
  **FIXED:** Fresh §5.5.3 probing found forced Python DuckDB fallback result
  UDFs throwing `FHIRPathSyntaxError` for `2147483648.toInteger()` while the
  native DuckDB/C++ public result wrappers return empty/NULL with
  `fhirpath_is_valid=false`. The expression uses an out-of-range Integer
  literal, so it is invalid, but non-strict public fallback result wrappers
  should remain row-resilient like native. The fallback row-resilience helper
  now includes `_has_out_of_range_integer_literal()`, while
  `fhirpath_is_valid()` still reports false. Guard with
  `.temp/qa/fp06_historian_fresh_probe.py` and focused conversion parity tests.
- **FHIRPath FP-06 HISTORIAN native invalid-expression result wrapper row resilience (2026-06-12):**
  **FIXED:** Fresh retry probing found native DuckDB result UDFs throwing for
  invalid parser/lexer expressions in the FP-06 boundary, including
  `-2147483649.toInteger()`, while the forced Python fallback returned
  empty/NULL with `fhirpath_is_valid=false`. The same shared wrapper class
  covered invalid surrogate string literals such as `'\uD834'`. Native
  `EvaluateFhirpath()` now returns an empty collection when `GetOrCompile()`
  yields no AST, preserving `fhirpath_is_valid()` as the validity signal.
  Guard with `.temp/qa/fp06_historian_fresh_probe.py`,
  `test_conversion_parity.py`, `test_literal_parity.py`, and native
  `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the bundled
  extension after native wrapper edits.
- **FHIRPath FP-06 SKEPTIC fresh iif numeric-zero singleton fallback (2026-06-12):**
  **FIXED:** FHIRPath §5.5.1 explicitly states `iif(0, 'true', 'false')`
  returns the true branch because numeric `0` is a non-empty singleton, not
  Boolean `false`. Fresh native DuckDB/C++ and forced Python fallback probing
  found the fallback returning the false branch for `iif(0, ...)`,
  `iif(0.0, ...)`, and `iif(0.toInteger(), ...)`, while native returned the
  spec-expected true branch. The root was Python singleton Boolean helper
  equality checks (`x == False` / `val == False`) conflating numeric zero with
  the Boolean singleton `false`; `is_true()` now uses Boolean identity checks
  so non-Boolean singleton truthiness is handled deliberately. Guard with
  `.temp/qa/fp06_skeptic_fresh_probe.py` and
  `test_conversion_parity.py`.
- **SPEC milestone code review after FP-01 through FP-05 (2026-06-12):**
  **OPEN REVIEW FINDINGS:** `REV-FP-001` public native result-UDF invalid
  parse row-resilience was remediated during FP-06 HISTORIAN by returning
  empty collections from `EvaluateFhirpath()` when `GetOrCompile(...)` fails.
  Native delimited identifiers still ignore failed surrogate escape validation
  because `readDelimitedIdentifier()` does not check
  `appendUnicodeEscape(...)`. FP-04's native R4 hierarchy expansion remains
  split from
  `isKnownFHIRType()`, leaving direct type specifiers such as
  `CodeSystem`, `QuestionnaireResponse`, `Binary`, and `Parameters`
  rejected despite hierarchy entries. Track the remaining `REV-FP-002` and
  `REV-FP-003` in the milestone `code_review_findings.md`; add parity tests
  for delimited identifier escapes and direct `ofType(<resource>)` coverage
  before closing.
- **FHIRPath FP-05 EXPLORER fresh subsetting/combining rerun (2026-06-11):**
  **VERIFIED CLEAN:** Fresh §5.3/§5.4 EXPLORER probing matched native
  DuckDB/C++ and forced Python fallback across 43 expressions covering
  `[index]`, `single()`, `first()`, `last()`, `tail()`, `skip(num)`,
  `take(num)`, `intersect(other)`, `exclude(other)`, `union(other)`/`|`,
  and `combine(other, preserveOrder)`. Coverage emphasized pathological
  argument shapes, dynamic scoped arguments inside `select()`, empty and
  negative count/index boundaries, duplicate-retaining `combine()`/`exclude()`,
  duplicate-removing `union()`/`intersect()`, and resource-backed `value[x]`
  paths. Keep `.temp/qa/fp05_explorer_fresh_probe.py` aligned with
  `test_collection_operator_parity.py` when changing FP-05 evaluator behavior.
- **FHIRPath FP-05 HISTORIAN fresh subsetting/combining rerun (2026-06-11):**
  **VERIFIED CLEAN:** Fresh §5.3/§5.4 probing matched native DuckDB/C++ and
  forced Python fallback across 52 expressions covering `[index]`, `single()`,
  `first()`, `last()`, `tail()`, `skip(num)`, `take(num)`,
  `intersect(other)`, `exclude(other)`, `union(other)`/`|`, and current
  `combine(other, preserveOrder)`. Coverage included invalid index/count
  literal types, multi-item singleton row resilience, duplicate-preserving
  `exclude()`/`combine()`, equality-backed set counts, and scoped
  `select(left.<set-fn>(right))` argument context. Keep
  `.temp/qa/fp05_historian_fresh_probe.py` root-pinned to the workspace on
  `sys.path`; launching probes from `.temp/qa` can otherwise import an
  installed stale package instead of the current source tree.
- **FHIRPath FP-05 SKEPTIC fresh `combine(..., preserveOrder)` gap (2026-06-11):**
  **FIXED:** Current HL7 FHIRPath §5.4 defines
  `combine(other : collection, [preserveOrder : Boolean]) : collection`, with
  `combine(B, true)` preserving input order while still retaining duplicates.
  Fresh native DuckDB/C++ and forced Python fallback probing found
  `ints.combine(otherInts, true)` returning empty/NULL with
  `fhirpath_is_valid=false`. Python core and native C++ now allow one or two
  arguments for `combine()`, validate the optional argument as a singleton
  Boolean when present, preserve duplicate-retaining append behavior, and keep
  exact one-argument arity for `union()`, `intersect()`, and `exclude()`.
  Guard with `.temp/qa/fp05_skeptic_fresh_probe.py`,
  `test_collection_operator_parity.py`, and native sqllogictest assertions;
  rebuild/copy the bundled extension after native evaluator changes.
- **FHIRPath FP-04 EXPLORER native R4 resource hierarchy gap (2026-06-11):**
  **FIXED:** Fresh §5.2 probing found native DuckDB/C++ dropping valid R4
  resource subclasses from `ofType(Resource)` and `ofType(DomainResource)`.
  The Python fallback includes resources such as `Questionnaire`,
  `QuestionnaireResponse`, `ValueSet`, and `CodeSystem` via the generated R4
  hierarchy, while native relied on a smaller embedded hierarchy table. Native
  `fhirTypeIsA()` now covers the missing R4 resource parent relationships and
  `isKnownFHIRType()` includes the generated R4 type-specifier names needed by
  `ofType()`. Keep `.temp/qa/fp04_explorer_fresh_probe.py`,
  `test_filter_projection_parity.py`, and native sqllogictest assertions
  aligned when changing native `fhirTypeIsA()`, `isKnownFHIRType()`, or
  `fn_isType()` resource subtype behavior; rebuild/copy the bundled extension
  after native evaluator edits.
- **FHIRPath FP-04 HISTORIAN fresh filtering/projection rerun (2026-06-11):**
  **VERIFIED CLEAN:** Fresh §5.2 probing matched native DuckDB/C++ and forced
  Python fallback across 24 expressions covering strict singleton-Boolean
  `where(criteria)`, `select(projection)` flattening and `$index`, recursive
  projection-only `repeat(projection)` de-duplication, no repeat-local
  `$index`, `ofType(type)` subtype/type-specifier validation, and
  `defineVariable()` non-leakage from `select()`/`repeat()` projections.
  Keep `.temp/qa/fp04_historian_fresh_probe.py` and
  `test_filter_projection_parity.py` aligned when changing §5.2 evaluator
  scope, type validation, or public native/fallback UDF wrappers.
- **FHIRPath FP-04 SKEPTIC fresh repeat `$index` scoping (2026-06-11):**
  **FIXED:** FHIRPath §5.2 defines `repeat(projection)` as a scoped function
  that sets `$this` for each queued item; unlike `where()` and `select()`, it
  does not set `$index` and the spec notes `$index` is undefined/not set during
  repeat iteration. Native C++ and forced Python fallback previously assigned a
  repeat-local counter, making `a.repeat($index)` unbounded in fallback and
  dependent on the native infinite-loop guard. `repeat()` now preserves any
  outer scoped `$index` without replacing it, so top-level `a.repeat($index)`
  is empty while `a.select($this.repeat($index))` can see the outer select
  index. Keep `.temp/qa/fp04_skeptic_fresh_probe.py`,
  `test_filter_projection_parity.py`, and native sqllogictest assertions
  aligned after future scoped-function edits; rebuild/copy the bundled
  extension after native evaluator changes.
- **FHIRPath FP-03 EXPLORER composed existence rerun (2026-06-11):**
  **VERIFIED CLEAN:** Fresh EXPLORER probing found no new §5.1 defects after
  the SKEPTIC/HISTORIAN fixes. Native DuckDB/C++ and forced Python fallback
  matched across 32 composed expressions covering vacuous empty defaults,
  nested `exists(criteria)`/`all(criteria)`, Boolean aggregate validation,
  scoped `subsetOf()`/`supersetOf()` arguments, structural JSON equality,
  compatible Quantity equality, numeric/string de-duplication, and invalid
  existence-helper arities. Keep `.temp/qa/fp03_explorer_fresh_probe.py` and
  `test_existence_parity.py` aligned when changing §5.1 dispatch or
  equality-backed set semantics.
- **FHIRPath FP-03 SKEPTIC scoped `subsetOf()`/`supersetOf()` argument context (2026-06-11):**
  **FIXED:** Fresh FP-03 SKEPTIC probing found native DuckDB/C++
  evaluating `subsetOf()` and `supersetOf()` argument expressions against the
  root resource instead of the current scoped item inside `select()`,
  `exists(criteria)`, and `all(criteria)`. Cases such as
  `groups.select(left.subsetOf(right))` and
  `groups.all(right.supersetOf(left))` diverged from the forced Python
  fallback and from FHIRPath scoped-function semantics. Native
  `Evaluator::evalFunction()` now evaluates those arguments against
  `outer_input` when present, matching other ordinary function arguments.
  Guard this with `.temp/qa/fp03_skeptic_fresh_probe.py`,
  `test_existence_parity.py::test_set_comparison_arguments_use_scoped_focus_in_native_and_fallback`,
  and native sqllogictest assertions when changing set-comparison argument
  evaluation; rebuild/copy the bundled extension after native evaluator edits.
- **FHIRPath FP-02 EXPLORER `implies` RHS singleton evaluation (2026-06-11):**
  **FIXED:** Fresh FP-02 EXPLORER probing found both native DuckDB/C++ and
  forced Python fallback short-circuiting `false implies <rhs>` before applying
  FHIRPath §4.5 singleton Boolean evaluation to `<rhs>`. Constant and dynamic
  multi-item RHS expressions such as `false implies (1 | 2)` and
  `false implies arr` returned `true`; per §4.2 Boolean logic, operands are
  evaluated as Booleans using §4.5 first. Python `logic.implies_op()` and
  native `Evaluator::evalBinaryOp()` now coerce the RHS before applying the
  false-LHS truth-table return, so multi-item RHS collections signal an
  evaluation error and public DuckDB UDFs return empty/NULL.
  Keep `.temp/qa/fp02_explorer_fresh_probe.py`,
  `test_boolean_logic_parity.py`, and native sqllogictest assertions aligned
  when touching `implies` evaluation.
- **FHIRPath FP-02 HISTORIAN native `trim()` invocation arity (2026-06-11):**
  **FIXED:** Fresh FP-02 HISTORIAN probing found native DuckDB/C++
  accepting argument-bearing `trim()` invocations such as `s.trim(1)` and
  `s.trim({})`, returning the trimmed string with `fhirpath_is_valid=true`.
  The forced Python fallback returns row-resilient empty results but also
  reports validity true. HL7 FHIRPath defines the string function signature as
  `trim() : String`, so `trim` is now exact-zero-arity in native validation
  and fallback `fhirpath_is_valid()`. Keep
  `.temp/qa/fp02_historian_fresh_probe.py`,
  `test_string_transform_parity.py`, and native sqllogictest assertions
  aligned after future string-function invocation changes; rebuild/copy the
  bundled extension after native evaluator edits.
- **FHIRPath FP-02 SKEPTIC function invocation fallback row resilience (2026-06-11):**
  **FIXED:** Fresh FP-02 SKEPTIC probing found the forced Python DuckDB
  fallback `fhirpath()` list UDF leaking `NotImplementedError` for unknown
  function invocations such as `unknownFunction()`, while native C++ returns
  the public row-resilient empty result and `fhirpath_is_valid()` returns
  false. `fhirpath_scalar()` now returns an empty collection for
  `NotImplementedError` in non-strict mode while preserving strict-mode
  propagation. Keep `.temp/qa/fp02_skeptic_diff_probe.py` and focused
  `test_operator_parity.py` native/fallback coverage aligned when touching
  fallback public UDF exception handling for function invocation errors.
- **FHIRPath FP-01 EXPLORER partial DateTime literal row resilience (2026-06-11):**
  **FIXED:** Fresh EXPLORER probing found forced Python fallback SQL UDFs throwing
  `FHIRPathSyntaxError` for invalid partial DateTime literals with time
  components after only a year or year-month, such as `@2014T14` and
  `@2014-01T14:30`, while the native DuckDB extension returned public
  empty/NULL results and `fhirpath_is_valid=false`. FHIRPath §4.1 allows a
  bare trailing `T` to mark partial DateTime values at year/year-month/full-date
  precision, but time components require a full date before `T`. Fallback
  `_has_invalid_partial_datetime_time_literal()` now classifies that invalid
  literal class, and public fallback SQL wrappers return native-matching
  empty/NULL results instead of throwing. Keep
  `.temp/qa/fp01_explorer_fresh_probe.py` and
  `test_literal_parity.py` aligned when touching fallback temporal prechecks
  or public row-resilient wrappers.
- **FHIRPath FP-01 HISTORIAN unpaired Unicode surrogate string escapes (2026-06-11):**
  **FIXED:** FHIRPath §4.1 String literal escapes require UTF-16 surrogate
  escape code units to be paired into a valid Unicode scalar value. Fresh
  FP-01 HISTORIAN probing found both native DuckDB and forced Python fallback
  reporting `fhirpath_is_valid("'\\uD834'") = true`; native result UDFs then
  throw DuckDB invalid-unicode errors and fallback scalar/text UDFs throw
  Python-to-C++ cast errors. Python `_unescape_fhirpath_string()` and native
  `appendUnicodeEscape()` now reject unpaired high/low surrogate code units
  while preserving existing malformed non-surrogate escape behavior such as
  `\u005` becoming `u005`. Keep `.temp/qa/fp01_historian_fresh_probe.py`,
  `test_literal_parity.py`, and `extensions/fhirpath/test/sql/fhirpath.test`
  aligned; rebuild/copy the bundled extension after native lexer changes.
- **FHIRPath FP-01 SKEPTIC DateTime timezone offset bounds (2026-06-11):**
  **FIXED:** FHIRPath §4.1 DateTime literals are FHIR/ISO-style temporal
  literals and the FHIR R4 `dateTime` primitive regex allows timezone offsets
  only through `13:59` or exactly `14:00`. Fresh FP-01 SKEPTIC probing found
  native DuckDB and forced Python fallback both accepting
  `@2016-02-29T23:59:59.123+14:01` and
  `@2016-02-29T23:59:59.123-14:01` as valid. Python `FP_DateTime.__new__`
  and native C++ `parseDateTimeParts()` now reject offset hours past 14 and
  reject nonzero minutes at hour 14, while preserving result-UDF
  row-resilience for malformed temporal literals. Keep
  `.temp/qa/fp01_skeptic_probe.py`, `test_literal_parity.py`, and
  `extensions/fhirpath/test/sql/fhirpath.test` aligned after future DateTime
  literal changes; rebuild and copy the bundled native extension after C++
  evaluator changes.
- **FHIRPath Section 5.1 native C++ arity validation (Domain 1 SKEPTIC, 2026-06-07):**
  **FIXED:** Native DuckDB/C++ FHIRPath now rejects invalid Section 5.1 helper
  arities in parity with the forced Python fallback. Ordinary helper dispatch
  is guarded in `Evaluator::evalFunction()` including the FHIR-specific
  zero-argument `hasValue()` helper, and `exists()` has its own guard in
  `Evaluator::evalExists()` because the parser emits `NodeType::ExistsCall`
  and bypasses generic function dispatch. Keep
  `test_existence_parity.py::test_existence_helpers_reject_invalid_arity_in_native_and_fallback`,
  `.temp/qa/domain1_skeptic_probe.py`, and the native sqllogictest surface
  aligned. Rebuild and copy `fhirpath.duckdb_extension` after future native
  evaluator changes.
- **SQL-on-FHIR runner JSON primitive boundary parity (SOF-VD-11 SKEPTIC fresh rerun, 2026-06-01):**
  **FIXED:** Native C++ member access must preserve raw JSON number text and
  numeric value for JSON primitives so `value.ofType(Quantity).value` authored
  as `1.0` reports precision `1` and boundaries `0.95000000`/`1.05000000`,
  matching the forced Python fallback. FHIR `date`, `dateTime`, and `time`
  JSON strings must coerce by field/choice metadata before
  `lowBoundary()`/`highBoundary()`, and root-level `where(criteria)` must use
  the same filtering path as chained `.where(criteria)`. Keep
  `test_environment_type_parity.py`, ViewDefinition runner regressions, and
  the SOF-VD-11 native/fallback spec_tests probe aligned; rebuild/copy the
  bundled extension after touching native evaluator paths.
- **FHIRPath FP-20 EXPLORER resource-specific code metadata rerun (2026-05-24):**
  **FIXED:** Native C++ reflection must not classify every unknown primitive
  string field as FHIR `string` when the R4 model defines a narrower primitive.
  `Questionnaire.subjectType` is a repeating FHIR `code`, so
  `Questionnaire.subjectType.type().name` must return `code` and
  `Questionnaire.subjectType.is(code)` must be true, matching the forced
  Python fallback. Keep `.temp/qa/fp20_explorer_probe.py`,
  `test_environment_type_parity.py`, and native sqllogictest assertions aligned;
  rebuild/copy the bundled extension after native `fhirFieldType()` changes.
- **FHIRPath FP-20 HISTORIAN external constant grammar rerun (2026-05-24):**
  **FIXED:** Native C++ must treat whitespace and comments after `%` as
  hidden tokens before reading the external constant identifier or string,
  matching the formal grammar `externalConstant: '%' (identifier | STRING)`.
  Expressions such as `% 'ucum'`, `%/*grammar*/'ucum'`,
  `%//grammar\n'ucum'`, `% \`context\`.id`, and
  `% \`vs-administrative-gender\`` are valid and must match the forced Python
  fallback. Keep `.temp/qa/fp20_historian_probe.py`,
  `test_environment_type_parity.py`, and `extensions/fhirpath/test/sql/fhirpath.test`
  aligned; rebuild and copy the bundled extension after native lexer changes.
- **FHIRPath FP-20 SKEPTIC environment/type reflection rerun (2026-05-24):**
  **FIXED:** Native C++ must enforce exact public helper signatures for
  Section 9/10 environment and reflection surfaces. `type()` takes no
  arguments; malformed calls such as `type(false)` and `1.type(false)` return
  empty/NULL in public result UDFs and make `fhirpath_is_valid()` false,
  matching the forced Python fallback. `defineVariable()` requires a singleton
  String variable name and one optional value expression; missing names,
  non-String names, empty name expressions, and extra arguments are invalid.
  Keep coverage in `test_environment_type_parity.py`,
  `.temp/qa/fp20_skeptic_probe.py`, and
  `extensions/fhirpath/test/sql/fhirpath.test`; rebuild and copy the bundled
  native extension after future changes in this area.
- **FHIRPath FP-19 EXPLORER aggregate arity rerun (2026-05-24):**
  **FIXED:** Native C++ `aggregate()` must enforce the §7.1 signature
  `aggregate(aggregator [, init])`. Zero-argument calls and calls with more
  than one `init` argument are invalid: public result UDFs return empty/NULL,
  while `fhirpath_is_valid()` returns false. Keep coverage in
  `test_aggregate_lexical_parity.py`, `.temp/qa/fp19_explorer_probe.py`, and
  `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the bundled
  extension after touching native aggregate dispatch.
- **FHIRPath FP-19 SKEPTIC aggregate/lexical rerun (2026-05-24):**
  **FIXED:** Native C++ now matches forced Python fallback for Section 7
  aggregate `init` scoping and Section 8 lexical handling. `aggregate()` passes
  the outer invocation focus to optional `init`, preserving resource-backed
  seeds such as `a.aggregate($total + $this, seed)` and
  `{}.aggregate($this + $total, seed)`. Native parser identifier alternatives
  now preserve valid keyword exceptions `as`, `contains`, `in`, and `is`, while
  requiring reserved operator keywords such as `div`/`mod` to be delimited.
  Native lexer whitespace is limited to space, tab, LF, and CR, so form-feed
  and vertical-tab are invalid like the fallback. Keep coverage in
  `test_aggregate_lexical_parity.py`, `.temp/qa/fp19_skeptic_probe.py`, and
  `extensions/fhirpath/test/sql/fhirpath.test`.
- **FHIRPath FP-18 EXPLORER arithmetic rerun (2026-05-24):**
  **FIXED:** Section 6.6/6.7 arithmetic must reject date/time results outside
  the valid FHIRPath year range and preserve row resilience in public DuckDB
  wrappers. Native C++ `fn_dateArith()` now throws `FHIRPathSpecError` when
  arithmetic would format year `0000` or `10000`, so literal overflow such as
  `@9999 + 1 year` is invalid and public result UDFs return empty/NULL.
  Forced Python fallback wrappers now catch `OverflowError` from
  `dateutil`/`datetime` arithmetic for both literal and resource-backed paths.
  The same pass aligned scalar divided by Quantity: `2 / 1 'mg'` returns
  `2 '1/mg'` on native and fallback instead of native `0.5 'mg'` or fallback
  `2 1/'mg'`. Keep coverage in `test_arithmetic_parity.py` and
  `.temp/qa/fp18_explorer_probe.py`.
- **FHIRPath FP-18 HISTORIAN arithmetic rerun (2026-05-24):**
  **FIXED:** Native C++ date/time arithmetic now rejects reversed or otherwise
  incompatible temporal arithmetic at validation time. `Quantity +
  Date/DateTime/Time`, `Date + Number`, and invalid date/time quantity units
  such as `@1974-12-25 - 1 'cm'` throw `FHIRPathSpecError` internally, so
  public result UDFs remain empty/NULL and `fhirpath_is_valid()` is false.
  Native Decimal `+`, `-`, and `*` preserve fixed-scale result text where
  operand scale is known, so `1.2 * 1.8` returns `2.16` like the forced Python
  fallback. Keep coverage in `test_arithmetic_parity.py` and
  `.temp/qa/fp18_historian_probe.py`.
- **FHIRPath FP-18 SKEPTIC arithmetic rerun (2026-05-24):**
  **VERIFIED:** Date/Time arithmetic must keep the official R4 second-vs-
  millisecond boundary: second-unit quantities use their integer portion, so
  `0.5 seconds` is a no-op at second/millisecond precision, while
  `500 milliseconds` applies sub-second arithmetic. Guard native C++ and forced
  Python fallback parity for `@T00:00:00.500 + 0.5 seconds`,
  `@2016-01-01T00:00:00.500 + 0.5 seconds`, `effectiveTime + 0.5 seconds`,
  and millisecond additions in `test_arithmetic_parity.py` and the fresh
  `.temp/qa/fp18_skeptic_probe.py`. The same pass fixed fallback
  `fhirpath_is_valid('(1 | 2) + 1')` by adding a string/comment-aware
  top-level math scanner for statically provable literal-union operands.
- **FHIRPath FP-17 EXPLORER boolean logic rerun (2026-05-24):**
  **VERIFIED:** Pathological Section 6.5 Boolean chains did not require new
  remediation after the SKEPTIC and HISTORIAN passes. Fresh native C++,
  forced Python fallback, and direct fallback probes matched for §6.8
  precedence cases such as `t or f implies f`, `f implies t and f`,
  `t xor {} or t`, and `t or f xor t`; chained root/member `not()`;
  singleton truthiness for strings and complex JSON; `where()` predicates
  containing `or`/`implies`; public row-resilient NULL/empty behavior for
  multi-item Boolean operands; and `fhirpath_is_valid()` parity for constant
  invalid operands. Keep `.temp/qa/fp17_explorer_probe.py` as the fresh
  edge-combination evidence pattern.
- **FHIRPath FP-17 HISTORIAN boolean logic rerun (2026-05-24):**
  **VERIFIED:** Systematic Section 6.5 coverage did not require new
  remediation after the FP-17 SKEPTIC fixes. Native C++ and forced Python
  fallback matched for all official truth-table cells for `and`, `or`, `xor`,
  and `implies`; root and method `not()`; invalid argument-bearing
  `not(false)` / `t.not(false)`; non-Boolean singleton truthiness for strings,
  numbers, and complex JSON; precedence from §6.8; and public row-resilient
  behavior for multi-item operands. Keep `.temp/qa/fp17_historian_probe.py`
  as the fresh matrix pattern. Temporary probes under `.temp/qa` should insert
  the repository root into `sys.path` because executing a script from `.temp`
  can otherwise import an installed stale `fhir4ds` package instead of the
  workspace tree.
- **FHIRPath FP-17 SKEPTIC boolean logic rerun (2026-05-24):**
  **FIXED:** Section 6.5 Boolean operators and `not()` must use Section
  4.5 singleton Boolean evaluation consistently across public DuckDB UDFs,
  native C++, forced Python fallback, and direct Python helper APIs. Direct
  `fhir4ds.fhirpath.duckdb.operators` helpers now treat any non-Boolean
  singleton as truthy and raise `FHIRPathError` for multi-item operands
  instead of silently returning empty. Native root `not()` now parses as a
  valid function over the current focus, while argument-bearing `not(false)`
  and `t.not(false)` are invalid and row-resilient public UDFs return
  empty/NULL. Keep coverage in `test_boolean_logic_parity.py` and
  `test_filter.py`.
- **FHIRPath FP-16 EXPLORER collection rerun (2026-05-24):**
  **VERIFIED:** Pathological Section 6.4 combinations did not require new
  remediation. Native C++ and forced Python fallback matched for empty-union
  singleton operands, invalid singleton operands wrapped in Boolean logic,
  Quantity candidates where an incompatible item precedes a compatible item,
  temporal precision mixtures, and complex object membership. Remember that
  union and membership use `=` equality, not `~` equivalence: complex objects
  whose list-valued child properties contain the same items in different order
  remain distinct under `|`, `in`, and `contains`.
- **FHIRPath FP-16 HISTORIAN collection rerun (2026-05-24):**
  **VERIFIED:** No additional remediation was required after systematic
  Section 6.4 coverage. Native C++ and forced Python fallback matched expected
  behavior for union duplicate elimination over numbers, strings, temporal
  values, FHIR Quantity paths, and complex JSON objects; `in`/`contains` empty
  propagation; singleton error row resilience plus `fhirpath_is_valid=false`
  for constant multi-item singleton operands; and equality-backed membership.
  Keep `.temp/qa/fp16_historian_probe.py` as the matrix pattern for future
  collection regressions.
- **FHIRPath FP-16 SKEPTIC collection rerun (2026-05-24):**
  **FIXED:** Section 6.4 membership operators need static singleton
  validation parity for constant literal unions. Native C++ already reported
  `fhirpath_is_valid=false` for `(1 | 2) in arr` and
  `arr contains (1 | 2)`, while forced Python fallback evaluated against a
  sparse validation resource and returned true. The fallback validator now
  checks only statically provable literal-union operands on the singleton side:
  left operand for `in`, right operand for operator `contains`. Preserve the
  distinction from string-function `s.contains(term)`, and keep duplicate
  elimination/numeric equality/empty-union cases such as `(1 | 1.0) in arr`
  valid. Dynamic row-dependent expressions still rely on public UDF
  row-resilience.
- **FHIRPath FP-15 EXPLORER type rerun (2026-05-24):**
  **VERIFIED:** No new remediation was required for Section 6.3 `is`/`as`
  after fresh EXPLORER probes over pathological type chains. Native C++ and
  forced Python fallback matched for `Any`/`System.Any`, nested choice
  assertions such as `component.value.ofType(Integer).as(Integer).is(Integer)`,
  `CodeableConcept` and `Quantity` choice paths, resource/complex supertypes,
  delimited type specifiers such as FHIR-qualified `Patient` and `Integer`,
  unknown type identifiers, static multi-item singleton errors, and
  data-dependent row-resilient public UDF behavior. Keep `.temp/qa/fp15_explorer_probe.py`
  as the fresh evidence pattern if this area is revisited.
- **FHIRPath FP-15 HISTORIAN type rerun (2026-05-24):**
  **FIXED:** Forced Python fallback `ofType()` now mirrors the
  Section 6.3 type-helper behavior added for `is`/`as`: `System.Any` should be
  the root type for typed filtering, and nested choice paths such as
  `Observation.component.value.ofType(Integer)` should retain the
  `valueInteger` item. The root cause was `filtering.of_type_fn()` using only
  generic `TypeInfo` equality/subtype checks instead of the same `System.Any`
  and unqualified choice primitive matching as `types.is_fn()` /
  `types.as_fn()`. Keep native/fallback coverage for `ofType(Any)`,
  `ofType(System.Any)`, and nested `component.value.ofType(...)` in
  `test_type_parity.py`.
- **FHIRPath FP-15 SKEPTIC type rerun (2026-05-24):**
  **FIXED:** Section 6.3 `is`/`as` must treat `System.Any` as the root/base
  type. Native C++ and forced Python fallback previously validated
  `System.Any` but returned false/empty for every singleton input, including
  literals, FHIR resources, FHIR primitives, and complex values. The fallback
  also lost unqualified capitalized choice primitive `as()` semantics when the
  assertion was chained, so `Observation.valueInteger` passed in native for
  `value.as(Integer).exists()` but failed in forced Python fallback. Preserve
  explicit namespace distinction: `value.as(System.Integer).exists()` and
  ordinary fields such as `active.as(Boolean).exists()` remain false, while
  unqualified choice assertions such as `value.as(Integer).exists()` remain
  valid. Keep coverage in `test_type_parity.py` and rebuild/copy the bundled
  extension after native type changes.
- **FHIRPath FP-14 EXPLORER one-sided DateTime timezone comparison (2026-05-24):**
  **FIXED:** Native C++ and forced Python fallback must expose the same
  implementation policy for DateTime comparisons where only one operand has a
  timezone offset. Native compares raw shared-precision fields when the other
  operand has no offset, so fallback `FP_TimeBase.compare()` must not strip the
  offset for normalization and then fall back to `_getDateTimeInt()` on the
  original offset-bearing object. Keep coverage for `<`, `>`, `<=`, and `>=`
  one-sided timezone DateTime comparisons in `test_comparison_parity.py`.
- **FHIRPath FP-14 HISTORIAN comparison rerun (2026-05-24):**
  **FIXED:** Section 6.2 comparison must not order Time-only values against
  Date or DateTime values. Native C++ already returned empty for
  `@2018-01-01 < @T10:00:00`, but the forced Python fallback compared the
  normalized temporal lists and returned a definitive Boolean. The fallback
  now treats Time-vs-Date/DateTime as an incompatible comparison domain before
  `FP_TimeBase.compare()` runs. Keep coverage in
  `test_comparison_parity.py::test_time_only_values_are_not_ordered_against_dates_or_datetimes`.
- **FHIRPath FP-14 SKEPTIC comparison rerun (2026-05-24):**
  **FIXED:** Section 6.2 comparison operators must not order Boolean
  operands, must treat multi-item operands as singleton errors internally,
  and must not compare calendar duration keywords with UCUM duration codes
  above seconds. Public DuckDB UDFs remain row-resilient and return empty/NULL
  for those evaluation errors, but literal invalid cases such as
  `true > false`, `(1 | 2) < 3`, and `1 < (2 | 3)` now make
  `fhirpath_is_valid()` false. Mixed calendar/UCUM comparisons such as
  `1 year > 1 'a'`, `1 month <= 1 'mo'`, and `1 minute > 1 'min'` return
  empty, while `10 seconds > 1 's'` and millisecond comparisons remain
  comparable. Keep coverage in `test_comparison_parity.py`; rebuild/copy the
  bundled native extension after touching native comparison logic.
- **FHIRPath FP-13 EXPLORER nested complex equality/equivalence rerun (2026-05-24):**
  **FIXED:** §6.1 complex equality/equivalence must recurse through child
  properties using the same FHIRPath semantics as direct child comparisons.
  Native C++ previously used exact raw JSON numeric equality for nested
  Decimal children, so `{"value":1.24} ~ {"value":1.2}` was false instead of
  true at the least precise Decimal scale. Both native and Python fallback also
  missed nested Quantity-shaped child values inside parent complex objects, so
  `rangeA = rangeB` and `rangeA ~ rangeB` failed when `rangeA.high` was
  `1 cm` and `rangeB.high` was `10 mm`, despite direct `rangeA.high = rangeB.high`
  succeeding. Keep nested Decimal/Quantity parent-object coverage in
  `test_equality_parity.py`; rebuild/copy the bundled native extension after
  touching native JSON equality recursion.
- **FHIRPath FP-13 HISTORIAN equality/equivalence rerun (2026-05-24):**
  **FIXED:** §6.1 ordered collection `=`/`!=` must preserve singleton
  equality's empty result when any paired item comparison is indeterminate.
  Native C++ previously used Boolean-only `fpValuesEqual()` for multi-item
  equality, so `(@2012 | @2013) = (@2012-01 | @2013)` and
  `(1 'cm' | 2 'cm') = (1 'g' | 2 'cm')` returned false instead of empty.
  The native path now uses tri-state singleton equality for ordered
  multi-item `=`/`!=`. The Python fallback complex equivalence path also now
  compares list-valued child properties with recursive order-independent
  matching instead of sorting, so complex children like
  `coding[{code:'A'},{code:'B'}] ~ coding[{code:'b'},{code:'a'}]` work.
  Keep these regressions in `test_equality_parity.py` and rebuild/copy the
  bundled extension after native equality changes.
- **FHIRPath FP-13 SKEPTIC equality/equivalence fresh rerun (2026-05-24):**
  **FIXED:** §6.1.2 multi-item equivalence must compare resource-backed
  Quantity values with full Quantity unit semantics, not generic JSON object
  equivalence. Fresh probe `component.value ~ referenceRange.high` over
  `Observation.component.valueQuantity` and `Observation.referenceRange.high`
  returned false in native C++ but true in forced Python fallback for
  `[1 cm, 2 cm]` versus `[0.02 m, 10 mm]`. Native `fpValueAsQuantity()` now
  preserves JSON Quantity value source text so equivalence tolerance uses the
  authored decimal precision before order-independent item matching. Forced
  Python fallback Decimal equivalence now uses `ROUND_HALF_UP` rather than
  default half-even rounding, so `1.25 ~ 1.2` returns false. Regression
  coverage lives in `test_equality_parity.py` and
  `extensions/fhirpath/test/sql/fhirpath.test`; rebuild/copy the bundled
  extension after touching native equality.
- **FHIRPath FP-12 EXPLORER descendants repeat semantics (2026-05-24):**
  **FIXED:** §5.8.2 defines `descendants()` as shorthand for
  `repeat(children())`, so it must only traverse newly produced child values
  under FHIRPath equality semantics. The Python fallback and native C++ path
  previously accumulated every recursive child, so repeated-looking nested
  JSON with duplicate primitive or complex values made
  `descendants().count() = repeat(children()).count()` false. Native repeat
  keys must canonicalize JSON object key order recursively; otherwise equal
  complex values like `{"x":1,"y":2}` and `{"y":2,"x":1}` drift from
  `repeat(children())`. Native `descendants()` must also avoid fixed shallow
  depth cutoffs; a 105-level resource must reach the deepest descendant while
  retaining the result-size safety guard. Keep repeated descendant value coverage in
  `test_tree_utility_parity.py` and rebuild/copy the bundled native extension
  after future tree-navigation changes.
- **FHIRPath FP-12 HISTORIAN tree/utility rerun (2026-05-24):**
  **FIXED:** §5.8 `descendants()` must not expose split JSON primitive
  extension containers that `children()` hides. The forced Python fallback now
  uses the same child projection for recursive descendants as `children()`,
  preserving native/fallback parity for resources with `_birthDate`-style
  primitive extension JSON. §5.9 `trace(name : String [, projection])` also
  requires ordinary `name` arguments to be evaluated in the outer invocation
  focus while only the optional projection is evaluated over the traced input;
  native C++ now matches fallback for dynamic labels such as
  `name.trace(id).given.count()`. Keep these cases in
  `test_tree_utility_parity.py` and rebuild/copy the bundled extension after
  native trace changes.
- **FHIRPath FP-12 SKEPTIC tree/utility signatures (2026-05-24):**
  **FIXED:** §5.8 `children()`/`descendants()` and §5.9
  `now()`/`today()`/`timeOfDay()` are exact zero-argument functions, and
  `trace(name : String [, projection])` requires a singleton String name plus
  at most one projection expression. Native C++ previously ignored extra
  arguments and ignored trace arguments entirely; fallback also accepted
  zero-argument `trace()`. Keep invalid-signature and trace projection
  row-resilience coverage in `test_tree_utility_parity.py` and rebuild/copy
  the bundled extension after native dispatcher changes.
- **FHIRPath FP-11 EXPLORER Decimal round source text (2026-05-24):**
  **FIXED:** Native C++ `round([precision])` must not round Decimal literals
  through binary `double` text formatting when the source literal text is
  available. `1.23456789.round(20)` preserves `1.23456789`, and half-up ties
  such as `1.005.round(2)` / `(-1.005).round(2)` produce `1.01` / `-1.01`,
  matching §5.7.8 and forced Python fallback behavior. Keep high-precision and
  tie cases in `test_math_parity.py` and rebuild/copy the bundled extension
  after touching native `fn_round()`.
- **FHIRPath FP-11 HISTORIAN round result type (2026-05-24):**
  **FIXED:** §5.7.8 declares `round([precision : Integer]) : Decimal` and
  says omitted precision defaults to 0, so `1.round()` must materialize the
  same Decimal result type as `1.round(0)`. Both `rround()` in the Python
  evaluator and `fn_round()` in the native evaluator now return Decimal for
  omitted precision, preserving `1.round() is Decimal = true` and
  `1.round() is Integer = false`. Keep native/fallback parity in
  `test_math_parity.py`.
- **FHIRPath FP-11 SKEPTIC math functions (2026-05-24):**
  **FIXED:** §5.7 math functions need exact signature validation, concrete
  numeric type errors, dynamic argument focus, and result type preservation
  across native C++ and forced Python fallback. Guard wrong-arity calls such as
  `1.abs(2)`, `10.log()`, `2.power(3, 4)`, and `2.sqrt(1)`;
  incompatible constants such as `'2.5'.sqrt()` and `true.abs()` must make
  `fhirpath_is_valid=false` while public result UDFs remain row-resilient.
  Sourced `p.log(base)` evaluates `base` in the outer resource focus.
  Superseding current §5.7 behavior from 2026-06-12: `ceiling()`, `floor()`,
  `round()`, and `truncate()` accept Quantity, and `power()` returns Decimal.
  Keep coverage in `test_math_parity.py` and rebuild/copy the bundled
  extension after native math changes.
- **FHIRPath FP-10 EXPLORER Unicode case mapping (2026-05-24):**
  **FIXED:** Native C++ `upper()`/`lower()` hand-maintained Unicode mapping
  now covers the EXPLORER dotted/dotless Turkish I and accented Greek vowel
  case pairs that diverged from the forced Python fallback:
  `İSTANBUL.lower()`, `ıstanbul.upper()`, `άέήίόύώ.upper()`, and
  `ΆΈΉΊΌΎΏ.lower()`. Keep native/fallback coverage in
  `test_string_transform_parity.py` and rebuild/copy the bundled extension
  after future `fn_upper`/`fn_lower` changes.
- **FHIRPath FP-10 HISTORIAN string-transform rerun (2026-05-24):**
  **FIXED:** §5.6.6-§5.6.12 transform parity must include malformed regex
  syntax, singleton empty strings, and broader UTF-8 case mapping beyond the
  initial examples. Native `fhirpath_is_valid()` now compiles regex literals
  during validation so malformed patterns such as `s.matches('[invalid')` are
  invalid even on sparse validation input. Forced Python fallback regex
  compilation raises `FHIRPathError`, preserving row-resilient empty/NULL
  public UDF behavior. Forced fallback `replace()` preserves a present empty
  string when the pattern is non-empty and not found, so `empty.replace('z',
  'x')` returns `['']`, not empty collection. Native C++ maps additional Latin
  Extended-A pairs such as `č/Č`, `ž/Ž`, and `š/Š`. Keep fresh native vs forced
  fallback coverage in `test_string_transform_parity.py` and rebuild/copy the
  bundled extension after native transform changes.
- **FHIRPath FP-10 SKEPTIC string-transform rerun (2026-05-24):**
  **FIXED:** §5.6.6-§5.6.12 transform functions now have native and forced
  fallback parity for exact arity, dynamic argument focus, singleton String
  input, and regex safety. Native C++ rejects extra-argument transforms such as
  `s.upper(1)`, `s.replace('a','b','c')`, `s.matches('a','b')`,
  `s.length(1)`, and `s.toChars(1)`; sourced `s.replace(pattern, sub)` and
  `s.matches(regex)` evaluate arguments against sibling resource fields; the
  fallback `length()` helper enforces singleton input; and
  `fhirpath_is_valid()` rejects obvious non-String literals and dangerous regex
  literals, including patterns over 1000 characters, before sparse validation
  can hide them. Preserve native vs forced fallback coverage in
  `test_string_transform_parity.py`.
- **FHIRPath FP-09 EXPLORER literal-union validation (2026-05-24):**
  **FIXED:** Forced Python fallback `fhirpath_is_valid()` must reason about
  literal union arguments using FHIRPath singleton and union semantics, not a
  token-only "`|` means invalid" shortcut. Multi-item literal unions such as
  `s.substring((1|2))`, `s.substring(1, (1|2))`, and
  `missing.indexOf(('a'|'b'))` are invalid for singleton FP-09 parameters,
  while duplicate-eliminating unions such as `s.indexOf(('a'|'a'))` and
  `s.substring((1|1))` are valid. Numeric equality also matters:
  `s.substring((1|1.0))` preserves the first effective Integer item and is
  valid, while `s.substring((1.0|1))` preserves the first Decimal item and is
  invalid for an Integer parameter. Keep native C++ and forced fallback parity
  in `test_string_search_parity.py`.
- **FHIRPath FP-09 HISTORIAN string-search argument focus
  (2026-05-24):** **FIXED:** Native C++ string-search functions must evaluate
  ordinary value arguments against the outer invocation focus for sourced calls,
  not against the source string itself. Guard `s.indexOf(term)`,
  `s.substring(start, length)`, `s.startsWith(prefix)`, `s.endsWith(suffix)`,
  and `s.contains(term)` where `term`/`start`/`length`/`prefix`/`suffix` are
  sibling resource fields. Literal arguments and no-source calls still evaluate
  in the current focus, and scoped functions still own their `$this`/`$index`
  behavior. Keep coverage in `test_string_search_parity.py` and native
  `extensions/fhirpath/test/sql/fhirpath.test`.
- **FHIRPath FP-09 SKEPTIC string-search validation (2026-05-24):**
  **FIXED:** §5.6 string-search functions must enforce exact signatures and
  concrete parameter types before sparse validation input can hide malformed
  calls. Guard `indexOf(substring)`, `substring(start[, length])`,
  `startsWith(prefix)`, `endsWith(suffix)`, and string-function
  `contains(substring)` against missing/extra arguments, non-String search
  terms, non-Integer substring bounds, constant non-String inputs, and
  multi-item literal parameters. Native C++ throws `FHIRPathSpecError` for
  semantic violations while public DuckDB result UDFs remain row-resilient;
  forced Python fallback `fhirpath_is_valid()` includes a static FP-09 arity
  and literal-argument precheck so native/fallback validation stays aligned.
  Keep coverage in `test_string_search_parity.py` and native
  `extensions/fhirpath/test/sql/fhirpath.test`.
- **FHIRPath FP-08 EXPLORER empty optional Quantity unit arguments
  (2026-05-24):** **FIXED:** Forced Python fallback must distinguish an
  omitted `toQuantity([unit])` / `convertsToQuantity([unit])` optional unit
  argument from an explicitly empty unit argument such as `{}`. `make_param()`
  returns `[]` for the empty argument; per FHIRPath empty-argument propagation,
  `1.toQuantity({})` and `1.convertsToQuantity({})` return empty, not
  `1 '1'` or `true`. Keep native C++ and forced Python fallback parity
  coverage in `test_fp08_empty_quantity_unit_parity.py`.
- **FHIRPath FP-08 HISTORIAN resource-backed Quantity conversion
  (2026-05-24):** **FIXED:** `toQuantity([unit])`,
  `convertsToQuantity([unit])`, `toString()`, and `convertsToString()` must
  treat valid FHIR Quantity path values as Quantity input, not as opaque JSON
  objects. Native C++ now materializes Quantity-like `JsonVal` values through
  the strict Quantity parser before conversion/stringification; Python fallback
  uses strict ResourceNode/dict Quantity parsing, rejects non-finite or
  non-numeric `value` fields, and preserves fractional compatible-unit
  conversion such as `5 mg -> 0.005 g`. Keep resource-backed valid/invalid
  Quantity cases in `test_conversion_parity.py` and rebuild/copy the bundled
  extension after native serialization or conversion changes.
- **FHIRPath Section 5.5 Quantity/String/Time conversion (FP-08 SKEPTIC rerun,
  2026-05-24):** **FIXED:** FP-08 converters enforce exact signatures and
  singleton rules across native C++ and forced Python fallback. Guard invalid
  forms such as `s.toString(1)`, `time_min.toTime(1)`,
  `1.toQuantity('1','g')`, `1.toQuantity(1)`,
  `1.convertsToQuantity(('1'|'g'))`, `s.convertsToString(1)`,
  `convertsToString(s)`, `convertsToTime(time_min)`,
  `(1|2).toString()`, and `(1|2).convertsToQuantity()`. Native must validate
  optional Quantity unit arguments as singleton Strings before conversion, and
  fallback does not preserve old global `convertsToString(value)` /
  `convertsToTime(value)` convenience forms. Keep
  `test_conversion_parity.py::test_fp08_conversion_signatures_and_singleton_errors_match_fallback`
  and native sqllogictest coverage aligned.
- **FHIRPath FP-08 dynamic Quantity unit arguments (2026-06-12):** **FIXED:**
  Native C++ `toQuantity([unit])` and `convertsToQuantity([unit])` resolve
  dynamic unit arguments such as `targetUnit` against the outer invocation
  context, matching forced Python fallback behavior for sibling unit paths.
  Guard `value.toQuantity(targetUnit)`,
  `quantityText.toQuantity(targetUnit)`, and
  `items.select(quantityText.toQuantity(targetUnit))` across native and forced
  fallback paths.
- **FHIRPath Section 5.5 Date/DateTime/Decimal conversion (FP-07 SKEPTIC rerun, 2026-05-24):**
  **FIXED:** FP-07 conversion functions must keep exact zero-argument
  signatures across native C++ and forced Python fallback. Guard invalid forms
  such as `'1'.toDecimal(2)`, `'2015'.toDate(2)`,
  `'2015'.toDateTime(2)`, `'1'.convertsToDecimal(2)`, and global
  `convertsToDate(value)`/`convertsToDateTime(value)`/`convertsToDecimal(value)`.
  Native `toDecimal()` must not stringify Date/DateTime values such as
  `@2015.toDecimal()`, and fallback temporal converters recognize
  FP_Date/FP_DateTime literal inputs while raising on multi-item
  `toDecimal()` input so `fhirpath_is_valid()` stays aligned. Keep
  `test_conversion_parity.py` and native sqllogictest coverage together.
- **FHIRPath Section 5.5 EXPLORER rerun (FP-06, 2026-05-24):**
  **FIXED:** Forced Python fallback wrapper normalization for no-whitespace
  quoted Quantity literals must not run inside ordinary string literals.
  A global regex rewrote `iif('1'.convertsToInteger(), 'T', 'F')` to use
  the string `'1 '`, causing the wrong lazy branch to be selected. The
  fallback unary polarity evaluator must also create `DescendingSortMarker`
  only while evaluating `sort()` criteria; ordinary expressions such as
  `-1.convertsToInteger()` parse as `-(1.convertsToInteger())` and must
  return public empty/NULL row resilience with `fhirpath_is_valid=false`,
  matching native C++ and FHIRPath §6.8 precedence.
- **FHIRPath Section 5.5 HISTORIAN rerun (FP-06, 2026-05-24):**
  **FIXED:** `iif` and conversion function signature validation must be exact
  across native C++ and forced Python fallback. Native now rejects malformed
  `iif(true)`, extra-argument `iif(true, 'yes', 'no', 'extra')`,
  multi-item criteria such as `iif(1|2, 'yes', 'no')`, and extra-argument
  zero-argument conversions such as `true.toBoolean(1)` and
  `'1'.toInteger(2)`. Forced fallback now raises on constant multi-item
  converter inputs such as `(true|false).toBoolean()` and
  `(1|2).convertsToInteger()` so `fhirpath_is_valid()` matches native while
  public result UDFs stay row-resilient. Keep the subprocess-style local-path
  probe pattern for `.temp` scripts so they import the workspace package
  instead of an installed wheel.
- **FHIRPath Section 5.5 conversion arity (FP-06 SKEPTIC rerun,
  2026-05-24):** **FIXED:** `convertsToBoolean()` and
  `convertsToInteger()` are zero-argument conversion functions in the
  FHIRPath spec. Native C++ and forced Python fallback now reject invalid
  argument-bearing forms such as `'true'.convertsToBoolean(2)`,
  `'1'.convertsToInteger(2)`, `convertsToBoolean(strTrue)`, and
  `convertsToInteger(strInt)` with public empty/NULL row resilience and
  `fhirpath_is_valid=false`. Keep parity coverage for public result UDFs plus
  `fhirpath_is_valid()`.
- **FHIRPath Section 5.3/5.4 EXPLORER rerun (FP-05, 2026-05-24):**
  **FIXED:** Forced Python fallback `skip(num)` and `take(num)` must treat an
  empty count argument such as `a.skip({})` or `a.take({})` as spec-valid empty
  propagation, not as an invalid integer conversion. `make_param()` represents
  an empty singleton argument as `[]`; `take_fn`/`skip_fn` must return empty
  before integer coercion. Keep native C++ and forced fallback parity coverage
  for `fhirpath_is_valid()` on empty count arguments.
- **FHIRPath Section 5.3/5.4 SKEPTIC rerun (FP-05, 2026-05-24):**
  **FIXED:** Native C++ must enforce exact arity for subsetting and combining
  functions. Malformed calls such as `a.first(0)`, `a.tail(0)`, `a.skip()`,
  `a.skip(1, 2)`, `a.combine()`, and `a.union(b, ints)` must return public
  empty/NULL row resilience with `fhirpath_is_valid=false` in both native C++
  and forced Python fallback. Validate `skip(num)`/`take(num)` argument count
  and Integer type before empty-input short-circuiting so sparse validation
  resources do not mask malformed arguments. Rebuild and copy the bundled
  extension after native evaluator changes.
- **FHIRPath Section 5.2 EXPLORER rerun (FP-04, 2026-05-24):**
  **FIXED:** Native Section 5.2 function calls must enforce exact arity and
  type-specifier shape for `where(criteria)`, `select(projection)`,
  `repeat(projection)`, and `ofType(type)`. Native C++ now rejects malformed
  calls such as `Patient.where()`, `item.where(true, false)`,
  `item.select(linkId, item)`, `item.repeat()`, and
  `Patient.ofType('Patient')` instead of returning data. Forced fallback now
  resolves nested choice values for
  `entry.resource.ofType(Observation).value.ofType(Integer)` by applying the
  existing TypeSpecifier/filtering path to the evaluated source expression.
  Keep native and forced fallback parity coverage for malformed
  arity/type-specifier calls and nested choice-type `ofType`.
- **FHIRPath Section 5.2 HISTORIAN rerun (FP-04, 2026-05-24):**
  **FIXED:** Native `ofType()` with a missing type argument must be invalid.
  The FHIRPath Section 5.2.4 signature is `ofType(type : type specifier)`,
  and public `fhirpath_is_valid()` must reject wrong type-function arity even
  when public result UDFs convert the resulting spec error to empty/NULL for
  row resilience. Keep native and forced fallback coverage for
  `entry.resource.ofType()` alongside unknown-type validation.
- **FHIRPath Section 5.2 SKEPTIC rerun (FP-04, 2026-05-24):**
  **FIXED:** `ofType(type)` must validate that the type argument resolves to a
  model type even when the input collection is empty. Native
  `evalOfType` now validates the resolved type specifier before iterating input,
  so `fhirpath_is_valid()` returns false for paths such as
  `entry.resource.ofType(NotAType).id` even when validation uses a sparse
  Patient sample that makes the source path empty. Keep native and forced
  fallback coverage for unknown `ofType` specifiers.
- **FHIRPath Section 5.1 EXPLORER rerun (FP-03, 2026-05-24):**
  **FIXED:** `exists(criteria)` is specified as `where(criteria).exists()`,
  so criteria evaluation must not short-circuit before validating later items.
  A collection where the first item yields `true` and a later item yields a
  multi-item Boolean, such as `nested.exists(flags)` over `flags=[true]` then
  `flags=[false,true]`, must surface a criteria singleton error that public
  DuckDB wrappers convert to empty/NULL. The forced Python fallback
  `fhirpath_is_valid()` scanner now ignores logical operator keywords followed
  by parenthesized operands, such as `and (` in `all(criteria)`, without
  allowing actual unknown functions.
- **FHIRPath §4.2-§4.5 operator/function QA rerun (FP-02 EXPLORER, 2026-05-24):**
  **FIXED:** Native unary `+`/`-` evaluation must enforce singleton input
  after parsing dot/function invocation, because §6.8 gives `.` higher
  precedence than unary operators. The normative example `-7.combine(3)`
  parses as `-(7.combine(3))` and must return public empty/NULL row
  resilience instead of using the first item. Forced Python fallback wrapper
  prechecks must not reject leading unary `+` as syntax; `+7.combine(3)` is
  syntactically valid and fails at singleton evaluation. Keep native SQL and
  forced fallback parity coverage for both unary signs plus the parenthesized
  control `(-7).combine(3)`.
- **FHIRPath §4.2-§4.5 operator/function QA rerun (FP-02 SKEPTIC, 2026-05-24):**
  **FIXED:** Native C++ operator precedence must treat `is`/`as` as higher
  precedence than union `|`, matching the normative §6.8 table. Guard cases
  include ``1 | 2 is Integer`` and ``1 | 'a' as String`` across native and
  forced Python fallback surfaces. Native string helpers such as `trim()` must
  enforce singleton input instead of silently using the first item of a
  multi-item collection. Rebuild and copy the bundled extension after touching
  native parser/evaluator paths.
- **FHIRPath §4.1 literal QA rerun (FP-01 EXPLORER, 2026-05-24):**
  **FIXED:** Temporal literals must reject year `0000` across Date and
  DateTime surfaces, quoted Quantity units must use the same string-unescape
  pass as ordinary string literals, empty quoted Quantity units such as
  ``1 ''`` are invalid, and Python fallback equality must return empty rather
  than raising when literal `|` de-duplication compares temporal values with
  non-string/non-temporal values. Keep native C++ and forced Python fallback
  parity coverage for `fhirpath`, typed wrappers, and `fhirpath_is_valid()`.
- **FHIRPath §4.1 literal QA rerun (FP-01 SKEPTIC, 2026-05-23):**
  **FIXED:** Forced Python fallback must preserve no-whitespace quoted UCUM
  Quantity literals such as ``10'mg'`` through syntax prechecks before masking
  strings, because the formal grammar is `quantity: NUMBER unit?`. String
  unescape now combines valid UTF-16 surrogate-pair escapes such as
  ``'\uD834\uDD1E'`` into one Unicode scalar value. Keep native C++ and forced
  Python fallback parity coverage for `fhirpath`, scalar/text/json helpers, and
  `fhirpath_is_valid()` when changing literal lexing.
- **FHIRPath §4.1 literal QA rerun (FP-01 HISTORIAN, 2026-05-23):**
  **FIXED:** Typed DuckDB wrappers must not stringify arbitrary literal
  classes. `fhirpath_timestamp` returns only DateTime-shaped results, and
  `fhirpath_quantity` returns only Quantity literals or JSON Quantity objects.
  Forced Python fallback prechecks reject timezone-suffixed Date/partial
  DateTime literals and out-of-range Integer literals before compile. When
  testing forced fallback, create/register the fallback connection before
  loading the native extension or isolate backends in subprocesses.
- **`fhirpath_is_valid()` unknown-function detection in lazy branches (Release 0.0.6 Domain 2, 2026-05-20):**
  **FIXED:** Forced Python fallback used to validate by evaluating against a
  sample Patient, so unknown functions hidden in an unselected `iif()` branch
  could return `true` even though native C++ rejected the AST. Validation now
  scans function calls outside strings/comments/delimited identifiers/temporal
  literals before sample execution. Preserve `iif()` short-circuiting for
  evaluation while keeping public native and forced fallback
  `fhirpath_is_valid()` aligned.
- **Quantity.value type reflection fallback parity (SOF-VD-11 SKEPTIC, 2026-05-20):**
  **FIXED:** Python fallback FHIRPath must report `valueQuantity.value.type().name`
  and `value.ofType(Quantity).value.type().name` as `decimal`, matching native
  C++. `ResourceNode.get_type_info()` should trust numeric/Boolean JSON value
  shape before broad suffix fallbacks such as `.value -> string` when no exact
  model path exists. This protects SQL-on-FHIR ViewDefinition runtime type
  guards for Observation decimal columns.
- **SQL-on-FHIR `fhirpath_repeat` deep fallback traversal (SOF-VD-07 EXPLORER, 2026-05-20):**
  **FIXED:** The forced Python fallback must not rely on Python/orjson
  recursion limits when parsing, evaluating, traversing, or serializing
  deeply nested raw JSON for `fhirpath_repeat`. Keep the fallback traversal
  iterative, temporarily raise the parser/evaluator recursion budget from the
  actual JSON nesting depth under the repeat fallback recursion-limit lock, and
  use the iterative serializer for repeated child JSON output. Guard with
  native-vs-fallback ViewDefinition repeat coverage over raw nested
  `QuestionnaireResponse.item` JSON beyond the default Python recursion limit.
- **DuckDB fallback `$this` current-focus parity (SOF-VD-07 HISTORIAN, 2026-05-20):**
  **FIXED:** The forced Python fallback must treat `$this` as the current
  focus and must split `$name.path` variable expressions before evaluating the
  trailing FHIRPath. Native C++ already returns the current JSON focus for
  `$this`/`$this.path`; fallback code must match for direct UDF calls,
  `fhirpath_repeat` entries such as `$this.item`, and SQL-on-FHIR
  ViewDefinition repeat columns such as `$this.linkId`.
- **SQL-on-FHIR `fhirpath_repeat` parity (SOF-VD-07 SKEPTIC, 2026-05-20):**
  **FIXED:** The public DuckDB `fhirpath_repeat(resource, paths_json)` surface
  must treat `paths_json` entries as FHIRPath expressions, not a separate
  dotted-key mini-language. Python fallback and native C++ must both evaluate
  each repeat expression from the current repeated object, recursively visit
  object results to parsed JSON depth, union duplicate node hits across paths,
  and match ViewDefinition `select.repeat` execution. Rebuild and copy the
  bundled `fhirpath.duckdb_extension` after native repeat changes.
- **Review-20 environment-variable explicit policy (2026-05-17):** Native C++ and forced Python fallback must share the same explicit environment-variable policy. Built-ins and known default variables such as ``%`vs-administrative-gender``` and ``%`ext-patient-birthTime``` remain valid, but arbitrary `%vs-*`/`%ext-*`, `%factory`, and `%terminologies` are invalid unless implemented deliberately in both backends. Keep `test_environment_type_parity.py` and native `extensions/fhirpath/test/sql/fhirpath.test` guard cases aligned; rebuild and copy the bundled `fhirpath.duckdb_extension` after native environment-variable changes.
- **FHIRPath §9 environment variable scope parity (FP-20 EXPLORER, 2026-05-17):** **FIXED:** The native extension exposes `defineVariable()` as a public environment-variable helper, so the forced Python fallback must implement the same scoped behavior. Variables defined in an invocation chain remain visible to later invocations in that chain, but variables created inside `where()`/`select()`/`repeat()`/`all()`/`aggregate()` expression parameters must be restored afterward. Guard cases: `defineVariable('x', id).select(%x)`, `name.select(defineVariable('x', family).select(%x))`, same-chain redefinition returning invalid/empty, system-variable overwrite returning invalid/empty, and `a.where(defineVariable('leak', $this).exists()).select(%leak)` returning empty/NULL in both native and forced fallback.
- **FHIRPath §10 type reflection metadata (FP-20 HISTORIAN, 2026-05-17):** **FIXED:** Public native and forced Python fallback `type()`/`is()`/`as()` surfaces must preserve FHIR metadata for Reference, Attachment, URI, and media-type fields. Native `type()` returns one TypeInfo per input item and serializes TypeInfo JSON in the same public key order as the Python fallback. Guard cases: `managingOrganization.type().name = 'Reference'`, `managingOrganization.is(Reference)`, `Questionnaire.url.type().name = 'uri'`, `Parameters.parameter[0].valueUri.type().name = 'uri'`, `(1|2).type().count() = 2`, and `DocumentReference.content.attachment.contentType.type().name = 'code'`. Rebuild and copy the bundled extension after native type-reflection changes.
- **FHIRPath §9-§11 environment/type safety (FP-20 SKEPTIC, 2026-05-17):** **FIXED:** Undefined environment variables are strict evaluator errors; public DuckDB wrappers convert them to empty/NULL for row resilience, but `fhirpath_is_valid()` must be false in both native C++ and forced Python fallback. Both normative environment variable forms, ``%`name``` and `%'name'`, must share string escape handling. Anonymous/self-aliased BackboneElement metadata such as `Patient.contact` must not create self-referential type hierarchy loops; normalize those type checks to `BackboneElement` and keep native/fallback parity for `contact.is(BackboneElement)` and `contact.as(BackboneElement).name.family`. Rebuild and copy the bundled `fhirpath.duckdb_extension` after native lexer/type changes.
- **FHIRPath no-whitespace calendar quantity literals (FP-19 EXPLORER, 2026-05-17):** **FIXED:** DuckDB Python fallback wrapper syntax prechecks must allow the §12.1 grammar shape `quantity: NUMBER unit?` even when no whitespace separates the number and calendar duration unit. Valid public cases include `1month`, `1months`, `1millisecond`, and `1year + 2months`; invalid suffixes such as `1foo`, `123abc`, uppercase `1Month`, and `1 Month` remain invalid. Keep native-vs-forced-fallback coverage in `test_aggregate_lexical_parity.py`.
- **FHIRPath §7 aggregate scope restoration (FP-19 HISTORIAN, 2026-05-17):** **FIXED:** Python core/fallback expression-parameter evaluation must restore `$this` after each parameter expression, and `aggregate()` must restore `$total`/`$index` after returning. Regression cases: `(1|2).aggregate($this+$total, 0) + $index` and `... + $total` return empty/NULL, while `combine($index)`/`combine($total)` do not append leaked loop variables. Keep direct core tests plus native-vs-forced-fallback DuckDB parity in `test_conformance_regressions.py` and `test_aggregate_lexical_parity.py`.
- **FHIRPath §8 wrapper comment prechecks (FP-19 HISTORIAN, 2026-05-17):** **FIXED:** DuckDB Python fallback wrapper syntax heuristics must strip ignored comments before applying leading-operator/trailing-token regex checks, and delimiter-balance checks must ignore strings, delimited identifiers, and comments. Valid leading comments such as `/* leading */ id` and `// leading\nid` must match native C++ and remain `fhirpath_is_valid=true`.
- **FHIRPath §8 delimited identifier escapes (FP-19 SKEPTIC, 2026-05-17):** **FIXED:** Delimited identifiers must use the same left-to-right escape handling as FHIRPath strings. Do not strip backticks with global replacement because escaped interior backticks are part of the model key. Regression cases: `` `back\`tick` ``, `` `line\nbreak` ``, and `` `omega\u03A9` ``. Keep direct core tests plus native-vs-forced-fallback DuckDB parity in `test_conformance_regressions.py` and `test_aggregate_lexical_parity.py`.
- **FHIRPath parser full-consumption rule (FP-19 SKEPTIC, 2026-05-17):** **FIXED:** The Python core parser must reject trailing unconsumed tokens after parsing an expression. Case-sensitive lexical mistakes such as `1 Month` must not evaluate as the prefix `1`. `parser.parse()` checks for EOF after `parser.expression()`; keep this guard when changing parser recovery or wrapper prechecks.
- **FHIRPath §6.7 no-whitespace temporal arithmetic (FP-18 EXPLORER, 2026-05-17):** **FIXED:** Native C++ temporal literal lexing must not consume `+`/`-` as timezone text unless a complete `(+|-)hh:mm` offset follows. Operators do not require whitespace, so expressions such as `@T23+119 minutes`, `@2016-02-29T23+119 minutes`, and `@2016-02-29T23:59+61 seconds` must parse as temporal arithmetic and match the forced Python fallback. Regression coverage lives in `test_arithmetic_parity.py`; rebuild and copy the bundled `fhirpath.duckdb_extension` after lexer changes.
- **FHIRPath §6.7 hour-precision Time arithmetic (FP-18 HISTORIAN, 2026-05-17):** **FIXED:** The Python fallback `FP_TimeBase._plus_time()` must handle hour-only `Time` precision explicitly. More precise units convert down to hours with truncation before addition (`@T12 + 61 minutes -> T13`, `@T12 + 59 minutes -> T12`), and `Time` arithmetic must reject date units such as days/months/years (`@T12 + 1 day` returns empty/invalid). Native C++ already followed this rule; keep native and forced Python fallback parity in `test_arithmetic_parity.py`.
- **FHIRPath §6.7 Date/Time arithmetic (FP-18 SKEPTIC, 2026-05-17):** **FIXED:** Native C++ and forced Python fallback must reject definite UCUM year/month quantities (`1 'a'`, `1 'mo'`) in date/time arithmetic, reject time-based units on `Date` values below day precision, preserve explicit DateTime timezone offsets at every time precision, avoid adding `+00:00` to no-timezone DateTimes, and convert more-precise quantities down to partial `Time` precision instead of promoting the result. Regression cases: `@2016 + 1 'a'` returns empty/invalid, `@2016-02-29 + 23 hours` returns empty/invalid, `@T12:34 + 30 seconds` remains `T12:34`, `@T00:00:00 - 1 millisecond` remains `T00:00:00`, and FHIR temporal path values such as `effectiveDateTime + 1 second` and `effectiveTime + 750 milliseconds` work in both native and forced fallback.
- **FHIRPath §6.6 Math/Quantity arithmetic parity (FP-18 SKEPTIC, 2026-05-17):** **FIXED:** Native C++ and forced Python fallback public DuckDB arithmetic must agree on `div`, `mod`, 32-bit integer overflow, and compatible Quantity operations. Decimal `div` may return integer-shaped output, decimal `mod` must preserve rounded source text instead of binary double artifacts, 32-bit integer overflow promotes to Decimal at the public surface, compatible Quantity `+`/`-`/`*` canonicalize through base units, and compatible same-dimension Quantity `/` returns dimensionless Quantity `1 '1'` rather than a bare Decimal. Guard the official R4 `testQuantity11` shape and public parity cases in `test_arithmetic_parity.py`; rebuild and copy the bundled extension after native arithmetic changes.
- **FHIRPath §6.5 Boolean truth tables and precedence (FP-17 HISTORIAN, 2026-05-17; corrected FP-02 EXPLORER, 2026-06-11):** **FIXED:** Native C++ and forced Python fallback public DuckDB UDFs agree on the full `and`/`or`/`xor`/`implies`/`not()` three-valued truth tables, singleton non-Boolean truthiness, `and` binding tighter than `or`/`xor`, left-associative `or`/`xor` and `implies`, and multi-item operand row resilience. `false implies <rhs>` may return `true` only after `<rhs>` has passed §4.5 singleton Boolean evaluation; multi-item RHS collections such as `false implies arr` are errors. Regression coverage lives in `test_boolean_logic_parity.py`.
- **FHIRPath §6.5 multi-item Boolean operands (FP-17 SKEPTIC, 2026-05-17; corrected FP-02 EXPLORER, 2026-06-11):** **FIXED:** Boolean operators must run singleton Boolean evaluation before applying three-valued truth tables. A multi-item operand is a semantic error that public DuckDB UDFs convert to empty/NULL; it must not be treated like empty just because another operand determines the truth-table result. Regression cases: `arr or true`, `arr and false`, `arr implies true`, and `false implies arr` where `arr` has multiple items.
- **FHIRPath §6.4 membership singleton errors (FP-16 EXPLORER, 2026-05-17):** **FIXED:** Strict/core evaluation must raise when `in` receives a multi-item left operand or `contains` receives a multi-item right operand. Public DuckDB UDFs intentionally catch those semantic errors and return empty/NULL for row resilience, so keep both direct core tests and native-vs-forced-fallback public UDF parity tests. Guard cases: `a in one` and `one contains a` where `a` has multiple items.
- **FHIRPath §6.4 collection operators with FHIR Quantity paths (FP-16 HISTORIAN, 2026-05-17):** **FIXED:** Native C++ `fpValuesEqual()` now materializes Quantity-like JSON path values before collection membership/de-duplication, matching ordinary `=` behavior and the forced Python fallback. Guard cases: `value = component.value`, `value in component.value`, `component.value contains value`, `(value | component.value).count()`, and `value.union(component.value).count()` where `Observation.valueQuantity` is `1 cm` and `component.valueQuantity` is `10 mm`. Rebuild and copy the bundled `fhirpath.duckdb_extension` after touching this helper.
- **FHIRPath §6.4 membership/containership equality (FP-16 SKEPTIC, 2026-05-17):** **FIXED:** `in` and `contains` route item matching through FHIRPath `=` semantics, not raw host-language equality. Temporal values are the sharp edge: `@2012 in @2012`, `@T10:30:31.0 in @T10:30:31`, and timezone-equivalent DateTimes must be true in both native C++ and forced Python fallback, matching `|`/`union()` de-duplication. Regression coverage lives in `test_collection_operator_parity.py`.
- **DuckDB `fhirpath_is_valid` parity (review-15, 2026-05-17):** **FIXED:** `fhirpath_is_valid()` is an expression-validity check, not a non-empty-result check. Native C++ and forced Python fallback must both return `true` for valid expressions that evaluate to empty because operands are incompatible (`'10' > 2`, `'x' + 1`, `true < 1`) while still returning `false` for unresolved type specifiers, wrong type-function arity, and malformed temporal literals. Keep `test_comparison_parity.py::test_valid_empty_result_expressions_keep_is_valid_parity` as the guardrail.
- **FHIRPath §6.3 EXPLORER parity sweep (FP-15 EXPLORER, 2026-05-17):** **VERIFIED CLEAN:** Fresh native C++ vs forced Python fallback probes covered operator/function forms, resource and complex supertypes, FHIR primitive exact `as()` behavior, backtick-qualified type names, `System.Patient` non-match behavior, unresolved type specifiers, wrong arity, empty input, and multi-item singleton resilience. No new issues found; keep `test_type_parity.py` and `test_conformance_regressions.py` as the focused guardrails.
- **FHIRPath §6.3 qualified type specifier namespaces (FP-15 HISTORIAN, 2026-05-17):** **FIXED:** `FHIR.Boolean`, `FHIR.Integer`, `FHIR.String`, `FHIR.Decimal`, `FHIR.Date`, `FHIR.DateTime`, and `FHIR.Time` are invalid FHIR-model type aliases and must make `is`/`as` surfaces return empty/NULL with `fhirpath_is_valid=false`. Preserve official R4 behavior for `System.Patient`: it is treated as a resolvable type specifier that does not match a FHIR Patient, so `Patient.is(System.Patient).not()` returns true. Native and forced Python fallback parity coverage lives in `test_type_parity.py`; rebuild and copy the bundled extension after native type-specifier changes.
- **FHIRPath §6.3 type operators (FP-15 SKEPTIC, 2026-05-17):** **FIXED:** `is`/`as` validate type specifiers instead of treating unknown or missing types as false/empty. `is` signals singleton errors in strict/core evaluation, while public DuckDB wrappers convert those errors to empty/NULL for row resilience. `as` follows the §6.3 "type or subclass" rule for FHIR resources and complex datatypes; preserve R4 primitive conformance where FHIR primitive casts such as `Patient.gender.as(string)` remain empty while `Patient.gender.as(code)` succeeds. Regression coverage lives in `test_conformance_regressions.py` and `test_type_parity.py`.
- **Comparison string typing (FP-14 SKEPTIC, 2026-05-17):** Python fallback comparison must not coerce numeric-looking `String` operands into numbers. FHIRPath conversion table makes `String -> Integer/Decimal` explicit only; `Integer -> Decimal` is the relevant implicit numeric conversion. The fix is metadata-aware: XML-derived FHIR numeric primitives may be converted only when the original `ResourceNode.get_type_info()` identifies a numeric FHIR primitive (`decimal`, `integer`, `unsignedInt`, `positiveInt`, `integer64`). Plain string literals and arbitrary JSON string fields remain strings. Keep native C++ and forced Python DuckDB fallback parity for cases such as `'10' < '2'` and `'10' > 2`.
- **Native Quantity path comparison (FP-14 HISTORIAN, 2026-05-17):** Native C++ comparison must materialize FHIR JSON `Quantity` path values into `FPValue::Quantity` before applying `<`, `>`, `<=`, or `>=`. **FIXED:** `isQuantityLike()` now recognizes FHIR `Quantity`/subtype metadata and structural Quantity objects before comparison, covering path-to-path expressions such as `Observation.value > Observation.component.value`. Keep native and forced Python fallback parity coverage in `test_comparison_parity.py`.
- **FHIR Quantity `unit` fallback in comparison (FP-14 EXPLORER, 2026-05-17):** **FIXED:** Python fallback Quantity parsing recognizes structural FHIR Quantity objects with `value` plus either `code` or `unit`, matching the native `isQuantityLike()` path. Display-unit-only objects such as `{"value":4,"unit":"m"}` no longer become plain dicts during `<`, `>`, `<=`, or `>=` evaluation. Keep forced fallback parity with native for path-to-path comparisons.

## NOT A BUG Registry

- **FHIRPath FP-09 HISTORIAN iter 1 §5.6.1-§5.6.5 string search
  spec-walkthrough (2026-06-28):** **VERIFIED CLEAN:** A 68-case
  systematic HISTORIAN spec-walkthrough re-verified every normative
  rule from FHIRPath v2.0.0 §5.6.1-§5.6.5 across all five functions
  (`indexOf`, `substring`, `startsWith`, `endsWith`, `contains`) at
  the public DuckDB UDF boundary comparing bundled native C++
  extension vs forced Python fallback. The HISTORIAN pass independently
  confirms the FP-09 SKEPTIC archive below: zero native↔fallback diffs.
  The canonical trap for this surface — the empty-STRING vs empty-
  COLLECTION distinction — is correctly handled by both paths because
  `arg.empty()` (C++) and `util.is_empty(...)` (Python) check
  FHIRPath-collection emptiness, not string emptiness. The FHIRPath
  literal `''` evaluates to a 1-item collection containing an empty
  string, so it reaches the function body and produces the spec-defined
  result (`indexOf('')→0`, `startsWith('')→true`, `endsWith('')→true`,
  `contains('')→true`). Probe artifact:
  `/mnt/d/fhir4ds/.temp/qa/fp09_historian_2026_06_28/probe.py`. Full
  conformance 2822/2822 unchanged.

- **FHIRPath FP-09 SKEPTIC §5.6.1-§5.6.5 string search parity (2026-06-28):**
  **VERIFIED CLEAN:** SKEPTIC predict-then-probe pass over §5.6 String
  Manipulation search functions (`indexOf(substring)`,
  `substring(start, [length])`, `startsWith(prefix)`,
  `endsWith(suffix)`, `contains(substring)`) covered 60+ expressions
  across 4 rounds comparing bundled native C++ extension vs forced
  Python fallback at the public DuckDB UDF boundary. All 8 SKEPTIC-
  predicted bugs (H1-H8) were empirically REJECTED:
  - Empty input propagation: both paths return `[]` (orchestrator
    catches legacy `ensure_string_singleton` errors and converts).
  - Empty-string argument: `'abc'.indexOf('')` → `0`,
    `'abc'.startsWith('')` → `true`, `'abc'.endsWith('')` → `true`,
    `'abc'.contains('')` → `true` — matches spec §5.6.1/3/4/5.
  - Empty-collection argument: `'abc'.indexOf({})` → `[]`,
    `'abc'.substring(0, {})` → `'abc'` (treated as no length per
    §5.6.2), `'abc'.startsWith({})` → `[]`.
  - substring boundary: `'abc'.substring(3)` → `[]`,
    `'abc'.substring(2, 100)` → `'c'`, `'abc'.substring(1, -1)` → `''`
    (empty string, not collection — C++ implementation choice).
  - Unicode code-point positions: `'café'.indexOf('é')` → `3`;
    `'a😀b'.indexOf('😀')` → `1` (4-byte UTF-8 handled by native
    `utf8ByteToChar`/`utf8CharToByte` helpers).
  - Multi-element input/argument: errors caught upstream, return `[]`
    (row-resilience policy, same as FP-03 EXPLORER finding).
  - Sourced calls (e.g., `s.indexOf(term)`): argument resolves in
    outer focus correctly in both paths.
  - Case sensitivity: `'café'.indexOf('É')` → `-1`,
    `'café'.contains('CAF')` → `false` (no case folding).
  Pre-existing parity test
  `fhir4ds/fhirpath/duckdb/tests/integration/test_string_search_parity.py`
  provides regression coverage including arity/type validation and
  union-argument validation. Full conformance held at 2822/2822.
  Evidence lives in
  `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp09_reproducer*.py`.

- **FHIRPath FP-05 SKEPTIC §5.3/§5.4 subsetting/combining parity (2026-06-28):**
  **VERIFIED CLEAN:** SKEPTIC predict-then-probe pass over §5.3 Subsetting
  (`[index]`, `single()`, `first()`, `last()`, `tail()`, `skip(num)`,
  `take(num)`, `intersect(other)`, `exclude(other)`) and §5.4 Combining
  (`union(other)` / `|`, `combine(other)`, 2-arg `combine(other,
  preserveOrder)` extension) covered 76 expressions across both native
  DuckDB/C++ and forced Python fallback paths. All 8 predicted bug
  hypotheses (H1-H8) empirically REJECTED:
  - `[index]` correctly accepts Integer/Long, rejects Boolean/Decimal/String
    via native `extractStrictInteger` (evaluator.cpp:2476) and fallback
    `indexer_expression` type guard (evaluators/__init__.py:589-591).
  - `single()` on multi-element input logs "scalar evaluation error" in
    both paths and returns `[]` (row-resilience, same policy as FP-03
    EXPLORER finding above); strict-mode raising is symmetric.
  - `skip(num<=0)` returns input, `take(num<=0)` returns `[]`, both paths
    agree across negative/zero/INT_MIN/INT_MAX/LONG_MAX boundaries.
  - `intersect`/`union` dedup; `exclude`/`combine` do not; order
    preservation verified on resource-backed paths (`Patient.name`,
    `Patient.identifier` with duplicates).
  - 2-arg `combine(other, preserveOrder=true/false)` extension matches
    across both paths; non-normative 2-arg form returns empty in both
    paths when second arg evaluates to empty collection (consistent
    extension behavior, not a spec violation).
  - ResourceNode unwrapping in set operations is correct in both paths;
    `fpValuesEqual` (native) and `equality()` (fallback) agree on
    complex-resource, primitive, and Quantity equality.
  Full conformance held at 2822/2822. Evidence lives in
  `.temp/qa/fp05_skeptic/probe.py` and `.temp/qa/fp05_skeptic/deep_probe.py`.

- **FHIRPath FP-03 EXPLORER non-Boolean/arity inputs to §5.1 existence functions return empty `[]` (2026-06-28):**
  **VERIFIED INTENDED:** EXPLORER fuzz pass on §5.1 existence functions
  surfaced 11 pathological inputs (non-Boolean inputs to `allTrue()` /
  `anyTrue()` / `allFalse()` / `anyFalse()`, arity violations on `all()` /
  `exists()` / `subsetOf()` / `supersetOf()`, non-Boolean criteria in
  `all()`) that return `[]` instead of raising. Verified this is the
  documented row-resilience policy:
  - `extensions/fhirpath/src/fhirpath_extension.cpp:865-868` catches
    `fhirpath::FHIRPathSpecError` and returns `{}` with the comment
    "Resilience: per user mandate, row-level spec violations return empty,
    not crash."
  - `fhir4ds/fhirpath/duckdb/udf.py:1961-1989` mirrors the policy and
    adds `FHIRPATH_STRICT_MODE=1` opt-in for callers requiring raising.
  - `fhirpath_is_valid()` correctly distinguishes:
    statically-detectable arity violations (returns `False`) from runtime
    type violations (returns `True`, parser cannot know runtime types).
  - Both native and fallback paths agree exactly (zero divergence) on all
    11 cases. Native C++ does not currently expose a strict-mode toggle
    (feature gap, not a bug).
  Large-collection stress (10K/50K/100K elements through `count()` /
  `distinct()` / `isDistinct()`) produced full native/fallback parity at
  every size with no crashes; native is ~30x faster on `distinct()` /
  `isDistinct()` at 100K. Guard with `.temp/qa/fp03_explorer_probe.py`,
  `.temp/qa/fp03_explorer_focused_probe.py`, and
  `.temp/qa/fp03_explorer_validity.py`.

- **FHIRPath FP-12 HISTORIAN fresh rerun (2026-06-12):**
  **VERIFIED CLEAN:** Fresh §5.8/§5.9 probing against the current source tree
  matched bundled native DuckDB/C++ and forced Python fallback behavior for
  `children()`, `descendants()`, `trace(name, [projection])`, `now()`,
  `timeOfDay()`, and `today()`. The rerun independently covered the
  2026-06-12 trace projection fix: optional projection is evaluated once per
  input item with `$this`/`$index`, but `trace()` still returns the original
  input and restores surrounding scope. Preserve parity for split primitive
  extension hiding in tree navigation, `descendants() = repeat(children())`
  de-duplication, deep traversal, invalid utility signatures, and same-expression
  determinism of current-time helpers. Evidence lives in
  `.temp/qa/fp12_historian_fresh_probe.py` and
  `test_tree_utility_parity.py`.

- **FHIRPath Section 5.6.1-5.6.5 HISTORIAN fresh rerun (FP-09, 2026-06-12):**
  **VERIFIED CLEAN:** Fresh 66-expression probing matched bundled native
  DuckDB/C++ and forced Python fallback behavior for `indexOf(substring)`,
  `substring(start[, length])`, `startsWith(prefix)`, `endsWith(suffix)`, and
  string-function `contains(substring)`. Preserve current behavior for empty
  String search terms, empty input/argument collections, Unicode scalar-value
  indexing over emoji and combining marks, dynamic sibling-field argument focus
  inside and outside `select()`, runtime row-resilient type/cardinality errors,
  and the string `.contains()` versus collection `contains` operator split.
  Guard with `.temp/qa/fp09_historian_fresh_probe.py` and
  `test_string_search_parity.py`.
- **FHIRPath Section 5.6.1-5.6.5 SKEPTIC fresh rerun (FP-09, 2026-06-12):**
  **VERIFIED CLEAN:** A fresh native DuckDB/C++ vs forced Python fallback
  probe covered string search functions `indexOf(substring)`,
  `substring(start[, length])`, `startsWith(prefix)`, `endsWith(suffix)`, and
  string-function `contains(substring)`. Preserve the distinction between
  expression validity and runtime evaluation: dynamic resource-backed
  non-String/non-Integer arguments such as `s.indexOf(badTerm)` return
  row-resilient empty/NULL outputs but keep `fhirpath_is_valid()` true, while
  statically invalid calls such as `s.substring(1.5)` remain invalid. Keep
  Unicode scalar-value indexing and function/operator `contains`
  disambiguation guarded by `.temp/qa/fp09_skeptic_fresh_probe.py` and
  `test_string_search_parity.py`.
- **FHIRPath Section 5.1 HISTORIAN fresh rerun (FP-03, 2026-06-11):**
  **VERIFIED CLEAN:** A fresh 36-expression matrix found no additional
  defects after the FP-03 SKEPTIC scoped `subsetOf()`/`supersetOf()` fix.
  Native DuckDB, forced Python fallback, and direct Python wrappers matched
  for `empty()`, `exists([criteria])`, `all(criteria)`, `allTrue()`,
  `anyTrue()`, `allFalse()`, `anyFalse()`, `subsetOf()`, `supersetOf()`,
  `count()`, `distinct()`, and `isDistinct()`. Preserve coverage for vacuous
  empty defaults, strict Boolean criteria, full Boolean aggregate validation,
  scoped set-comparison arguments, structural JSON equality, compatible
  Quantity equality, and public wrapper row resilience. Evidence lives in
  `.temp/qa/fp03_historian_fresh_probe.py` and
  `test_existence_parity.py`.
- **Release 0.0.8 Domain 2 ARCHAEOLOGIST rerun (2026-06-07):**
  **VERIFIED CLEAN:** Fresh native C++ vs forced Python fallback probes found no
  defects across lazy `iif()` branch evaluation, `$index` scoping inside
  `repeat(iif(...))`, `trace()` identity with valid projection, self-cycle
  `repeat($this)` de-duplication, union duplicate elimination versus
  `combine()` duplicate preservation, and strict equality versus
  whitespace/case-normalizing string equivalence. Evidence lives in
  `.temp/qa/domain2_archaeologist_probe.py`; targeted parity pytest passed 5/5
  and FHIRPath R4 conformance stayed 935/935.
- **FHIRPath Section 7/8 HISTORIAN rerun (FP-19, 2026-05-24):**
  **VERIFIED CLEAN:** A fresh 31-case native C++ vs forced Python fallback
  probe plus 7 direct core checks found no additional aggregate or lexical
  issues after the FP-19 SKEPTIC fixes. Preserve coverage for aggregate init
  outer focus, empty-source init, `$total`/`$index` restoration, comments
  outside strings/identifiers, comment delimiters inside strings and delimited
  identifiers, strict whitespace (space/tab/LF/CR only), NBSP/form-feed/
  vertical-tab rejection outside comments, identifier keyword exceptions
  (`as`, `contains`, `in`, `is`), reserved keywords/duration units requiring
  delimiters, case-sensitive keywords, invalid numeric literal syntax, and
  no-whitespace calendar quantities.
- **FHIRPath Section 5.5.4-5.5.6 EXPLORER rerun (FP-07, 2026-05-24):**
  **VERIFIED CLEAN:** A fresh 46-case pathological native C++ vs forced Python
  fallback probe matched for Date, DateTime, and Decimal conversion behavior
  across invalid calendar/timezone ranges, partial precision, strict decimal
  grammar, empty and resource-backed multi-item row resilience, invalid arity,
  lazy `iif()` branches, `select()` chains, and explicit root-filter chains.
  Resource-backed cardinality errors are data-dependent: public result UDFs
  return empty/NULL while `fhirpath_is_valid()` can remain true.
- **FHIRPath Section 5.5.4-5.5.6 HISTORIAN rerun (FP-07, 2026-05-24):**
  **VERIFIED CLEAN:** A fresh 56-case probe matched native C++ and forced
  Python fallback public DuckDB behavior for `toDate()`, `convertsToDate()`,
  `toDateTime()`, `convertsToDateTime()`, `toDecimal()`, and
  `convertsToDecimal()`. Preserve coverage for strict decimal grammar,
  valid/invalid calendar ranges, timezone-offset shape/range checks, partial
  DateTime precision, empty propagation, multi-item singleton row resilience,
  invalid arity, and resource-backed string values.
- **FHIRPath Section 5.3/5.4 HISTORIAN rerun (FP-05, 2026-05-24):**
  **VERIFIED CLEAN:** A fresh 53-case probe matched native C++ and forced
  Python fallback public DuckDB outputs for every requested subsetting and
  combining surface: `[index]`, `single()`, `first()`, `last()`, `tail()`,
  `skip(num)`, `take(num)`, `intersect(other)`, `exclude(other)`,
  `union(other)`/`|`, and `combine(other)`. Preserve coverage for strict
  Integer index/count arguments, malformed arity invalidation, row-resilient
  multi-item `single()`, duplicate-preserving `exclude()`/`combine()`, and
  equality-backed `union()`/`intersect()` across native and forced fallback
  registrations.
- **FHIRPath Section 5.1 HISTORIAN rerun (FP-03, 2026-05-24):**
  **VERIFIED CLEAN:** A fresh section-by-section probe covered all mandatory
  existence functions across 52 native C++ and forced Python fallback cases:
  `empty()`, `exists([criteria])`, `all(criteria)`, Boolean aggregates,
  `subsetOf()`, `supersetOf()`, `count()`, `distinct()`, and `isDistinct()`.
  Native and fallback outputs matched, including empty/default truth values,
  `$index` criteria binding, row-resilient invalid criteria, full Boolean
  aggregate validation, structural JSON equality, numeric equality, and
  compatible Quantity equality. Keep `test_existence_parity.py` plus fresh
  ad hoc parity probes as guardrails for future section 5.1 changes.
- **FHIRPath Section 5.1 SKEPTIC rerun (FP-03, 2026-05-24):**
  **VERIFIED CLEAN:** Fresh native C++ vs forced Python fallback probes over
  existence functions found no parity or spec issues across 35 targeted cases.
  Keep coverage for `$index` inside `exists(criteria)`/`all(criteria)`, scope
  restoration after early returns, strict Boolean criteria, full-collection
  Boolean aggregate validation, empty/default results, FHIR Quantity path
  equality, structural JSON equality, and numeric `1` vs `1.0` equality in
  `test_existence_parity.py`.
- **FHIRPath §4.2-§4.5 HISTORIAN rerun (FP-02, 2026-05-24):**
  **VERIFIED CLEAN:** A fresh section-by-section pass over operator syntax,
  function invocation, null/empty propagation, and singleton evaluation found
  no native C++ vs forced Python fallback mismatches across 24 public DuckDB
  cases. Keep probes isolated by subprocess and force the workspace root onto
  `sys.path`; otherwise local scripts can accidentally import an installed
  package with a stale bundled extension.
- **Release 0.0.6 Domain 1 null/singleton wrapper behavior (2026-05-20):**
  Public DuckDB FHIRPath wrappers intentionally convert strict singleton and
  criteria-evaluation errors to empty/NULL for row resilience. A SKEPTIC sweep
  over missing paths, JSON nulls, `where()` criteria, multi-item singleton
  failures, scalar wrappers, and native-vs-forced-fallback registration found
  no parity mismatch; keep `test_existence_parity.py` and `test_type_parity.py`
  as guardrails.
