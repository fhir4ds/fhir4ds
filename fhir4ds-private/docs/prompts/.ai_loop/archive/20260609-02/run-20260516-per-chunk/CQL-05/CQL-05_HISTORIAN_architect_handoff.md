# CQL-05 HISTORIAN Architect Handoff

Durable invariants added by this pass:

- `Choice<T...>` and `Tuple { ... }` are structural type specifiers. Parser support alone is insufficient; translator `is`/`as` routing, target validation, type-name formatting, static inference, and conformance checks must all include them.
- `Children()` and `Descendants()` return `Any` collections. If the DuckDB UDF surface uses `VARCHAR[]` as the transport type, primitive items need an internal type marker before downstream `is`/`as` checks can be spec-correct.
- `as` is a type assertion, not a conversion. A structural child tagged as String must not satisfy `as Integer` just because the string text is numeric.
- `convert <Quantity> to String` should share the `ToString(Quantity)` quantity formatting path and must not fall back to generic JSON/string casting.

Regression expectation: keep native-loaded and forced Python fallback registrations paired in CQL structural parity tests whenever changing `is`, `as`, `convert`, `Children`, `Descendants`, or their helper UDFs.
