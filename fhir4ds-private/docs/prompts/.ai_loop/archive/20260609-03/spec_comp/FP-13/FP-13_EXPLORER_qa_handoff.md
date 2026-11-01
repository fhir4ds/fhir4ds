# QA Handoff: FP-13 EXPLORER

## Scope

- Chunk: FP-13, FHIRPath §6.1 Equality
- Personality: EXPLORER
- Spec source: HL7 FHIRPath Normative Release, §6.1.1-§6.1.4

## Probe Strategy

Built a fresh `.temp/qa/fp13_explorer_probe.py` that compares native DuckDB C++
extension results with forced Python fallback results across equality,
equivalence, negated operators, empty propagation, string normalization,
Quantity unit conversion, Date/Time precision, multiset collection equivalence,
nested complex objects, and `where`/`select` chains.

## Confirmed Issues

### QA-001: Native nested Decimal complex equivalence

- Reproducer: `decObjA ~ decObjB`
- Data: `decObjA.value = 1.24`, `decObjB.value = 1.2`
- Native actual: `false`
- Fallback actual: `true`
- Expected: `true`
- Spec basis: §6.1.2 says complex equivalence compares child properties
  recursively, and Decimal equivalence rounds to the precision of the least
  precise operand.

### QA-002: Nested Quantity complex equality/equivalence

- Reproducer: `rangeA = rangeB`, `rangeA ~ rangeB`
- Data: `rangeA.high = 1 cm`, `rangeB.high = 10 mm`
- Native/fallback actual: `false`
- Expected: `true`
- Control: `rangeA.high = rangeB.high` and `rangeA.high ~ rangeB.high` both
  return `true`.
- Spec basis: §6.1.1 and §6.1.2 require recursive complex child comparison,
  and Quantity equality/equivalence compare same-dimension quantities using
  unit conversion.

## Artifacts

- Probe: `.temp/qa/fp13_explorer_probe.py`
- Logs: `.temp/qa/fp13_explorer_probe.log`,
  `.temp/qa/fp13_explorer_probe_rerun.log`
