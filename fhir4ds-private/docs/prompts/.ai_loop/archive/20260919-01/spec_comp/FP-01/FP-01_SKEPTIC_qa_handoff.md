# QA Handoff — FP-01 SKEPTIC (Iteration 1, 2026-08-16)

## Chunk
FHIRPath §4.1 Literals: Boolean, String, Integer, Decimal, Date, Time, DateTime, Quantity (incl. time-valued quantities). Native C++ extension vs forced Python fallback compared on every probe (~200 cases total across probe1/probe2/follow-ups).

## Spec sources verified
- HL7/fhirpath N1 normative source (`spec/N1/index.adoc` at tag N1, fetched via GitHub API): §4.1.8 Quantity + Time-valued Quantities table, §6.1.1 Quantity Equality, §6.1.2 Equivalence, §6.2 Comparison, §6.7 Date/Time Arithmetic, §5.5.7 toQuantity calendar conversion factors.
- Current published spec text (hl7.org/fhirpath, main-branch source) for the year/month calendar-vs-UCUM "empty (not comparable)" semantics.
- Official R4 test fixtures `fhir4ds/fhirpath/duckdb/tests/compliance/r4/tests-fhir-r4.xml`: `7 days = 1 'wk'` → true; `@1973-12-25 + 1 'mo'` / `+ 1 'a'` marked `invalid="execution"`; `@1973-12-25 + 1 'd'` / `+ 1 'wk'` valid; `'1 'mo''.toQuantity() = 1 month` has NO expected output (unspecified).

## Probes
- `/mnt/d/fhir4ds/.temp/qa/fp01_skeptic_2026_08_16/probe1.py` (113 cases), `probe2.py` (51 cases), plus inline follow-ups (calendar conversion chain, quoted-keyword matrix, comparison matrix, core-engine isolation).

## Issues opened (7)
| ID | Sev | Summary |
|---|---|---|
| QA-001 | HIGH | Quoted calendar keyword literals (`1 'month'`) not canonicalized in Python: `1 'month' = 1 month` → False (native True, spec True); `1 'month' = 1 'mo'` / `1 'year' = 1 'a'` → True (native empty, spec empty) |
| QA-002 | HIGH | Quoted PLURAL calendar keywords rejected in date arithmetic (Python only): `@2015-02-04 + 2 'days'` error vs native `2015-02-06`; `@T14:34:28 + 30 'minutes'` error vs native `T15:04:28` |
| QA-003 | MEDIUM | Calendar conversion factors not applied to unanchored equality (both backends): `1 month = 30 days`, `1 year = 365 days` → false (spec factors: true). Recommend DEFERRED — needs coordinated cross-engine rework; C++ UCUM table shared with CQL |
| QA-004 | MEDIUM | Month/year-vs-days ordering comparisons: fallback empty, native true/false (8/8 divergent: `1 month > 30 days` etc.) |
| QA-005 | LOW | `-0.0` display: native `-0.0` vs Python `0.0` (equality unaffected) |
| QA-006 | LOW | `4 'year'` display form: native `4 year` vs Python `4 'year'` (same root cause as QA-001) |
| QA-007 | LOW | fhirpath_json quantity double precision: native 15 sig digits vs Python 16 (`3.141592653589793236 'mg'`) |

## Root-cause lead for FIX (QA-001/QA-002/QA-006 — one fix)
Canonicalize quoted calendar duration keywords (16 spellings: year/years/month/months/week/weeks/day/days/hour/hours/minute/minutes/second/seconds/millisecond/milliseconds) to the bare keyword form when constructing `FP_Quantity` from a quoted unit — mirroring the C++ lexer/parser which stores STRING units unquoted, and the spec §4.1.8 unit-representation table where `'year'` IS the calendar keyword. Touch points:
- `fhir4ds/fhirpath/engine/evaluators/__init__.py:quantity_literal` (stores `f"'{unit_text}'"`)
- `fhir4ds/fhirpath/engine/invocations/equality.py:74-79` (deep_equal strict-unit branch), `:19-20` (`_YEAR_MONTH_*_UNITS` sets)
- `fhir4ds/fhirpath/engine/nodes.py:212-243` (`_arithmetic_duration_units` missing quoted plurals)
- `fhir4ds/fhirpath/duckdb/udf.py` `_evaluate_literal_temporal_arithmetic` regex (verify still handles quoted-keyword units)

## Verified-clean surfaces (do NOT re-litigate)
- Bare calendar-vs-UCUM equality/equivalence/comparison matrix matches spec + official tests (`1 year = 1 'a'` empty, `1 second = 1 's'` true, `1 year ~ 1 'a'` true, `1 year > 1 'a'` empty, `7 days = 1 'wk'` true)
- Date/Time arithmetic unit acceptance matches official tests (`'d'`/`'wk'`/`'s'`/`'ms'` OK; `'a'`/`'mo'` execution-error)
- Integer range (2147483647/-2147483648 boundaries), Decimal `0.1+0.2=0.3`, string escapes incl. `\uXXXX`/surrogate pairs, Date/Time/DateTime lexical+calendar validation (leap years, `+14:01` offsets, `ZZ`, `T24`, week-dates, `@2015Z`), Time-literal timezone rejection (both, intended), quantity `.value`/`.code`/`.system`/`.unit` members, unit conversions (`1 'kg' = 1000 'g'`, `3 'm' = 300 'cm'`), case-sensitive UCUM (`5 'MG'` → empty)

## Reproducers
See issue `evidence` fields in `evolution.json`; core-engine repro isolates the Python path without DuckDB:
`python3 -c "from fhir4ds.fhirpath import evaluate; print(evaluate('{\"resourceType\":\"Patient\"}', \"1 'month' = 1 month\"))"` → `[False]` (expected `[True]`)

## Validation requirement
Conformance baseline 2822/2822 must hold after any fix (PROC_VALIDATION.md). Focused parity tests belong in `fhir4ds/fhirpath/duckdb/tests/integration/test_literal_parity.py`.
