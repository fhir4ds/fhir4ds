# QA Handoff - FP-06 SKEPTIC

## Scope

SPEC COMPLIANCE CHUNK FP-06: FHIRPath §5.5.1 `iif`, §5.5.2 Boolean Conversion, and §5.5.3 Integer Conversion.

Spec source consulted: official HL7 FHIRPath continuous-build source, `input/pages/index.md`, lines covering singleton evaluation and conversion functions.

Normative points used:
- Singleton evaluation for a Boolean input treats a single non-Boolean item as `true` when it cannot be implicitly converted to Boolean.
- `iif(criterion, true-result, otherwise-result)` evaluates only the selected result branch and its criterion uses singleton Boolean evaluation.
- The spec examples explicitly state `iif(0, 'true', 'false')` returns `'true'` because `0` is a non-empty singleton, not Boolean false.
- `toBoolean()` accepts only the listed Boolean representations; `convertsToBoolean()` returns whether `toBoolean()` would succeed.
- `toInteger()` accepts Integer/Long, integer-grammar Strings, and Boolean; `convertsToInteger()` mirrors that convertibility.

## Fresh Probe

Created `.temp/qa/fp06_skeptic_fresh_probe.py` with native DuckDB/C++ and forced Python fallback comparisons across 25 expressions.

Hypotheses tested:
- `iif` may accidentally evaluate unselected branches.
- `iif` may mishandle singleton non-Boolean criteria, especially numeric zero.
- `iif` may overwrite or lose an outer `$index`.
- Boolean conversion may over-accept lexical variants such as `'1.00'`.
- Integer conversion may mishandle signs, whitespace, and 32-bit range boundaries.

## Finding

`QA-001` MEDIUM OPEN: forced Python DuckDB fallback treats numeric zero criteria in `iif` as Boolean false.

Evidence before remediation:

```text
iif(0, 'T', 'F') native= (['T'], '["T"]', True) fallback= (['F'], '["F"]', True)
iif(0.0, 'T', 'F') native= (['T'], '["T"]', True) fallback= (['F'], '["F"]', True)
iif(0.toInteger(), 'T', 'F') native= (['T'], '["T"]', True) fallback= (['F'], '["F"]', True)
```

Expected: `['T']` for all three, per FHIRPath §5.5.1 and singleton evaluation.

## Review Finding Intersection

REV-FP-001 through REV-FP-004 do not intersect this FP-06 finding. No invalid surrogate, delimited identifier, R4 type table, or trailing-whitespace behavior was used as proof.
