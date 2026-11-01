# Engineer Handoff - FP-13 SKEPTIC

Resolved all open QA issues.

## Fixes

- `QA-001` native Quantity equivalence:
  - Spec: FHIRPath §6.1.2 multi-item equivalence is order-independent and
    Quantity equivalence compares compatible dimensions across units.
  - Root cause: native multi-item `~` used generic JSON equivalence for
    resource-backed Quantity path values, and JSON Quantity materialization did
    not preserve numeric source precision for tolerance matching.
  - Change: `fpValueAsQuantity()` now preserves JSON Quantity `value`
    source text, and native `valuesEquivalent` converts Quantity-like values
    before generic JSON equivalence.

- `QA-002` Python Decimal equivalence:
  - Spec: FHIRPath §6.1.2 Decimal equivalence rounds to the least precise
    operand; §5.7.8 defines 0.5-or-higher round-up behavior.
  - Root cause: fallback `Decimal.quantize()` used the default half-even
    context, and zero-precision equivalence used Python `round()`.
  - Change: fallback decimal equivalence now uses `ROUND_HALF_UP` for all
    precision levels.

## Validation

- Fresh QA repro: `.temp/qa/fp13_skeptic_probe_after_fix.log`, 32/32 clean.
- Focused parity: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q` -> 8 passed.
- Native extension: `extensions/fhirpath/build/release/test/unittest '*fhirpath*'` -> 538 assertions passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Artifacts

- Deep research note for the failed first native attempt:
  `fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`.
- Rebuilt and copied bundled native extension:
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.
