# Architect Handoff - CQL-11 HISTORIAN

The HISTORIAN pass for CQL-11 is clean after remediation. Seven findings were fixed and verified across the translated CQL surface, native C++ DuckDB extension, forced Python fallback, and C++-only/browser-style direct helper surface.

Architectural guardrails to preserve:

- Dynamic FHIR `value[x]` operands in numeric-only CQL Arithmetic Part 2 operators must use typed numeric projection (`fhirpath_number`), not `fhirpath_text` plus SQL coercion.
- CQL minimum/maximum constants should be folded at translation boundaries when the spec defines representational underflow/overflow; do not rely on DuckDB arithmetic promotion or public helper behavior to discover these cases.
- Decimal boundary constants must be emitted as numeric SQL literals, not quoted strings, when participating in numeric expressions.
- Public DuckDB helper UDFs remain part of the compatibility surface. Python fallback, native-loaded C++, and no-Python/C++-only direct calls must agree for overflow, invalid temporal strings, and precision counting.
- DateTime timezone suffixes are metadata for offset handling, not precision digits.

Update durable docs with these rules before archiving this role. The golden standard for this role is in `.temp/architect/golden_standard.md`.
