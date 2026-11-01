# QA Handoff - CQL-07 SKEPTIC

## Scope

CQL-07 conversion functions, focused on weak spots after CQL-06: unit-bearing conversions, ratio parsing, and native-loaded versus forced Python fallback parity.

## Finding

`ToQuantity('5 ''not-a-unit''')` and `ToRatio('1 ''not-a-unit'':2 ''mg''')` return JSON instead of NULL. Their conversion checks also return true. The CQL reference requires the quantity string unit designator to be a valid case-sensitive UCUM unit or CQL calendar duration keyword, and `ToRatio` delegates each side to the `ToQuantity` quantity format.

Recorded as `QA-001` in `evolution.json`.
