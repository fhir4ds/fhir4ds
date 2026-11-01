# Engineer Handoff — CQL-03 Spec Compliance, iter 1 (Remediation) — 2026-08-19

## QA-001 RESOLVED — malformed temporal literals silently accepted (HIGH)
- Root cause: `fhir4ds/cql/parser/lexer.py` `_read_datetime_literal` greedily
  collects `-T:.+Z` alnum runs; `_validate_datetime_literal` was ad-hoc
  (partial range checks only). Garbage in: `@2024-01-15.year` →
  DateTimeLiteral("2024-01-15.year") evaluated as a raw string; unpadded
  `@2024-1-1` compared True against `@2024-01-01`; `@2024-02-30` /
  `@2019-02-29` round-tripped; `+99:00` / `+02` offsets accepted; Time
  literals carried offsets / out-of-range components unchecked at lex time.
- Fix: strict CQL 1.5 grammar shape validation (zero-padded DATE/TIME/DATETIME,
  optional `Z|±hh:mm` offset restricted to [-14:00, +14:00]), full calendar
  validation incl. leap years via `datetime.date`, Time-literal range checks.
  Malformed input now raises `LexerError`. Note: regex patterns are composed
  by concatenation — rf-strings mangle `{2}` quantifiers into replacement
  fields.
- Coverage: `test_cql_malformed_temporal_literals_rejected_at_lex_time_per_spec`
  (15 valid forms parse, 18 malformed forms rejected).

## QA-002 RESOLVED — invalid-unit quantity comparison wrong on native (HIGH)
- Root cause: `extensions/cql/src/cql/quantity.cpp` `quantity_compare()`
  same-code fast path compared values without unit validation; `5 'xyz' =
  5 'xyz'` → True on C++ vs null on Python. Spec §Equal: invalid units → null.
- Fix: `same_code_unit_valid_for_compare()` guard in the same-code branch.
  Valid = table/calendar/'1' unit, UCUM annotation ('{dose}', '[pH]'),
  annotated known unit ('mm[Hg]'), or compound of valid components
  ('mg/m2'); unknown bare codes ('xyz') → null (Equal) / false (~).
- REGRESSION ENCOUNTERED AND FIXED (Recovery Gate): the first table-only
  guard broke 3 DQM measures (CMS69 75.8%, CMS771 96.8%, CMS1218 98.6% —
  they compare '{...}', 'mg/m2', '[pH]' quantities). Caught by the
  PROC_VALIDATION baseline gate; corrected to the annotation/compound-aware
  validity. A first corrected build segfaulted (infinite self-recursion for
  separator-free codes) — fixed with an early return; guard clause added.
- Final extension md5 `67c1b10a93db5cc47b26082dfc43de21`, deployed to repo
  bundle + site-packages, md5-verified, verified through reloaded
  connections.
- Coverage: `test_cql_invalid_unit_quantity_comparison_returns_null_per_spec`
  (8 cases × both backends).

## Final validation
- Chunk parity file: 17/17 pass; ratio UDFs: 40/40 pass.
- CQL unit tests (lexer/parser/cql01): 264/264 pass.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 — baseline fully restored (log:
  `.temp/qa/cql03_spec_2026_08_19/validation_summary3.log`).

## QA-003 INTENDED — ToString(Ratio) Decimal formatting (LOW)
- `ToString(1:8)` → `1.0 '1':8.0 '1'` vs `ToString(5 'mg')` → `5 'mg'`:
  deliberate Decimal-semantics formatting in RatioToString, pinned by
  `fhir4ds/cql/duckdb/tests/test_ratio_udfs.py:301-313`; both backends agree;
  spec silent on whole-value Ratio formatting. Documented in AGENTS.md.

## Validation
- Chunk parity file: 17/17 pass (was 15 + 2 new).
- CQL unit tests (lexer/parser/cql01): 264/264 pass.
- Full conformance: see architect phase / validation log at
  `.temp/qa/cql03_spec_2026_08_19/validation_summary.log`.
