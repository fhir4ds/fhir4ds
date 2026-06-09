# fhir4ds.fhirpath Notes

## Known Fragile Areas

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
  `1.abs(2)`, `10.log()`, `2.power(3, 4)`, and `2.sqrt(1)`; incompatible
  constants such as `'2.5'.sqrt()`, `true.abs()`, and `5 'mg'.ceiling()` must
  make `fhirpath_is_valid=false` while public result UDFs remain row-resilient.
  Sourced `p.log(base)` evaluates `base` in the outer resource focus, and
  integer `2.power(3)` materializes as Integer (`8`), not Decimal (`8.0`).
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
- **FHIRPath §6.5 Boolean truth tables and precedence (FP-17 HISTORIAN, 2026-05-17):** **VERIFIED CLEAN:** Native C++ and forced Python fallback public DuckDB UDFs agree on the full `and`/`or`/`xor`/`implies`/`not()` three-valued truth tables, singleton non-Boolean truthiness, `and` binding tighter than `or`/`xor`, left-associative `or`/`xor` and `implies`, multi-item operand row resilience, and the intentional `false implies <expr>` short-circuit. Regression coverage lives in `test_boolean_logic_parity.py`.
- **FHIRPath §6.5 multi-item Boolean operands (FP-17 SKEPTIC, 2026-05-17):** **FIXED:** Boolean operators must run singleton Boolean evaluation before applying three-valued truth tables. A multi-item operand is a semantic error that public DuckDB UDFs convert to empty/NULL; it must not be treated like empty just because another operand determines the truth-table result. Regression cases: `arr or true`, `arr and false`, and `arr implies true` where `arr` has multiple items. The spec-permitted `false implies <expr>` short-circuit remains intentional.
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
