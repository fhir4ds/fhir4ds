# QA Handoff — CQL-06 HISTORIAN (iteration 1, 2026-08-20)

## Chunk
CQL 1.5 Type Operators — Conversion Checks (CanConvertQuantity, ConvertQuantity, ConvertsTo{Boolean,Date,DateTime,Decimal,Long,Integer,Quantity,Ratio,String,Time}).

## Method
HISTORIAN pass: re-verified the prior SKEPTIC fix (bare calendar-duration keywords in ToQuantity/ConvertsToQuantity/ToRatio/ConvertsToRatio) on BOTH backends (Python-supplements and native-extension) plus ~45 fresh dual-backend probes and a 30-case end-to-end `translate_cql → to_sql() → DuckDB` matrix in `/mnt/d/fhir4ds/.temp/qa/cql06_historian_2026_08_20/`. Spec semantics verified against CQL 1.5 Appendix B (§ToString, §ToQuantity, Table 9-G) fetched live from cql.hl7.org.

## SKEPTIC fix re-verification: PASS
- ToQuantity('5 years') / ('4 days') / ('5 seconds') / ('-5 years') / ('+5 months') parse on both backends, identical JSON; '5 mg', '5 Years' still rejected (case-sensitive, non-calendar UCUM bare stays rejected). '5years', '5   years' accepted (spaces optional/multiple ok); '5 years ' (trailing) rejected — acceptable.
- Native/Python parity: 100% across all probes (Python ToQuantity UDF serves both registered backends; C++ to_quantity not on this serving path).

## New divergences found
- **QA-001 (HIGH)**: `ToString(4 days)` returns `"4 'day'"`. CQL 1.5 Appendix B §ToString states verbatim: "ToString(4 days) results in the string value `4 days` (i.e. not `4 'd'`)" — calendar-duration units must render as a bare keyword; the quoted `'(<unit>)`' form is for UCUM units. Table 9-G Quantity format: `(-)?#0.0# ('<unit>')|(<unit>)`. Root cause: `QuantityToString` macro in `fhir4ds/cql/duckdb/macros/conversion.py` unconditionally wraps the unit in single quotes. Affects both backends (shared macro). Reproducer: probe2_e2e.py.
- Non-issue, verified: `ConvertsToLong(2147483648)` failing translation is spec-correct — CQL 1.5 has no implicit Integer→Long literal promotion; Long literals require the `L` suffix (`ConvertsToLong(2147483648L)` translates and lowers correctly).
- All other e2e surfaces (ConvertQuantity values/units, CanConvertQuantity families, To* functions, Table 9-E/9-F boundaries) conformant and parity-clean.

## Notes for FIX
- Fix `QuantityToString` in `fhir4ds/cql/duckdb/macros/conversion.py`: emit the unit bare (unquoted) when it is in `_CQL_CALENDAR_DURATION_UNITS` (data-driven registry in `udf/quantity.py`), keep quoted form for UCUM units ('5 cm' → `5 'cm'`). Ensure round-trip: ToQuantity(ToString(4 days)) must still equal the source.
- Regression guard: existing tests asserting quoted calendar output (if any) must be updated to the spec form; UCUM quoting must remain unchanged.
