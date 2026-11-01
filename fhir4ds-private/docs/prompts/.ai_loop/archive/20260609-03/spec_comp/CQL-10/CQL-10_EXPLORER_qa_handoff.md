# QA Handoff: CQL-10 EXPLORER

## Scope

- Chunk: CQL-10, Arithmetic Operators Part 1.
- Personality: EXPLORER.
- Spec anchor: CQL Reference v1.5.3 Appendix B, arithmetic operators.
- Probe: `.temp/qa/cql10_explorer_probe.py`.

## Fresh Exploration

The probe recomposed direct public helper calls and translated CQL over forced Python fallback, native-loaded registration, and C++-only extension loading where that extension exports the helper surface. It covered:

- `HighBoundary`/`LowBoundary` default and explicit precision, timezone suffixes, invalid dates/times, exponent numeric text, and huge exponent rejection.
- `Log`/`Ln` public Python/native macro behavior, including invalid bases and one-argument `Log` rejection.
- C++-only exported `mathLog`/`mathLn` behavior for invalid inputs.
- Dynamic FHIR numeric choices through arithmetic, ensuring `valueString` is not numeric evidence.
- Quantity arithmetic over malformed/empty JSON, null operands, scalar/Quantity boundaries, query aliases, singleton-from values, and temporal Quantity edges.

## Result

The fresh probe itself passed. An early probe run produced a false Quantity signal because `.temp/qa` was importing an installed `fhir4ds` package instead of the workspace source; the probe now pins `/mnt/d/fhir4ds` into `sys.path` before importing project modules.

Focused pytest validation then exposed `QA-001`: translated numeric `HighBoundary(1.587)` returned `NULL` in the forced Python fallback because the translator cast the boundary helper's DuckDB `UNION(VARCHAR, DOUBLE)` output directly to `DOUBLE`.

Validation from the fresh probe:

```json
{
  "direct_sql_cases": 23,
  "translated_definitions": 10,
  "cpp_only_checked": true,
  "status": "PASS"
}
```

## State

- `QA-001` was logged for remediation.
