# CQL-07 HISTORIAN Architect Handoff

## Architectural Note

CQL structural values such as Quantity and Ratio are represented internally as
JSON strings in DuckDB, but CQL `ToString` is a typed conversion operator. The
translator must use static CQL type information to choose structural formatting
helpers instead of falling through to generic SQL string casts.

## Invariant Added

When CQL translation can statically identify a Ratio operand for `ToString(...)`
or `convert ... to String`, generated SQL must call `RatioToString(...)`.
Generic `TRY_CAST(... AS VARCHAR)` is not valid for Ratio because it exposes the
internal JSON representation and is not round-trippable CQL Ratio text.

## Residual Risk

Direct SQL calls to the generic DuckDB `ToString` macro do not carry CQL static
type information. CQL-authored expressions are covered by translator routing;
direct SQL users should call `RatioToString` for Ratio JSON values.
