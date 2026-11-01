# QA Handoff - FP-13 SKEPTIC

Spec source verified directly: HL7 FHIRPath Normative Release v2.0.0,
§6.1.1-§6.1.4. Equality propagates empty operands, multi-item equality is
order-dependent, equivalence treats empty-empty as true, multi-item equivalence
is order-independent, Quantity equivalence compares compatible dimensions
across units, Date/Time precision mismatches are false for `~` but empty for
`=`, and `!=` / `!~` are converses.

SKEPTIC source-first hypotheses:
- Native multi-item `~` might compare resource-backed Quantity JSON through
  generic JSON equivalence rather than Quantity unit conversion.
- Strict complex `=` might depend on raw JSON object key order instead of child
  property equality.
- Decimal equivalence ties might drift between C++ `round()` and Python
  `Decimal.quantize()`.
- Date/Time equality might mishandle precision, seconds/milliseconds, or
  timezone normalization.
- Negated operators might fail empty propagation/converse rules.

Fresh probe:
- Script: `.temp/qa/fp13_skeptic_probe.py`
- Log: `.temp/qa/fp13_skeptic_probe.log`
- Coverage: 32 cases across empty propagation, strings, numeric/decimal,
  multi-item collection equality/equivalence, Quantity unit conversion,
  Date/Time precision/timezone cases, complex equality, and negated operators.
- Backends: native C++ DuckDB extension loaded; forced Python fallback loaded
  with fake DuckDB version.

Findings:
- `QA-001` MEDIUM: native `component.value ~ referenceRange.high` returns
  false while fallback returns true. Expected true per §6.1.2 because the two
  multi-item Quantity collections are equivalent order-independently after
  unit conversion (`1 cm`/`2 cm` vs `0.02 m`/`10 mm`).
- `QA-002` MEDIUM: forced Python fallback `1.25 ~ 1.2` returns true while
  native returns false. Expected false because Decimal equivalence rounds to
  the least precise operand and FHIRPath round semantics are half-up.

Controls that passed:
- Empty propagation for `=`, `!=`, `~`, `!~`.
- String case/whitespace equivalence.
- Literal Quantity equality/equivalence, including calendar vs definite
  durations.
- Date/Time precision and timezone examples from §6.1.
- Complex CodeableConcept equality/equivalence with differing JSON key order.
