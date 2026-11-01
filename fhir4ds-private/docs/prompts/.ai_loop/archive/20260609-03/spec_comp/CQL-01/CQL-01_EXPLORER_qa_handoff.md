# QA Handoff - CQL-01 EXPLORER

Personality: EXPLORER
Chunk: CQL-01, primitive CQL types

## Scope

Fresh probes targeted primitive edge combinations after the SKEPTIC and
HISTORIAN passes: scalar parameter defaults, runtime overrides, qualified
`System.*` primitive type specifiers, `Any`/`System.Any`, definition aliases,
decimal precision preservation, string escapes, invalid numeric suffixes, and
native-loaded versus forced Python fallback DuckDB registrations.

Spec basis checked directly against CQL 1.5.3:
- Appendix B Types says `Any` is the maximal supertype and all types derive
  from it.
- Appendix B Type Operators says `as<T>(argument Any)` returns null only when
  the runtime argument is not of the requested type.

## Finding

`QA-001` HIGH: scalar primitive definitions asserted `as Any`/`as System.Any`
can generate invalid population SQL. A valid expression such as:

```cql
define I: 5
define IAsSystemAny: I as System.Any
```

materializes a scalar CTE, but the final population SELECT expects a `resource`
column from that CTE. DuckDB raises:

```text
Values list "IAsSystemAny" does not have a column named "resource"
```

The reproducer is `.temp/qa/cql01_explorer_probe.py`; it currently fails before
product remediation.

## Validation Run

- `python3 .temp/qa/cql01_explorer_probe.py` fails on `QA-001` as expected.

## Next Phase

Remediation should keep `as Any` as a primitive scalar pass-through in
definition metadata and final population output selection. Add focused coverage
for bare and qualified `Any`, plus chained `Any` assertions over materialized
primitive definitions.
