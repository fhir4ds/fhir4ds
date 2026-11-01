# QA Handoff: CQL-19 EXPLORER List Operators Part 2

## Scope

Fresh EXPLORER probe for List Operators Part 2: `Last`, `Length`, list
`!=`/`!~`, `properly includes`, `properly included in`, `singleton from`,
`Skip`, `Tail`, `Take`, and `union`.

Tested translated CQL plus direct helper SQL against forced Python fallback,
native-loaded registration, and no-Python/browser-style C++ plus pure SQL
macros. Source/spec inputs were current source, official CQL reference Appendix
B, and current official XML conformance cases; archived workflow outputs were
not used as proof.

## Finding

`QA-001` MEDIUM SPEC_VIOLATION: Temporal list membership and equality collapsed
CQL temporal uncertainty to boolean false/true.

Reproducer from `.temp/qa/cql19_explorer_probe.py`:

- `{ @T15:59:59.999, @T20:59:59.999 } properly includes @T15:59:59`
- `@T15:59:59 properly included in { @T15:59:59.999, @T20:59:59.999 }`
- `@T15:59:59 in { @T15:59:59.999, @T20:59:59.999 }`
- `{ @T15:59:59.999 } != { @T15:59:59 }`

Expected: SQL NULL for temporal uncertainty.
Actual before remediation: `false` for membership/proper inclusion and `true`
for `!=`.

Spec basis: CQL Reference Appendix B list operators use CQL equality for list
membership/inclusion/equality; CQL temporal equality is uncertain when the
shared specified precision matches but one operand has more precise components.
The current official XML includes `ProperContainsTimeNull` and
`ProperInTimeNull` expecting null for this exact Time-precision boundary.

## Fresh Probe Result

After remediation, `python3 .temp/qa/cql19_explorer_probe.py` passed.
