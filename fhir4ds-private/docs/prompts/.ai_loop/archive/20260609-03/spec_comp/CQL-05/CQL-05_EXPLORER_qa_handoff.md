# QA Handoff — CQL-05 EXPLORER

## Scope

SPEC COMPLIANCE CHUNK CQL-05: CQL structural type operators:
`As<T>(argument)`, `Children(argument)`, `Convert to<T>(argument)`,
`Descendants(argument)`, and `Is<T>(argument)`.

EXPLORER probes focused on edge combinations after SKEPTIC/HISTORIAN:
strict `cast` versus nullable `as`, conversion through `Any`, nested
Quantity/Ratio/clinical conversions, List/Tuple assertion metadata,
Children/Descendants over nested tuple/list values, null/mixed-list behavior,
and native-loaded versus forced Python fallback parity.

## Findings

### QA-001 — HIGH — Structural Traversal Lost Nested Primitive Type Tags

Spec basis: CQL 1.5.3 Appendix B type operators define Children and
Descendants as returning child element values; downstream `is`/`as` test the
runtime type of those values.

Fresh reproducer:

```cql
define NestedDateDescendantIsDate:
  Last(Descendants({ a: { d: @2024-01-01 } })) is Date

define ListDateChildIsDate:
  First(Children({ a: {@2024-01-01} })) is Date

define NestedLongDescendantIsLong:
  Last(Descendants({ a: { l: 1L } })) is Long
```

Actual before fix: nested Date values were emitted as String, list Date
children were emitted as String, and nested Long descendants were emitted as
Integer.

Expected: Date/Time/Long identity must survive structural traversal so
`is`/`as` and `List<T>` checks operate on the CQL value type.

### QA-002 — HIGH — Function Inlining Dropped Strict Cast Semantics

Spec basis: CQL 1.5.3 Appendix B `cast X as T` is distinct from nullable
`X as T`; cast mismatches raise at runtime.

Fresh reproducer:

```cql
define function StrictString(x Any): cast x as String
define StrictFunctionMismatch: StrictString(5)
```

Actual before fix: translated to SQL NULL, matching nullable `as`.

Expected: translated SQL must raise `CQL strict cast failed`.

## Probe

Fresh probe written to `.temp/qa/cql05_explorer_probe.py`.

Initial failing observations were reproduced before remediation. After the
fix, the same probe passes across forced Python fallback and native-loaded
registrations.
