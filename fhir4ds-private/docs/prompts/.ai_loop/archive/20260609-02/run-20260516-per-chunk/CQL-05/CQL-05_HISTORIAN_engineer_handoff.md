# CQL-05 HISTORIAN Engineer Handoff

Changed files for this role:

- `fhir4ds/cql/translator/expressions/_query.py`: added Choice/Tuple type specifier naming, validation, static tuple inference, recursive structural conformance, and typed Children()/Descendants() item checks.
- `fhir4ds/cql/translator/expressions/_operators.py`: routed Choice/Tuple targets through structural `is`/`as`, avoided generic translation of structural `as` targets, and lowered Quantity-to-String conversion through `QuantityToString`.
- `fhir4ds/cql/duckdb/udf/list.py`: encoded primitive structural child items with internal CQL type tags so downstream `is`/`as` can distinguish Integer, Boolean, Decimal, and String.
- `fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py`: added native-loaded versus forced Python fallback coverage for Choice/Tuple targets, structural child primitive identity, and Quantity convert-to-String.

Implementation note: the primitive tags are internal to the CQL structural traversal UDF surface. Translator consumption is limited to scalar items extracted from `cqlChildren`/`cqlDescendants` lists, so ordinary string-to-integer conversion behavior is unchanged.
