# QA Handoff — CQL-06 EXPLORER (3rd personality launch)

Date: 2026-08-20. Personality: EXPLORER (boundary/combination probing).
Probes: `.temp/qa/cql06_explorer3_2026_08_20/probe{,2,3}.py` + inline isolates.

## What was probed (dual-path: forced-python vs native-extension; identical everywhere)

- ToString round-trip battery for every type (Integer/Long/Decimal/Boolean/Date/
  DateTime w/ offset+fraction/Time/Quantity UCUM+calendar/Ratio) then ConvertsToX
  of the rendered string — ALL true; ToQuantity(ToString(4 days)) = 4 days holds.
- ConvertsToDateTime at every precision (YYYY .. .fff) incl. offsets ±14:00
  boundary (+14:01/+15:00 correctly false), unpadded/invalid-calendar rejection,
  tz-without-time rejection. ConvertsToDate incl. datetime-string acceptance.
- ConvertsToTime precision ladder, 24:00/12:60 rejection, leading-T acceptance.
- Numeric strings: signs, leading zeros, whitespace, 32/64-bit range edges,
  '1e3'/'.5'/'5.' rejection. ConvertsToLong(2147483648L) true.
- ConvertsToBoolean full table incl. case sensitivity ('TRUE','T','Y' true —
  spec says case-insensitive) and 'falsetto'/2/2.0 false.
- ConvertQuantity calendar↔UCUM: 4 weeks→'d' = 28 'd'; year→'mo' = 12; year→'d'
  = 365.25; month→'d' = 30.4375 (UCUM Julian-year factors, consistent); mg→s
  null; CanConvertQuantity ≡ (ConvertQuantity not null) invariant held on all
  probes incl. null operands.
- ToQuantity(Ratio) overload: ToQuantity(ToRatio('1.0 'mg':2.0 'mg'')) =
  0.5 '1' — spec-correct (numerator ÷ denominator).
- Null propagation: all 12 operators return null for null argument (spec).
- case/if-then-else chaining: correct first-match and and-composition.
- Conversion checks in where-clauses over retrieves: correct via
  `ConvertsToInteger(O.value as String)` (returns exactly o1).
- e2e population SQL both backends: identical rows.

## Issues filed (see evolution.json)

- QA-001 HIGH — `.value` FHIR-to-System primitive accessor returns NULL on all
  FHIR primitives (birthDate.value, status.value, (O.value as FHIR.string).value).
  Breaks the canonical FHIRHelpers pattern and converts-checks on FHIR fields.
  Root cause: fhirpath path-literal chain-merge appends 'value' verbatim.
- QA-002 MEDIUM — ConvertsToDecimal('1.123456789') false while ToDecimal rounds
  to 1.12345679; _DECIMAL_STRING_RE {1,8} cap contradicts the To function.
- QA-003 MEDIUM — ConvertsToTime/ToTime accept timezone suffixes ('12:00:00Z',
  '+05:00'); CQL Time format hh:mm:ss.fff has no timezone.

## Known-deferred artifacts hit (NOT filed; prior doctrine)

- List-literal/define-alias list query sources (Count undercounts, Sum binder
  error) = CQL-05 QA-107 DEFERRED family.
- Unknown CQL function names (e.g. `iif(...)`, `foobarbaz(...)`) pass through to
  SQL verbatim and fail at execution; CQL's conditional is `if ... then ... else`
  (lowers correctly). Noted as observation, out of chunk.

## Spec verification

CQL 1.5 reference (cql.hl7.org/09-b-cqlreference.html) fetched and paraphrased
into expectations BEFORE judging: ConvertsTo truth clause, ToBoolean string
table (case-insensitive t/f/yes/no/y/n/1/0), ToInteger/ToDecimal formats
((+|-)?#0 / (+|-)?#0(.0#)?), ToDate/ToDateTime/ToTime formats (offset only on
DateTime), ToQuantity unit clause (UCUM or calendar keyword, case-sensitive
UCUM), ToRatio colon separator, ConvertQuantity/CanConvertQuantity UCUM
semantics + null behavior, ToString round-trip clause.
