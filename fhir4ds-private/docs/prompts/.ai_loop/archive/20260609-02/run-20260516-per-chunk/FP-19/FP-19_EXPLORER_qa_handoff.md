## QA Handoff - FP-19 EXPLORER

Scope: FHIRPath N1 §7 aggregates and §8 lexical elements.

Personality: EXPLORER.

Spec anchors checked:
- §7.1 `aggregate(aggregator [, init])` uses `$total` and `$this`.
- §4.1.8 and §12.1 grammar define Quantity as `NUMBER unit?`, with calendar duration keywords as units.
- §8.1 whitespace is token trivia and §12.1 sends whitespace/comments to the hidden channel.
- §8.5-§8.7 cover keyword identifiers, delimited identifiers, escapes, and case sensitivity.

Fresh probes:
- Nested aggregate expressions, aggregate on empty input with/without init, mixed collections, `$index` inside aggregate, and post-aggregate scope restoration.
- Comments before expressions, between dot/function/index tokens, and around arithmetic symbols.
- Escaped delimiters in string literals and backtick identifiers, Unicode delimited identifiers, keyword identifiers (`as`, `is`, `contains`) and reserved keywords through backticks.
- Case-sensitive keyword/literal boundaries, malformed temporal/comment/string/backtick lexemes, and public wrapper result shapes across `fhirpath`, `fhirpath_text`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_number`, and `fhirpath_is_valid`.

Finding:
- `FP19-EXP-001` MEDIUM: forced Python DuckDB fallback rejected no-whitespace calendar quantity literals such as `1month`, `1months`, `1millisecond`, and `1year + 2months`, while native DuckDB and the Python core accepted them. This is public native/fallback parity drift and conflicts with the grammar's `quantity: NUMBER unit?` shape.

Non-findings:
- Aggregate scope restoration and nested aggregate variables matched between native and forced fallback.
- Comments embedded around expression tokens matched between native and forced fallback.
- Delimited identifiers with escaped backticks, backslashes, Unicode escapes, and keyword names matched.
- Simple Unicode identifier `é` is invalid under the N1 grammar's ASCII `IDENTIFIER` rule; delimited Unicode identifiers work.
