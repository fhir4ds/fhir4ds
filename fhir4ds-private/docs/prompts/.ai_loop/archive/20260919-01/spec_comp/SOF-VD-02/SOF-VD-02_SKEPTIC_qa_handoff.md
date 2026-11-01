# QA Handoff — SOF-VD-02 (SKEPTIC), iteration 1

## Probed
~90 probes in `.temp/qa/sofvd02_skeptic_2026_08/probe{1..6}.py`, PYTHONPATH=repo:

1. **Parser validation (probe1)**: constant.name sql-name (empty/null/missing/underscore-start/digit-start/dash rejected; mid-underscore OK); value[x] exactly-one (zero/two/null/unsupported valueCoding rejected); per-type formats across all 19 primitives (uuid, oid, positiveInt 0, unsignedInt −1, integer-as-string, integer64 non-string/leading-zero, instant no-tz, boolean-as-string, decimal-as-string, url space, empty string, code trailing space, time 24:00, 3-digit year, base64Binary); duplicates; plural `constants` rejected with explicit singular-field message; non-array/non-object shapes. All correct.
2. **Substitution semantics (probe2/4)**: %name in column.path, column.where, select.where (root), forEach, forEachOrNull, nested select.where, unionAll — all execute correctly in DuckDB (native extension). Lexical guards: refs inside string literals, backtick identifiers, // and /* */ comments NOT substituted; longest-match; undefined %ref → explicit ValidationError at generate; duplicate/undefined at parse+validate. Builtins (%resource, %rowIndex) not shadowable (reserved vars win — previously pinned INTENDED). Decimal exactness (0.1+0.2=0.3 → true); int/bool/date/dateTime/instant/uuid substitution typing correct; string constants with embedded quotes/backslashes escape correctly end-to-end.
3. **Official fixtures end-to-end (probe5)**: executed every test in `constant_types.json` (14 types) and `constant.json` (8 tests incl. undefined-constant and incorrect-definition error tests) against fixture resources in DuckDB — all match `expect` rows exactly. NOTE: the committed `test_spec_compliance.py` only asserts parsing of these fixtures, never executes them; the execution parity lives only in my probe (candidate follow-up: promote to committed integration tests).
4. **Engine ground truth (probe4)**: temporal constants substituted as quoted strings behave identically to native @-literals in this engine (equality, precision-uncertain comparisons); `.hour` on time constants is empty because the engine lacks time-literal `.hour` natively too — engine gap, out of chunk.

## Found
- **QA-001 (MEDIUM, OPEN)**: valueInteger64 constants outside int32 range substitute to bare integer literals both engines silently evaluate to empty — no explicit error; wrong (empty) results. Evidence in evolution.json.

## Verified against
SQL-on-FHIR v2 IG StructureDefinition-ViewDefinition.html (fetched live): constant 0..* singular, name/%name, "placeholders are replaced by the value of the constant before the FHIRPath expression is evaluated"; FHIRPath spec Integer 32-bit signed range.
