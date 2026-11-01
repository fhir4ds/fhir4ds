# Engineer Handoff - FP-07 SKEPTIC

Date: 2026-06-12

## Issues

- `QA-001` MEDIUM `VERIFIED`: current FHIRPath §5.5.4/§5.5.5 optional Date/DateTime format arguments were rejected as invalid.
- `QA-002` MEDIUM `VERIFIED`: current FHIRPath §4.1 STU Long literals did not reach §5.5.6 Decimal conversion.
- `ARCH-001` MEDIUM `VERIFIED`: forced Python fallback still applied Integer int32 bounds to valid Long literals above the Integer range.

Open CRITICAL/HIGH/MEDIUM issues: 0.

## Fixes

- Added optional `String` format arguments for `toDate()`, `convertsToDate()`,
  `toDateTime()`, and `convertsToDateTime()` in the Python invocation registry
  and native dispatcher.
- Added token-based parsing for required current Date/DateTime format tokens:
  `yyyy`, `MM`, `dd`, `HH`, `mm`, `ss`, repeated `S`, `a`, and `Z`, plus
  common `yy` and variable-width numeric variants.
- Preserved Decimal converter zero-arity behavior.
- Added uppercase `LONGNUMBER` support in the Python grammar/generated parser
  and native C++ lexer/parser, with native Long literals evaluating through a
  distinct AST node.
- Updated the fallback Integer range precheck to skip valid uppercase Long
  suffixes before applying int32 bounds.
- Added targeted fallback row-resilience for malformed Long-like suffixes such
  as `2147483648LL`, `1.0L`, and `1l`.
- Rebuilt and copied the bundled native extension after native lexer/parser and
  evaluator changes; build/package/repository extension hashes matched.

## Key Files Changed

- `fhir4ds/fhirpath/engine/invocations/__init__.py`
- `fhir4ds/fhirpath/engine/invocations/misc.py`
- `fhir4ds/fhirpath/engine/evaluators/__init__.py`
- `fhir4ds/fhirpath/duckdb/evaluator.py`
- `fhir4ds/fhirpath/duckdb/udf.py`
- `fhir4ds/fhirpath/parser/FHIRPath.g4`
- `fhir4ds/fhirpath/parser/generated/*`
- `extensions/fhirpath/src/fhirpath/lexer.*`
- `extensions/fhirpath/src/fhirpath/parser.cpp`
- `extensions/fhirpath/src/fhirpath/ast.hpp`
- `extensions/fhirpath/src/fhirpath/evaluator.*`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp07_skeptic_fresh_probe.py`

## Validation

```bash
python3 .temp/qa/fp07_skeptic_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_conversion_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py fhir4ds/fhirpath/tests/unit/test_parser_errors.py fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q
./build/release/test/unittest "*fhirpath*"
git diff --check -- fhir4ds/fhirpath extensions/fhirpath fhir4ds-private/docs/prompts/.ai_loop .temp/qa/fp07_skeptic_fresh_probe.py .temp/architect/golden_standard.md
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:
- Fresh FP-07 probe passed, 14 expressions.
- Conversion parity passed, 20/20.
- Adjacent literal/parser tests passed, 43/43.
- Native FHIRPath unittest passed, 770 assertions.
- Diff check passed.
- Full conformance passed: ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Notes

- The implementation supports the required current format tokens and common
  numeric variants; localized month names and time zone names remain unsupported
  optional format codes.
- Native Decimal values still use the existing native decimal representation.
  Coverage now includes the spec example `42L` and a valid Long above the old
  Integer range, `2147483648L`.
