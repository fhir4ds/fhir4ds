# QA Handoff: SOF-VD-02 EXPLORER

Personality: EXPLORER
Iteration: 1
Chunk: SOF-VD-02, SQL-on-FHIR ViewDefinition constants

## Probe Summary

Fresh exploration targeted pathological constant inputs and chained use:
- Lexical `%name` substitution in column paths, where filters, nested paths, comments, string literals, and URL-like string values.
- Parser and direct dataclass handling for all supported primitive `constant.value[x]` choices.
- Undefined and duplicate constant names after the SKEPTIC fix.
- DuckDB execution parity boundaries for native-loaded and forced Python fallback paths.

## Spec Anchor

SQL-on-FHIR defines `ViewDefinition.constant` as `0..*`, `constant.name` as required `1..1` with the `sql-name` invariant, and `constant.value[x]` as required `1..1` with the FHIR primitive choice list. The FHIR datatype definitions make `instant` a constrained full dateTime requiring full date, time to seconds, and timezone; `dateTime` values that include a time component use the complete `YYYY-MM-DDThh:mm:ss` form with timezone.

## Finding

`SOF-VD-02-EXPLORER-001` (HIGH): constant primitive validation accepts invalid partial date/time values before SQL generation.

Accepted invalid examples:
- `{"name": "Bad", "valueDateTime": "2016T12:00:00Z"}`
- `{"name": "Bad", "valueDateTime": "2016-11T12:00:00Z"}`
- `{"name": "Bad", "valueInstant": "2016T12:00:00Z"}`
- `{"name": "Bad", "valueInstant": "2016-11T12:00:00Z"}`

Expected: parser/direct dataclass/serializer boundaries reject these as invalid FHIR primitives.

## Suggested Fix

Keep the fix centralized in `fhir4ds/viewdef/types.py` near `_validate_primitive_value()`:
- For `dateTime`, reject values with a time component unless the date portion is a complete `YYYY-MM-DD`, and require timezone when a time component is present.
- For `instant`, require a complete `YYYY-MM-DD` date, a time component, and timezone.
- Add parser and direct `Constant.to_dict()` regression coverage.
