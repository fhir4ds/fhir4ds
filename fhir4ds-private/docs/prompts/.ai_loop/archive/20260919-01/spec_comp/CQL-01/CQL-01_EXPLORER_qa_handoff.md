# QA Handoff — CQL-01 EXPLORER (iteration 1, 2026-08-19)

## Method
EXPLORER boundary-combination pass over CQL 1.5 primitive types (Any, Boolean,
Integer, Decimal, String, Long). ~100 probe cases in
`/mnt/d/fhir4ds/.temp/qa/cql01_explorer3_2026_08_19/` (probe.py: dual-path
translate+execute matrix; probe2.py: extent literals + define-alias arithmetic
via `translate_library_to_population_sql` end-to-end). Every case executed on
BOTH a native-loaded connection and a forced Python-fallback connection; parity
asserted. Spec grounding: local CQL 1.5 09-b-cqlreference.md
(/mnt/d/gemini/training_data/cql-master/input/pages/) — Decimal extent
(10^28−1)/10^8 = 99999999999999999999.99999999, ToBoolean Table 9-F
(true/t/yes/y/1, false/f/no/n/0, case-insensitive), overflow → null (§9.1.1).

## Re-verification of prior fixes (SKEPTIC + HISTORIAN)
All hold: overflow guards for direct literal arithmetic (max Int+1 → NULL,
Long min/max boundaries), exact cqlDivide (9.9/3.0 = 3.3), exact list Sum /
Avg (DECIMAL(38,8)), ToDecimal scale-rounding half-up, string→Integer grammar
rejects "1.0", CanConvert lowering, string escape table incl. '' doubling,
backslash, \uXXXX.

## Verified-correct (no action)
- Long literal arithmetic and mixed Integer/Long/Decimal nested chains within
  literal scope (A-group): overflow → null, Long boundaries exact.
- minimum/maximum Integer/Long in comparisons and case expressions (B-group);
  Decimal extent value itself is correct (20 int digits per spec).
- String quoting/escapes through translation AND execution incl. concat and
  Length; Boolean Table 9-F incl. ConvertsToBoolean('yes') = true (spec
  Table 9-F explicitly lists 'yes' → true; probe expectation initially wrong).
- Any demotion: (5 as Any)+1=6, (0.1 as Any)+(0.2 as Any)=0.3 exact,
  ('a' as Any)+'b'='ab', ToInteger('5' as Any)=5.
- ToX extremes: null/empty/space inputs → null, '+'-sign, leading zeros,
  Integer/Long range boundaries from strings, ToDecimal(true)=1.0.
- Typed null casts: (null as String)+'x' → null, Length(null as String) null.
- Type-keyword case sensitivity: lowercase `integer`/`string` etc. rejected
  as unresolved type specifiers (CQL type identifiers are case-sensitive).
- Define-alias arithmetic WITHOUT literal mixing (M + N = 0.3 exact, BIG
  Long overflow alias → null, string alias concat, typed-null alias concat).

## Issues (see evolution.json)
- QA-001 HIGH: define-alias Decimal arithmetic mixed with a numeric literal is
  forced through DOUBLE (`TRY_CAST((SELECT sub.value FROM "M") AS DOUBLE)` in
  `_operators.py` ~6960-6975): `define N: M + 0.2` → 0.30000000000000004,
  `(M+N)*3 = 0.9` → false. Spec: Decimal arithmetic exact.
- QA-002 HIGH: same alias path promotes Integer alias to DOUBLE, bypassing
  overflow: `define I: 2147483647; I + 1` → 2147483648.0 (expect null).
- QA-003 MEDIUM: out-of-range Decimal literals (e.g. 99999999999999999999999999.99,
  or even 100000000000000000000000000.0 whose +1 exceeds the extent) translate
  and execute silently; Integer/Long equivalents raise. Inconsistent
  strict-literal policy.

## Notes for FIX
- Root site: `fhir4ds/cql/translator/expressions/_operators.py` — the
  "cast the non-numeric side to DOUBLE so DuckDB arithmetic works" branch for
  SQLSubquery operands. definition_meta carries the referenced define's
  cql_type; use it to select INTEGER/BIGINT/DECIMAL(38,8) instead of DOUBLE,
  and ensure integral alias arithmetic gets the same TRY(...) overflow wrap
  the literal path already has (see final result assembly ~line 7149, which
  currently excludes subqueries via `_contains_sql_subquery`).
- QA-003: parser literal range check exists for Integer/Long
  (ValueError "out of range"); add the Decimal extent check (|value| >
  99999999999999999999.99999999 → raise). Careful: ToDecimal('...') of
  out-of-range strings must still return null at runtime (F02 passes).
  Conformance gate must stay 1706/1706 — check official fixtures do not use
  >extent Decimal literals.
