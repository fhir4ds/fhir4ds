# QA Handoff — CQL-01 (CQL 1.5 Primitive Types), iteration 1, SKEPTIC

## Method
Execution-level probing (translate_cql → to_sql → DuckDB SELECT with register_cql
macros), verified against local CQL 1.5 spec source
(/mnt/d/gemini/training_data/cql-master/input/pages/) and official cql-tests
fixtures. ~120 probes: literals (Boolean/Integer/Decimal/String/Long incl. 5L,
extremes), typed null, implicit numeric promotions, conversion functions
(ToInteger/ToDecimal/ToBoolean/ToLong/ToString/convert), ConvertsTo* family,
is/as, equality across precisions, null propagation, div/mod, successor,
minimum/maximum.

## Verified-correct highlights (no action)
- All literal forms, Long literals and Integer→Long→Decimal promotion, equality
  across precisions, `maximum/minimum Integer|Long|Decimal`, typed null,
  3/2=1.5 decimal division, overflow→null on constant-folded literals,
  ToBoolean full Table 9-F (t/f/yes/no/y/n/1/0, case-insensitive),
  ToInteger(Boolean/Long-in-range), string escapes ('' doubling),
  ConvertsTo* family, `1 = '1'` → null (no numeric/string conversion),
  'A' ~ 'a' → true, convert 1.9 to Integer → null (spec-correct: no
  Decimal→Integer conversion exists).

## Issues (see evolution.json)
- QA-001 HIGH: runtime Integer/Long arithmetic overflow not null-guarded
  (`maximum Integer + 1` crashes; `minimum Integer - 1` silently = -2147483649).
- QA-002 HIGH: `maximum Decimal + maximum Decimal` becomes SQL string
  concatenation (`||`), returns a concatenated string instead of null.
- QA-003 HIGH: ToDecimal('0.123456789') → null; spec requires limiting to impl
  scale (round), null only for malformed strings.
- QA-004 MEDIUM: decimal literal >8 fractional digits rejected at translation
  (ValueError) instead of being precision-limited.
- QA-005 MEDIUM: Truncate returns Decimal, spec says Integer.
- QA-006 MEDIUM: CanConvert(x, T) unimplemented; silently passes through to SQL
  → runtime CatalogException.

## Notes for FIX
- QA-001/QA-002 live in arithmetic SQL generation (operators.py / expressions/
  _operators.py); folded-literal path already correct.
- QA-002 root cause: `maximum Decimal` extent value is treated as String by
  inference when combined with `+`.
- QA-003/QA-004: two code sites — macros/conversion.py ToDecimal regexp
  ({1,8} fractional) and the literal validation raising ValueError.
- QA-006 must NOT be a hint-wrapper: either implement CanConvert or raise a
  TranslationError at translate time (no silent SQL passthrough).
