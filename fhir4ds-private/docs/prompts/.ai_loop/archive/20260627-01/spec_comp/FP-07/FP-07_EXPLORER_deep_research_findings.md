### Deep Research: QA-002

**1. Spec Determination:**
FHIRPath §4.1 defines Long as a signed 64-bit whole-number type. FHIRPath
§5.5.6 says `toDecimal()` accepts Integer, Long, or Decimal inputs and returns
a Decimal value. Existing project behavior represents Decimal text with a
`.0` suffix for whole-number Decimal conversion outputs.

**2. Prior Art:**
The existing FP-07 parity tests expect `2147483648L.toDecimal()` to surface as
`2147483648.0` and JSON integer `i.toDecimal()` to surface as `1.0` in both
native and forced fallback paths.

**3. Approaches Attempted:**
The first native patch copied `source_text` through both literal Integer values
and JSON values whose effective type is Integer. This fixed max-Long literal
Decimal text but regressed JSON integer conversion: `i.toDecimal()` returned
`1` instead of `1.0`.

**4. Blast Radius:**
`fn_toDecimal()` handles native literal Longs, ordinary Integer literals,
FHIR/JSON integer path values, and Boolean conversion. Only actual
`FPValue::Type::Integer` values can carry the Long-literal `source_text` added
by `eval(LongLiteral)`. JSON numeric path values are `JsonVal` with
effective type Integer and must keep the pre-existing Decimal formatting path.

**5. Recommended Path:**
Keep exact `source_text` propagation only in the `val.type ==
FPValue::Type::Integer` branch that receives literal Longs. Remove the
`source_text` copy from the later `effectiveType(val) == Integer` branch so
resource-backed JSON integers continue formatting Decimal results as `1.0`.
