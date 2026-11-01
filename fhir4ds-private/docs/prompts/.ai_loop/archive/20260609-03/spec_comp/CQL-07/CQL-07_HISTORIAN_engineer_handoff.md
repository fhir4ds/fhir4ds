# Engineer Handoff - CQL-07 HISTORIAN

Resolved:
- `QA-001` HIGH: conversion-check predicates now inline safe static scalar aliases the same way conversion functions do.

Root cause:
- `_translate_function_ref()` only treated `To*` functions as static conversion inputs. `ConvertsTo*`, `CanConvertQuantity`, and `ConvertQuantity` arguments were translated normally, so static Quantity/Ratio aliases could become patient/resource CTE lookups even though the original definitions were scalar and dependency-free.

Fix:
- Added `ConvertsToBoolean`, `ConvertsToDate`, `ConvertsToDateTime`, `ConvertsToDecimal`, `ConvertsToInteger`, `ConvertsToLong`, `ConvertsToQuantity`, `ConvertsToRatio`, `ConvertsToString`, `ConvertsToTime`, `CanConvertQuantity`, and `ConvertQuantity` to the static conversion-source inlining allowlist.
- Added the same function names to `_is_static_conversion_inline_candidate()` so nested safe aliases remain inlineable.
- Extended `test_conversion_check_parity.py` with static Quantity/Ratio alias coverage for `ConvertsToString`, `ConvertsToQuantity`, and `ConvertsToRatio`.
- Updated `AGENTS.md` with the new CQL-07 conversion-check alias boundary.

Validation:
- `python3 .temp/qa/cql07_historian_probe.py` passed.
- `python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_conversion_check_parity.py fhir4ds/cql/duckdb/tests/integration/test_conversion_function_parity.py -q` passed: 11 tests.
- `python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"` passed: 2822/2822 overall.

New issues:
- None.
