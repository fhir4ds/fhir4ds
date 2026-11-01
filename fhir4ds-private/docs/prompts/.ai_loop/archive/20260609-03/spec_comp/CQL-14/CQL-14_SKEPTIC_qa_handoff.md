# QA Handoff - CQL-14 SKEPTIC

Scope: CQL Date/Time Operators Part 2: `Now()`, `Today()`, `TimeOfDay()`, precision `same` / `same or before` / `same or after` / `on or before` / `on or after`, `DateTime - Quantity`, and `Time(...)`.

Spec grounding: the current CQL Reference defines `DateTime/Date/Time - Quantity` as precision-preserving temporal arithmetic with null propagation, `Time(...)` as an Integer component constructor, and `TimeOfDay()` / `Today()` as values derived from the evaluation request timestamp. Source consulted: https://cql.hl7.org/09-b-cqlreference.html#datetime-operators-3

Fresh probe written: `.temp/qa/cql14_skeptic_probe.py`.

Hypotheses tested:
- Current-clock helpers might be unstable or malformed across direct SQL and translated CQL.
- Time-only `same` comparisons might diverge between Python fallback and native C++.
- Unsupported precision strings such as `week` might silently default instead of returning SQL NULL.
- Partial DateTime quantity subtraction might mishandle month remainders or output precision.
- `Time(12, null as Integer, 0, 0)` might incorrectly construct a value despite an unspecified lower-precision component.

Result: no new defects found.

Validation:
- Fresh probe: PASS across forced Python fallback, native-loaded registration, and no-Python/native C++ runtime.
- Focused parity/no-Python tests: `10 passed`.
- Official datetime parser category: `246 passed`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706` including `CqlDateTimeOperatorsTest.xml 317/317`, DQM `47/47`, overall `2822/2822`.
