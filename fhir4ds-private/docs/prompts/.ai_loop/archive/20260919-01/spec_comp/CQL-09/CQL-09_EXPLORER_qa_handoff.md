# QA Handoff — CQL-09 Comparison Operators (EXPLORER, iteration 1)

## Scope
EXPLORER pass over the SKEPTIC+HISTORIAN-fixed tree. ~110 dual-path cases
(python supplements vs native registration; zero parity divergences on any
case). Probes: `.temp/qa/cql09/explorer_probe{1,2,3,4}*.py`.

## Mandate surfaces verified CONFORMANT (spec text fetched from cql.hl7.org §9)
- Equivalent (~) temporals at differing precision -> FALSE not null
  (`@2012-01-01T12:00 ~ @2012-01-01T12:00:00`, `@2012-01 ~ @2012-01-01`,
  `@T12:00 ~ @T12:00:00`); combined sec/ms precision decimal-equivalent
  (`.000 ~ (no ms)` -> true); offsets (`+01:00 ~ Z` same instant -> true;
  differing precision with offset -> false).
- ~ quantities: `100 'cm' ~ 1 'm'` true; calendar vs UCUM `1 'year' ~ 1 'a'`,
  `1 'month' ~ 1 'mo'`, `7 'day' ~ 1 'week'` true; `12 'month' ~ 1 'year'`
  false; cross-dimension false.
- ~ null handling never null: `null ~ null` true, `null ~ x` false,
  `'' ~ null` false; tuples/lists with nulls (`Tuple{a:1} ~ Tuple{a:1.0}`
  true; `{Tuple{a:1,b:null}} ~ {Tuple{a:1,b:2}}` false).
- NotEqual/NotEquivalent null propagation (`1 != null` null; `null !~ null`
  false; `@T12:00 !~ @T12:00:00` true).
- Between: mixed Integer/Decimal operands, null bounds -> null, strings,
  temporals, quantities, Date-vs-DateTime bounds (day precision decides ->
  true, verified §9.1 `>= low and <= high`), inverted range false.
- Converted values: ToDecimal feeds `<`, ToDateTime feeds Between,
  ToDecimal('abc') -> null propagates.
- 28-sig-digit Decimal extremes compare correctly; trailing-zero equivalence.
- String lexicographic strict Unicode (`'Z' < 'a'` true).
- Code/Concept ordered comparisons -> null (spec defines Greater only for
  Integer/Long/Decimal/Quantity/Date/DateTime/Time/String; silent on others —
  conservative null is acceptable, logged INTENDED).
- `true > false` -> true (Boolean ordering unspecified in CQL §9.10;
  consistent with FHIRPath; logged INTENDED observation).
- Long comparisons (`9223372036854775807L > ...L`) correct; bare out-of-range
  Integer literal correctly rejected.
- Chains in where over retrieves, Coalesce/if arms, aggregates (Sum/count
  over filtered retrieves; count(null-predicate)=0) — E2E dual-path equal.
- Parser decimal literal >8 fraction digits rounds half-up (repo path; NOTE:
  stale site-packages copy still hard-rejects — env, not code).

## Issues
- QA-001 (MEDIUM, CONFIRMED): static bare-numeric vs Quantity comparisons
  drop units -> definite booleans where spec (implicit Integer/Decimal->Quantity
  unit-'1' promotion, Table 9-E) requires unit-aware compare -> null for
  incompatible units. `1 = 1 'm'`/`1 = 1 'g'` -> true, `1 < 2 'm'` -> true.
  Engine already yields null for explicit `1 '1' = 1 'm'` — inconsistent.
  Also invalidates the AGENTS.md `5 'mg' = 5 -> True` "unity conversion"
  doctrine rationale (no test pins it).
- QA-002 (MEDIUM, CONFIRMED): `1 ~ 1 'm'` / `1 !~ 1 'm'` raise
  BinderException (quantityCompare given raw INTEGER) on both paths; spec
  requires promotion then false/true.

## Fix direction
Promote static numeric literals to unit-'1' quantity literals in the mixed
branches of _operators.py (~6910-6949) and in _translate_equivalence_op;
route through quantity_compare/quantityCompare. Keep dynamic choice-value
disambiguation paths (O.value = 1 'm') untouched. Update AGENTS.md doctrine.
