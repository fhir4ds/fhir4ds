# QA Handoff: CQL-04 SKEPTIC

Scope: CQL logical operators `And`, `Implies`, `Not`, `Or`, and `Xor`.

Spec basis: CQL 1.5.3 Appendix B logical operators define Boolean signatures
and three-valued null behavior. The existing repository invariant also requires
Boolean-only translator validation, with `between ... and ...` handled as a
parser separator exception.

Hypotheses tested:
- Direct DuckDB helper macros might inherit DuckDB numeric/string truthiness.
- Native `logicalImplies` VARCHAR overload might treat malformed Boolean text
  as false.
- Static clinical/complex CQL operands might bypass Boolean-only validation.
- Precedence might regress for `and`, left-to-right `or`/`xor`, and low
  precedence `implies`.
- `between ... and ... and true` might be misread as a logical operand error.

Findings:
- `QA-001` HIGH `SPEC_VIOLATION`: direct public logical helpers accepted
  invalid operands through DuckDB truthiness or malformed Boolean text. Examples:
  `"And"(1, true) -> true`, `"Xor"(1, false) -> true`, `"Not"(1) -> false`, and
  no-Python `logicalImplies('yes','false') -> true`.
- `QA-002` HIGH `SPEC_VIOLATION`: translated logical validation did not classify
  static clinical/complex operands such as `Code { ... }`, allowing raw SQL
  generation for non-Boolean logical operands.

QA reproducer: `.temp/qa/cql04_skeptic_probe.py`.
