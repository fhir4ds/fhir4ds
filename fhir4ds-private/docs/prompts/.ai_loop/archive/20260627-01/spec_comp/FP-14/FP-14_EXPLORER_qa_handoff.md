# QA Handoff - FP-14 EXPLORER

Spec focus: FHIRPath §6.2 Comparison (`>`, `<`, `<=`, `>=`).

Spec source consulted: official HL7 FHIRPath continuous-build source,
`input/pages/index.md`, §6.2 Comparison. Normative basis used for this pass:
comparison operators are defined only for String, Integer, Long, Decimal,
Quantity, Date, DateTime, and Time; empty operands return empty; multi-item
operands are errors; operands must be the same type or implicitly convertible;
Integer/Long may compare to Decimal; String ordering is lexical by Unicode
character value; Quantity ordering requires commensurable units; mixed
calendar-vs-UCUM year/month durations are not comparable; partial temporal
precision mismatches return empty; DateTime comparisons respect timezone
offsets.

Personality: EXPLORER.

Hypotheses tested:
- Large Long, Decimal, JSON numeric, and same-unit Quantity comparisons might
  still lose exact ordering above binary64 precision.
- Forced Python fallback might still compare resource-backed FHIR temporal
  primitive strings lexically instead of materializing Date/DateTime/Time.
- Unicode String ordering might differ between Python scalar ordering and
  native UTF-8 string ordering.
- Scoped/path Quantity comparisons and converted units might diverge when
  mixed with large JSON numeric source text.
- Public DuckDB result surfaces might disagree on empty, multi-item, or
  statically invalid comparison expressions.

Fresh artifacts:
- `.temp/qa/fp14_explorer_fresh_probe.py`

Validation performed during QA:
- `python3 .temp/qa/fp14_explorer_fresh_probe.py`

Result:
- Fresh probe passed 37 expressions across native C++ DuckDB and forced Python
  fallback registrations.
- No native/fallback mismatches found.
- No FP-14 issues opened.

Notes:
- The probe initially produced false failures because running a script from
  `.temp/qa` can import an installed stale `fhir4ds` package instead of the
  current checkout. The probe now forces the repository root onto `sys.path`
  before importing `fhir4ds`.
- Review-10 findings were checked for intersection. The open regex,
  delimited-identifier, direct type-specifier, and direct substring findings do
  not affect this §6.2 comparison pass.
