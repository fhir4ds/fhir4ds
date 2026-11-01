# QA Handoff: CQL-14 HISTORIAN

## Scope

Executed only the QA ENGINEER phase for CQL-14, Date/Time Operators Part 2. I did not inspect archived workflow output under `fhir4ds-private/docs/prompts/.ai_loop/spec_comp/**` and did not modify implementation source code.

Active workflow state:
- `phase`: `QA`
- `iteration`: `1`
- `qa_personality`: `HISTORIAN`
- Focus items: `Now()`, `Today()`, `TimeOfDay()`, `Time(hour, minute, second, millisecond)`, `Same As` precision, `Same Or Before/After` precision, `On Or Before/After` precision, and `DateTime minus Quantity`.

## Spec Anchors

Verified against the official CQL Reference v1.5.3:
- DateTime constructors require Integer components and no component may be specified below an unspecified precision.
- `Same As`, `Same Or Before`, and `Same Or After` compare Date/DateTime/Time values precision-by-precision; imprecision can yield null; invalid precision is not a valid comparison precision.
- `On Or Before` and `On Or After` for intervals are synonyms for `Same Or Before` and `Same Or After`.
- `Time(hour, minute, second, millisecond)` constructs a Time; at least one component is required, and components below an unspecified component are invalid.
- `TimeOfDay()` and `Today()` are derived from the evaluation request start timestamp.
- Date/Time `Subtract` with time-valued quantities ignores fractional components in the quantity; null operands produce null.

Primary source: https://cql.hl7.org/09-b-cqlreference.html

## Hypotheses

1. Current-clock functions may produce backend-specific string shapes that break component extraction or same-precision comparison.
2. Precision comparisons may mishandle partial Date/DateTime uncertainty, timezone normalization, or invalid precision strings.
3. `on or before` / `on or after` synonyms may lower differently than `same or before` / `same or after`, especially for interval operands.
4. `Time(...)` may accept static non-Integer components, runtime out-of-range components, or null gaps.
5. `DateTime - Quantity` may diverge across native-loaded DuckDB, forced Python fallback, and no-Python/browser-style C++ surfaces for fractional day/week quantities.

## Probes

Created and ran:

```bash
PYTHONPATH=/mnt/d/fhir4ds python3 .temp/qa/cql14_historian_probe.py > .temp/qa/cql14_historian_probe_results.json
```

The probe opens three isolated surfaces:
- `native`: `fhir4ds.cql.duckdb.register(...)`
- `python`: `_register_python_supplements(..., cpp_loaded=False, include_fhirpath=True)`
- `cpp_only`: direct loading of built `fhirpath.duckdb_extension` and `cql.duckdb_extension`

It tested direct helper SQL and translated CQL definitions for:
- `dateTimeNow`, `dateTimeToday`, `dateTimeTimeOfDay`
- `dateTimeSameAs`, `dateTimeSameOrBefore`, `dateTimeSameOrAfter`
- `cqlSameAsP`, `cqlSameOrBeforeP`, `cqlSameOrAfterP`
- translated `Now()`, `Today()`, `TimeOfDay()`, `Time(...)`
- translated `same`, `same or before/after`, `on or before/after`
- translated and direct `dateSubtractQuantity`

Focused existing tests:

```bash
PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest \
  fhir4ds/cql/duckdb/tests/integration/test_datetime_part2_parity.py \
  fhir4ds/cql/duckdb/tests/integration/test_wasm_cpp_surface.py \
  -q --tb=short | tail -n 80
```

Result: `10 passed in 11.83s`.

## Results

No parity issues found for:
- `Now()` / `dateTimeNow()` shape and same-statement stability
- `Today()` / `dateTimeToday()` shape and same-statement stability
- `TimeOfDay()` / `dateTimeTimeOfDay()` CQL time shape (`T%H:%M:%S`) and component extraction
- `Time(12, 30, 15, 250)`, minute precision `Time(12, 30)`, null-gap `Time(12, null, 0, 0)`, and runtime out-of-range hour
- `same month`, partial `same day` uncertainty, invalid precision returning null, and timezone-normalized `same second`
- `same or before/after` partial uncertainty and equality
- `on or before/after` point and interval synonyms
- `DateTime(2014) - 18 months`
- `@2024-01-02 - 0.5 days`
- `@2024-01-01T10:00:00 - 5 'h'`

Confirmed issue:
- `QA-001` added to `evolution.json`.
- Reproducer:

```sql
SELECT dateSubtractQuantity('2024-01-15', '{"value":1.5,"unit":"week"}');
```

Translated CQL reproducer:

```cql
define SubtractFractionalWeekFromDate: @2024-01-15 - 1.5 weeks
```

Outputs:
- no-Python/browser-style C++: `2024-01-04`
- native-loaded DuckDB registration: `2024-01-08`
- forced Python fallback registration: `2024-01-08`
- expected: `2024-01-08`

Rationale: CQL says fractional components in time-valued quantities are ignored. `1.5 weeks` should therefore subtract one week from `2024-01-15`.

Additional observation not logged as a spec issue:
- Direct Python-backed `dateSubtractQuantity('2024-01-01T10:00:00', '{"value":null,"unit":"hour"}')` raises `InvalidInputException`, while C++ returns `NULL`. This is malformed internal helper JSON rather than valid CQL source, so I left it out of `issues` but preserved the result in `.temp/qa/cql14_historian_probe_results.json`.

## State Updates

- `fhir4ds-private/docs/prompts/.ai_loop/evolution.json`: added `QA-001` as `OPEN`.
- `extensions/cql/AGENTS.md`: appended CQL-14 HISTORIAN fragile-area note for no-Python C++ fractional week subtraction.

Stopped after QA handoff as requested. No remediation or architect phase was run.
