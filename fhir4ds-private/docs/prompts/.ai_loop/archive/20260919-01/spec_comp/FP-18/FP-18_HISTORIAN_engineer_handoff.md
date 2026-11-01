# Engineer Handoff — FP-18 HISTORIAN iteration 1 (2026-08-18)

## Triage outcome (6 issues)
| ID | Severity | Status | Action |
|---|---|---|---|
| QA-001 | MEDIUM | DEFERRED | Native Quantity unit-space composition port (see below) |
| QA-002 | MEDIUM | RESOLVED | Native Time ± result rendering (T prefix removed) |
| QA-003 | MEDIUM | INTENDED | Integer overflow → Decimal is documented cross-engine doctrine |
| QA-004 | MEDIUM | INTENDED | Official fixtures pin UCUM 'd'/'wk'/'h'/'min' as VALID §6.7 units |
| QA-005 | MEDIUM | INTENDED | Fixtures pin fractional-quantity truncation (testPlusDate19 no-op) |
| QA-006 | LOW | RESOLVED | `-2147483648` (INT32_MIN) literal accepted |

## Fixes

### QA-002 — native §6.7 Time arithmetic result rendering
- Root cause: `fn_dateArith` (extensions/fhirpath/src/fhirpath/evaluator.cpp,
  Time branch) stored `result.string_val = "T" + hh:mm:ss`, while every other
  native Time path (TimeLiteral via `normalizeTimeLiteralString`, JSON-field
  detection, `parseTimeParts` consumers) stores the bare form. §5.5.8 Time
  toString format is `hh:mm:ss.fff` (no T); both engines render Time literals
  without T, so native arithmetic results were self-inconsistent and broke
  parity with the fallback.
- Fix: `result.string_val = buf;` (T prefix removed). Extension rebuilt
  (`make release`) and redeployed to the repo bundle
  (`fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`) and the
  user site-packages copy.

### QA-006 — Integer minimum literal
- Root cause: `number_literal` range check fired on the unsigned literal
  `2147483648` before unary negation, but §4.1.3 defines the minus sign as
  the unary negation operator, so `-2147483648` is the valid Integer minimum
  (native accepts it).
- Fix: `polarity_expression` (fhir4ds/fhirpath/engine/evaluators/__init__.py)
  special-cases unary minus over the exact 2^31 NumberLiteral (walking
  TermExpression/LiteralTerm wrapper nodes), returning -2147483648 — mirrors
  the existing `-9223372036854775808L` Long-literal convention. Bare
  `2147483648` and `-2147483649` still raise "Integer literal out of range".
- Side effect: `-2147483648 - 1` now yields Decimal('-2147483649') on the
  fallback, restoring parity with native's Decimal degradation (QA-003
  doctrine).

### QA-001 — DEFERRED (documented, not shimmable)
Native Quantity `+`/`-`/`*`//` composes in SI base units; spec examples and
the Python fallback compose in operand-unit space with most-granular-unit
results. Fixing requires porting the Python UCUM term-exponent algebra
(`_parse_unit_exponents`/`_render_unit_exponents`, derived-base expansion,
FP-02 HISTORIAN most-granular-unit selection — nodes.py) into evaluator.cpp:
net-new native functionality (~300 lines), not a surgical fix. Values are
semantically equal; no official fixture pins the rendered unit (testQuantity9
compares via base-reduced equality). Flagged for a dedicated native-UCUM
reconciliation chunk in AGENTS.md.

## QA-003/QA-004/QA-005 reclassifications (fixture/doctrine-driven)
- QA-004: `tests-fhir-r4.xml` testPlusDate13/15/18-22 pin `1 'd'`, `1 'wk'`,
  `1 's'`, `10 'ms'`, `1 'min'`, `1 'h'` as VALID §6.7 operands; only
  `'mo'`/`'a'` are execution-invalid (testPlusDate14/16). Fixtures outrank
  §6.7 prose per GLOBAL_RULES.
- QA-005: testPlusDate19 pins `+ 0.1 's'` on a ms-precision DateTime as a
  no-op; testPlusDate2 pins `+ 7.7 days` truncation. Current truncation is
  fixture-correct.
- QA-003: Integer overflow → exact Decimal degradation is documented
  cross-engine doctrine (`_numeric_arithmetic_result`; FP-11 power()
  doctrine comment). Both engines identical.
All three logged in the AGENTS.md NOT A BUG registry.

## Regression tests
`fhir4ds/fhirpath/tests/unit/test_fp18_math_operators.py`: new classes
`TestFP18Historian2026_08_18` (INT32_MIN pins, Decimal-degradation pins,
range enforcement, Time-without-T rendering) and
`TestDualEngineParityHistorianFP18` (native/fallback Time ± parity, auto-skip
without the built extension). File now 66 passed.

## Validation
- test_fp18_math_operators.py: 66/66 passed.
- Full fhirpath tree: 1829 passed / 172 failed — ALL failures are the known
  pre-existing source/binary/test drift family (prior launch QA-007: FP-01/
  FP-11-era parity tests, verified then against the PRE-LAUNCH binary;
  count actually improved from 183 to 172). No new failures introduced.
- Conformance master gate (conformance/scripts/run_all.py):
  ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47 —
  OVERALL 2832/2832. No regression.
