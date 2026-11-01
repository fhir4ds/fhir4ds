# QA Handoff: CQL-05 SKEPTIC

## Scope

SPEC COMPLIANCE CHUNK CQL-05: structural CQL type operators:
`As<T>(argument)`, `Children(argument)`, `Convert to<T>(argument)`,
`Descendants(argument)`, and `Is<T>(argument)`.

Spec sources checked:
- CQL 1.5.3 Appendix B Type Operators, especially `As`, `Children`, `Convert`,
  `Descendants`, `Is`, `ToQuantity`, and `ToString`.
- CQL 1.5.3 Logical Specification Type Operators.

## SKEPTIC Hypotheses

1. `convert ... to Any` might erase the original runtime type and let later
   `as` behave like conversion.
2. Nested conversion through `ToQuantity(...)` might lose Quantity shape before
   `convert ... to String`.
3. Composite typed nulls might fall through to generic FHIR resource probing.
4. `Children()` / `Descendants()` typed transport could coerce primitive child
   values or mishandle null descendants.
5. Dynamic FHIR `value[x] as Quantity/Concept` could diverge between native
   extension and forced Python fallback.
6. Public helper surfaces might differ across native-loaded, forced fallback,
   and no-Python C++ registration where the same function exists.

## Fresh Probe

Created and ran:

```bash
python3 .temp/qa/cql05_skeptic_probe.py
```

Final result: `CQL-05 SKEPTIC probe passed`.

## Findings

Four HIGH spec violations were confirmed and logged in `evolution.json`:

- `QA-001`: `convert ... to Any` erased source type before later `is`/`as`.
- `QA-002`: nested `convert ToQuantity(...) to String` returned internal JSON.
- `QA-003`: `(null as List<Integer>) is List<Integer>` returned SQL NULL.
- `QA-004`: `QuantityToString` formatted JSON integer quantities as `5 'mg'`
  instead of CQL `5.0 'mg'`, with native/fallback drift.

No additional open QA issues remain after remediation and validation.
