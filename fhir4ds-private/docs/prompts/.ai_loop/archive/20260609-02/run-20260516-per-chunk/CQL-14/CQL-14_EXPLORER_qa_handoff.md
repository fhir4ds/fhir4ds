# QA Handoff: CQL-14 Date/Time Operators Part 2, EXPLORER

Scope honored: QA only. I did not inspect or rely on archived `.ai_loop/spec_comp/**` output and did not modify implementation source. The requested `.ai_loop/AGENTS.md` file was not present; repository `AGENTS.md`, `extensions/cql/AGENTS.md`, workflow state/schema/procedure files, and relevant CQL source/tests were read.

## Spec Anchors

- CQL v1.5.3 Appendix B, Date and Time Operators: `Now()` returns the evaluation request start timestamp and is stable within an evaluation; `Today()` and `TimeOfDay()` derive from that same start timestamp.
- CQL v1.5.3 Appendix B, Same As/Same Or Before/Same Or After/On Or Before/On Or After: precision comparison proceeds from broad to requested precision, returns null when the requested precision is not present, and week precision is not supported.
- CQL v1.5.3 Appendix B, Subtract: `Date`/`DateTime`/`Time - Quantity` decrements by a time-valued Quantity; if either argument is null, result is null. Logical Specification Date and Time Operators also states date/time operations with null arguments return null unless specifically noted.
- CQL v1.5.3 Appendix B, Time: `Time(hour[, minute[, second[, millisecond]]])` constructs a time value, with no component below an unspecified precision.

Primary source: https://cql.hl7.org/09-b-cqlreference.html

## Hypotheses Probed

1. Current-clock helpers might not be statement-stable or might emit non-CQL lexical forms.
2. Precision helpers might accept unsupported precision synonyms (`week`, `weeks`) or mishandle partial temporal uncertainty.
3. `on or before/after` translation might diverge from `same or before/after` semantics in scalar and query execution.
4. Dynamic `Time(...)` operands and chained time arithmetic might lose precision or fail differently between native-loaded and forced Python fallback connections.
5. `DateTime - Quantity` public helpers might mishandle fractional, negative, missing, or malformed Quantity JSON differently between Python fallback and no-Python C++ surfaces.

## Probes And Results

Command:

```bash
python3 .temp/qa/cql14_explorer_probe.py
```

Result summary:

```text
wrote /mnt/d/fhir4ds/.temp/qa/cql14_explorer_probe_results.json
sql_cases=60 translated_cases=20 parity_checks=28
failures=9
```

The failures collapse to one issue:

- `dateSubtractQuantity('2024-01-01', '{"unit":"day"}')`
  - forced Python: `2024-01-01`
  - native-loaded: `2024-01-01`
  - C++-only: `NULL`
  - expected: `NULL`, because missing Quantity value is not a usable time-valued Quantity and must not be treated as zero.

- `dateSubtractQuantity('2024-01-01', '{"value":null,"unit":"day"}')`
  - forced Python/native-loaded: raises `InvalidInputException` from `float(None)`
  - C++-only: `NULL`
  - expected: row-level SQL `NULL`.

- `dateSubtractQuantity('2024-01-01', '{"value":"abc","unit":"day"}')`
  - forced Python/native-loaded: raises `InvalidInputException` from `float("abc")`
  - C++-only: `NULL`
  - expected: row-level SQL `NULL`.

Translated CQL scalar/query probes all passed across forced Python and native-loaded registration:

- chained `DateTime - Quantity` plus `same day as`
- `on or before day of`
- dynamic `Time(hour from ..., minute from ..., second from ..., millisecond from ...)`
- invalid `same week as` returning `NULL`
- `Now() = Now()`, `Today() = Today()`, `TimeOfDay() = TimeOfDay()`, and `TimeOfDay() same second as TimeOfDay()`
- list query with `where D same day or after ... return D - 12 hours`

Current-clock direct helper values were validated for CQL-like shape and stability within a SQL statement. Cross-backend equality was not required because each backend was executed in a different statement/time.

Command:

```bash
python3 -m pytest fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py -q --tb=short | tee .temp/qa/cql14_pytest_datetime_wasm.log | tail -n 60
```

Result:

```text
collected 10 items
fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py ..... [ 50%]
fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py .....      [100%]
10 passed in 12.16s
```

## Issue Logged

`QA-001` in `evolution.json`: Python-backed `dateSubtractQuantity` treats missing Quantity `value` as zero and raises for null/non-numeric values; expected public SQL behavior is `NULL`, matching C++-only behavior.

## Artifacts

- `.temp/qa/cql14_explorer_probe.py`
- `.temp/qa/cql14_explorer_probe_results.json`
- `.temp/qa/cql14_pytest_datetime_wasm.log`
