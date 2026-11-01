# QA Handoff: FP-08 EXPLORER

## Scope

FHIRPath §5.5.7 Quantity Conversion, §5.5.8 String Conversion, and §5.5.9 Time Conversion:
`toQuantity([unit])`, `convertsToQuantity([unit])`, `toString()`, `convertsToString()`, `toTime()`, and `convertsToTime()`.

## Spec Anchor

Verified against the FHIRPath Normative Release §5.5.7-§5.5.9. Key rules used:

- Quantity String conversion must match `(?'value'(\+|-)?\d+(\.\d+)?)\s*('(?'unit'[^']+)'|(?'time'[a-zA-Z]+))?`; quoted unit text is non-empty.
- String/time/quantity conversion functions operate on empty or singleton input; multi-item input signals an error to the calling environment.
- DuckDB public UDFs are expected to convert semantic errors to empty/NULL outside strict mode while preserving native/fallback parity.

## Exploration

Created `.ai_loop/.temp/qa/` and probed native C++ DuckDB registration against forced Python fallback registration.

Hypotheses tested:

1. Multi-item conversion inputs might leak the first item in native C++.
2. Quantity String parser might accept malformed unit shapes near official conformance examples.
3. Optional target-unit conversion could diverge between native and fallback.
4. Partial time precision and invalid time strings could diverge across backends.
5. Wrapper UDFs (`fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_quantity`) might disagree on empty/error propagation.

## Finding

`QA-001` MEDIUM OPEN: Native C++ accepts empty quoted quantity units.

Reproducer:

```python
resource = {"resourceType": "Observation", "q_empty_unit": "1 ''"}
expression = "q_empty_unit.toQuantity()"
```

Actual native C++ DuckDB:

```text
fhirpath       -> ["1 ''"]
fhirpath_json  -> [{"value":1,"unit":""}]
fhirpath_quantity -> "1 ''"
```

Forced Python fallback:

```text
fhirpath/fhirpath_json/fhirpath_quantity -> empty/NULL
```

`q_empty_unit.convertsToQuantity()` similarly returns `true` natively and `false` in forced fallback.

Expected: empty/false. The spec regex uses `[^']+`, requiring at least one character inside quoted units.

## Non-Findings

- Multi-item probes for the scoped conversion functions returned empty/NULL consistently through public UDFs.
- `1 day` target conversion to `hours` matched across native and forced Python fallback.
- Bare UCUM duration abbreviation `1 d` and prior negative `1 wk` remained rejected across native and fallback.
- Timezone-suffixed Time strings are rejected consistently; local R4 official compliance fixtures mark time literals with timezone suffixes invalid for this implementation target.

## Validation Run During QA

- Native versus forced Python fallback exploratory probe for Quantity/String/Time conversions.
- Local R4 compliance fixtures inspected for relevant conversion anchors.

## State

`evolution.json` updated with `QA-001` as OPEN.
