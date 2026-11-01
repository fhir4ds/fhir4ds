# QA Handoff - FP-14 SKEPTIC

## Scope

Fresh run for FHIRPath §6.2 Comparison:
`>`, `<`, `<=`, `>=` over native DuckDB/C++ and forced Python fallback paths.

Spec source consulted: HL7 FHIRPath continuous-build source, §6.2 Comparison.
The section defines comparison for strings, integers, longs, decimals,
quantities, dates, datetimes, and times. Empty operands return empty,
multi-item operands are singleton errors, operands must be same-type or
implicitly convertible, non-comparable Quantity/temporal comparisons return
empty, and `Long` is explicitly included among comparable numeric types.

## SKEPTIC Hypotheses

1. Native numeric comparison may still order via binary `double`, losing Long
   and large Decimal distinctions above 2^53.
2. Native resource-backed JSON numeric paths may have the same exact-ordering
   loss because JSON numbers feed `getNumericValue()`.
3. Quantity comparison may lose exact ordering for large same-unit values
   because native Quantity values are stored and converted as `double`.
4. Existing temporal precision rules could drift between native and fallback
   for partial Date/Time and second/millisecond precision.
5. Empty, multi-item, Boolean, and String-vs-number cases must remain
   row-resilient and parity-tested.

## Probe

Created fresh probe:

```bash
python3 .temp/qa/fp14_skeptic_fresh_probe.py
```

Result: failed with one issue family. Existing comparison parity baseline still
passes:

```bash
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_comparison_parity.py -q
```

Result: `10 passed`.

## Findings

### QA-001 - MEDIUM - SPEC_VIOLATION - OPEN

Native/C++ comparison loses exact ordering for large numeric and Quantity
operands, while forced Python fallback returns the expected §6.2 results.

Representative failures from the fresh probe:

```text
9223372036854775806L < 9223372036854775807L
  native:   (['false'], '[false]', False, True)
  fallback: (['true'], '[true]', True, True)

9223372036854775807L <= 9223372036854775806L
  native:   (['true'], '[true]', True, True)
  fallback: (['false'], '[false]', False, True)

9007199254740992.0 < 9007199254740993.0
  native:   (['false'], '[false]', False, True)
  fallback: (['true'], '[true]', True, True)

bigA < bigB
  native:   (['false'], '[false]', False, True)
  fallback: (['true'], '[true]', True, True)

9007199254740992 'mg' < 9007199254740993 'mg'
  native:   (['false'], '[false]', False, True)
  fallback: (['true'], '[true]', True, True)

valueQuantity < component.valueQuantity
  native:   (['false'], '[false]', False, True)
  fallback: (['true'], '[true]', True, True)
```

Likely root cause: `extensions/fhirpath/src/fhirpath/evaluator.cpp` comparison
routes numeric and Quantity values through `double` (`getNumericValue()`,
`quantity_value`, `convertQuantityToBase()`), collapsing adjacent values above
binary64 precision. Fix should preserve exact authored/JSON numeric text for
same-unit and numeric comparisons where possible, then keep existing UCUM
conversion behavior for ordinary unit conversions.
