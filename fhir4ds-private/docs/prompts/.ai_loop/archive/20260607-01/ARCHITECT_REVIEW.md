# Architecture Self-Audit: CQL Tests Runner Remediation

## Invariants

1. Facade serialization must not decide CQL semantics.
2. Parser changes must produce typed AST structures, not raw string hacks.
3. Translator changes must preserve CQL type metadata without introducing
   mid-pipeline `SQLRaw` or silent fallbacks.
4. UDF/runtime changes must preserve forced Python fallback and native-loaded
   DuckDB parity where both surfaces exist.
5. Null, false, empty list, and evaluation error must remain distinct.
6. Integer, Long, Decimal, Quantity, Ratio, Date, DateTime, Time, Code, and
   Concept must remain distinct semantic types.
7. Runner-owned extractor limitations must be documented rather than patched
   through invalid FHIR output.
8. Every remediation slice must have a targeted runner probe and a local
   owning-layer regression test.

## Audit Findings

- The draft correctly avoids facade-only semantic fixes.
- The draft needs the implementation to verify ownership with direct probes
  before edits; this is now explicit.
- Long is high-risk because current runner expected values are JavaScript
  `BigInt` while actual FHIR values are extracted as JavaScript `number`.
  Implementation must distinguish local metadata preservation from runner
  extraction limitations.
- Ratio literals should not be implemented by text replacement. They need AST
  representation and structured Ratio lowering.
- Interval/list null semantics likely touch broad UDF helpers. Validation must
  include existing interval/list parity tests, not only runner probes.
- Documentation should be delayed until the final observed baseline is known.

## Result

The design is acceptable for implementation if the engineer works in slices and
does not attempt a broad unvalidated rewrite.

