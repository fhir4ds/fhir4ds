# Engineer Handoff - FP-13 SKEPTIC

## Issues Resolved

### QA-001 - String equivalence whitespace/case normalization

Root cause:
Python fallback used split/join normalization, which collapsed repeated
whitespace and trimmed leading/trailing whitespace. Native C++ used byte-level
ASCII whitespace and case handling, so Unicode White_Space and non-ASCII case
pairs drifted from fallback.

Fix:
Fallback now maps each Unicode whitespace code point to one ASCII space without
collapsing or trimming, and uses Unicode casefolding. Native now decodes UTF-8
code points, maps Unicode White_Space code points one-for-one to ASCII space,
and applies Unicode case mapping.

Coverage:
Added native/fallback parity cases for repeated whitespace, leading whitespace,
tab-vs-space, NBSP-vs-space, and non-ASCII case equivalence.

### QA-002 - Quantity equality calendar-vs-UCUM duration rules

Root cause:
Both backends had a stale blanket mixed calendar-vs-UCUM duration guard for
units above seconds. That made definite week/day/hour/minute conversions false
and made calendar year/month versus UCUM year/month false instead of empty.
Fallback base conversion also missed some calendar duration keywords and
UCUM year/month conversion needed for same-kind Quantity equality.

Fix:
Mixed calendar-vs-UCUM equality is now indeterminate only for year/month
duration pairs. Week/day/hour/minute/second/millisecond quantities use normal
base conversion. Fallback duration base conversion now covers UCUM year/month
and calendar time-valued keywords. The native extension was rebuilt and copied
to `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`.

Coverage:
Added parity/native cases for `1 year = 1 'a'`, `1 month = 1 'mo'`,
`1 year ~ 1 'a'`, `1 year = 12 months`, `1 'a' = 12 'mo'`,
`1 week = 1 'wk'`, `7 days = 1 'wk'`, `1 hour = 60 'min'`, and
`1 minute = 60 's'`.

## Files Changed

- `fhir4ds/fhirpath/engine/invocations/equality.py`
- `fhir4ds/fhirpath/engine/nodes.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `.temp/qa/fp13_skeptic_fresh_probe.py`

## Validation Run

```bash
python3 .temp/qa/fp13_skeptic_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Results:
Fresh probe passed 22 expressions. Equality parity passed 11 tests. Adjacent
collection/existence parity passed 24 tests. Native fhirpath sqllogic passed
942 assertions. Full conformance reported 2822/2822 passing, 100.0% overall.

## New Issues

None.
