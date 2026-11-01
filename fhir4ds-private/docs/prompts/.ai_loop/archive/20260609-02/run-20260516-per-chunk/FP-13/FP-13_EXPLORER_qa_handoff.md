# QA Handoff - FP-13 EXPLORER

## Scope
- Chunk: FP-13, FHIRPath §6.1 Equality.
- Personality: EXPLORER.
- Surfaces probed: native C++ DuckDB extension and forced Python fallback via `register_fhirpath`.
- Official spec checked: HL7 FHIRPath Normative Release §6.1.1-§6.1.4.

## Exploration Summary
- Probed temporal cross-type equality/equivalence, timezone precision equality, quantity equality/equivalence, unordered collection equivalence, duplicate accounting, and complex recursive equivalence.
- Native and fallback agree for quantity conversion (`1 'mg' = 0.001 'g'`), second duration equality (`1 second = 1 's'`), string/complex equivalence, and duplicate-sensitive collection equivalence when tested with field arrays and `combine()`.

## Finding
- `QA-001` HIGH: native C++ treats same-precision `Date` vs `DateTime` literals as equal/equivalent.
- Reproducer:
  - `@2012 = @2012T`: native `(['true'], True, '[true]')`; forced fallback `([], None, None)`.
  - `@2012 ~ @2012T`: native `(['true'], True, '[true]')`; forced fallback `(['false'], False, '[false]')`.
  - `@2012-01 = @2012-01T`: native `(['true'], True, '[true]')`; forced fallback `([], None, None)`.
- Spec basis: §6.1 requires single-item operands to be the same type or implicitly convertible. `Date` and `DateTime` are distinct primitive types; equivalence only changes different-precision temporal results from empty to false, not type identity.

## Commands Run
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q --tb=short` -> 5 passed.
- Native/fallback repro script in `.temp/qa/fp13_explorer_probe.py` plus focused inline probes.

## Next Step
- Fix native C++ equality dispatch so `Date` vs `DateTime` returns empty for `=`/`!=` and false/true for `~`/`!~`, then add native/fallback parity coverage and SQL extension assertions.
