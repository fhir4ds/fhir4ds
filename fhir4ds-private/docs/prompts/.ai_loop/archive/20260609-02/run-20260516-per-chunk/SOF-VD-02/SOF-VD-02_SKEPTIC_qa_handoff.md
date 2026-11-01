## SOF-VD-02 QA Handoff - SKEPTIC

Scope probed: SQL-on-FHIR ViewDefinition constants: `constant`, `constant.name`, `constant.value[x]`, constant substitution in column and where FHIRPath expressions.

Spec anchor checked: SQL-on-FHIR v2.0.0 `ViewDefinition.constant` is `0..*`; `constant.name` is `1..1` and constrained by `sql-name` (`^[A-Za-z][A-Za-z0-9_]*$`); `constant.value[x]` is `1..1` and limited to primitive choices base64Binary, boolean, canonical, code, date, dateTime, decimal, id, instant, integer, integer64, oid, string, positiveInt, time, unsignedInt, uri, url, uuid. The spec says `%your_constant_name` in FHIRPath is replaced by the FHIR literal defined in `value[x]`.

Fresh probe written to `.temp/qa/sof_vd_02_skeptic_probe.txt`.

Issues found:

1. `SOF-VD-02-QA-001` - `constant.name` does not enforce the `sql-name` invariant. `_bad` is accepted and generates SQL; names with punctuation are parsed as constants and later mis-tokenized as partial undefined `%bad` references.
2. `SOF-VD-02-QA-002` - `constant.value[x]` is not exactly-one supported-choice validation. Multiple `value*` fields silently choose the first, unsupported `valueFoo` is accepted, null typed values are accepted, and supported `canonical` / `integer64` only work through the unsupported fallback with wrong type casing and no typed accessors.

Recommended remediation:

- Centralize constant value choice metadata so parser and `Constant.from_dict()` cannot drift.
- Enforce name shape at parse/convenience-constructor boundaries.
- Reject zero, multiple, unsupported, or null `value[x]` fields with explicit `ParseError` or `ValueError`.
- Add `valueCanonical` and `valueInteger64` accessors and tests for parser, SQL generation, DuckDB execution, and the official ViewDefinition conformance subset.
