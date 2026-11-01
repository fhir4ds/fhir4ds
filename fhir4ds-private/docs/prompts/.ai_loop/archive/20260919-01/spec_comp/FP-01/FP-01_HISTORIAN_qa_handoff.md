# QA Handoff — FP-01 HISTORIAN (Iteration 1, 2026-08-16)

## Chunk
FHIRPath §4.1 Literals: Boolean, String, Integer, Decimal, Date, Time, DateTime,
Quantity (incl. time-valued quantities). Systematic section-by-section
spec-walkthrough with native C++ vs forced Python fallback comparison on every
case (313 cases across 4 probes).

## Spec sources verified (fetched this launch)
- HL7/fhirpath **N1** `spec/index.adoc` (tag N1 via GitHub): full §4.1 text,
  §5.5.1-§5.5.7 toString/toQuantity + calendar conversion factor table,
  §6.1.1 Quantity Equality, §6.1.2 Equivalence, §6.2 Comparison.
- HL7/fhirpath **master** (= published v3.0.0 page) `spec/index.adoc`: §4.1.8
  Time-valued Quantities includes NEW normative sentence absent from N1:
  "The table above defines the equality/equivalence relationship between
  calendar and definite duration quantities. For example, `1 year` is not
  equal to `1 'a'`, but it is equivalent to `1 'a'`."
- Official R4 fixtures `tests-fhir-r4.xml` (938 tests): literal group
  (testLiteral*), testQuantity5/6 (`7 days = 1 week` / `7 days = 1 'wk'`
  → true), `testStringQuantityDayLiteralToQuantity` (`'1 day'.toQuantity() =
  1 'd'` → true), testPlusDate* (anchored arithmetic incl. invalid="execution"
  `'mo'`/`'a'`), TestEscape analogues, unary-plus `+1 < +2`.
- Harness check: `conformance/scripts/run_fhirpath_r4.py` exercises the Python
  core engine (strict mode) only — the native C++ literal surface is covered
  exclusively by parity tests, which keeps cross-engine parity probing
  essential for this chunk.

## Probes
`/mnt/d/fhir4ds/.temp/qa/fp01_historian_2026_08_16/`
- `fhirpath_N1_spec.adoc`, `fhirpath_master_spec.adoc` (fetched sources)
- `probe1.py` — 131 cases §4.1.1-§4.1.7 + `{}`: 0 parity divergences.
- `probe2.py` — 134 cases §4.1.8 + §5.5.7 factors + §6.7 anchored arithmetic +
  collections + rendering: 0 parity divergences.
- `probe3.py` — value dumps for mixed pairs, toQuantity, month-end anchoring,
  toString, fhirpath_json precision.
- `probe4.py` — 25 lexical edges (empty/space/no-space units, integer overflow
  promotion, Date-vs-DateTime equality, cross-type equality, range extremes):
  0 parity divergences.

## SKEPTIC-launch fix re-verification (all spec-correct, regression-free)
- Quoted calendar keyword canonicalization (QA-001/002/006): 16/16 spellings
  equal their bare form; `4 'year'` displays `4 year`; quoted plurals work in
  anchored date/time arithmetic (`@2015-02-04 + 2 'days'` → `2015-02-06`,
  `@T14:34:28 + 30 'minutes'` → correct value).
- §5.5.7 factors (QA-003/004): all 6 table rows verified INCLUDING the three
  rows SKEPTIC had not probed: `1 day = 24 hours` → true, `1 hour = 60
  minutes` → true, `1 minute = 60 seconds` → true, with full ordering boundary
  matrix (`1 day > 23 hours` true / `> 24 hours` false, etc.) — both engines.
- `-0.0` rendering (QA-005): `-0.0` → `0.0`, `-0.0 'mg'.value` → `0.0`,
  `-0.0 = 0.0` → true.
- `fhirpath_json` precision-15 (QA-007): `3.141592653589793236 'mg'` →
  `{"value":3.14159265358979,...}` in both engines; `0.1+0.2` → `0.3`.
- Conformance on the current tree: FHIRPath R4 **935/935**; focused
  `test_literal_parity.py` **31/31**.

## New issues opened (2)
| ID | Sev | Summary |
|---|---|---|
| QA-001 | MEDIUM | Mixed calendar-vs-UCUM pairs in the year/month group (`1 year = 1 'a'`, `1 month = 1 'mo'`, `1 year = 12 'mo'`, quoted variants) return **empty**; N1 §6.1.1 + master §4.1.8/§6.1.1 require **false** ("considered unequal"; "1 year is not equal to 1 'a'"). `!=` should be true, currently empty. Ordering correctly stays empty (§6.2); equivalence correctly true. |
| QA-002 | LOW | Time-literal + time-valued-quantity arithmetic results render with leading `T` (`(@T14:34:28 + 30 'minutes').toString()` → `T15:04:28`), violating the toString() Time representation `hh:mm:ss.fff` and our own literal rendering (`(@T14:34:28).toString()` → `14:34:28`). Both engines. |

## Verified-clean surfaces (do NOT re-litigate)
- Non-quantity literals (§4.1.1-§4.1.7): 131 cases incl. all escapes + the five
  spec TestEscape examples, surrogate pairs, exponential-notation rejection,
  `1.`/`.5` rejection, unary plus/minus binding, integer range boundaries,
  decimal trailing-zero equality, Date leap-year/zero-pad/range validation,
  week-date/ordinal rejection, Time range and timezone rejection, DateTime
  T-suffix partials (all 3 forms per spec examples), offset forms (`+09`,
  `+0900`, `+09:0`, `+09:60`, `+14:01`, lowercase `z`, `ZZ` all rejected),
  offset-normalized equality (`Z` = `+00:00` = `-00:00`), precision-aware
  equality (`.0` vs plain seconds), Date-vs-DateTime/cross-type equality →
  empty, `{} = {}` → empty (§6.1.1).
- Mixed exact pairs stay fixture-aligned TRUE: `1 week = 1 'wk'`, `1 day =
  1 'd'`, `1 hour = 1 'h'`, `1 minute = 1 'min'` (official testQuantity6 +
  `'1 day'.toQuantity() = 1 'd'` mandate this despite N1 §6.1.1 prose).
- UCUM-vs-calendar cross-group guards: `1 'a' = 365 days` → false,
  `1 'mo' = 29 days` → false, `1 'mo' > 29 days` → empty, `1 'a' > 364 days`
  → empty (§6.2), `1 'a' = 12 'mo'` → true (UCUM mean-month arithmetic).
- toQuantity: `(1 year).toQuantity('month')` → `12 month` (quoted arg equal);
  `(1 day).toQuantity('hours')` → `24 hours`.
- Collections: `(1 'year' | 1 year | 12 months).count()` → 1;
  `(1 day | 24 hours).count()` → 1; `(1 week | 7 days).count()` → 1;
  `(1 'month' | 1 'mo').count()` → 2.
- Month-end anchoring clamps correctly (`@2015-01-31 + 1 'month'` →
  `2015-02-28`; leap → `2016-02-29`); fixture invalid anchored UCUM
  (`'mo'`/`'a'`) rejected in both engines.
- Invalid/opaque units (`5 'xyzzy'`, `1 'fortnight'`, `1 'Year'`) are valid
  literals kept verbatim (comparisons on them → empty per §6.1.1);
  `5 ''` invalid; `4e2 'mg'` invalid (exponential).

## Validation requirement
Baseline 2832/2832 per PROC_VALIDATION.md must hold after any fix; FHIRPath
935/935 verified pre-fix this launch. Focused parity tests belong in
`fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py`. Native
changes require rebuilding + copying the bundled `fhirpath.duckdb_extension`.
