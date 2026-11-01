# Engineer Handoff - FP-13 HISTORIAN

## Scope

Remediated the fresh HISTORIAN FP-13 findings for FHIRPath §6.1 equality and
equivalence. The fixes were based on the current `evolution.json`, current
source tree, and a fresh probe only.

## Issues

### QA-001 - MEDIUM - VERIFIED

Root cause:
- Python fallback and native equality paths treated numeric primitives and
  Quantity values as incompatible unless both sides were already quantities.
- Native multi-item equality/equivalence and complex JSON helpers had separate
  comparison paths that also missed the implicit numeric-to-Quantity unit `1`
  rule.

Resolution:
- Added numeric-to-Quantity unit `1` coercion for §6.1 equality/equivalence in
  Python fallback and native C++.
- Routed native singleton, multi-item, collection helper, and complex JSON
  equality/equivalence through Quantity-aware comparison states.
- Added resource-backed UCUM code `1` coverage for singleton and multi-item
  comparisons.

### QA-002 - MEDIUM - VERIFIED

Root cause:
- Quantity equivalence returned boolean false/true for failed unit conversion
  instead of empty/NULL.
- A follow-up full-conformance run exposed fallback drift: `_quantity_base()`
  had a stale local conversion table missing `[lb_av]`, so the official R4
  `Observation.value !~ 185 'kg'` mass-unit sentinel returned empty.

Resolution:
- Changed Quantity equivalence to propagate empty/NULL for truly
  non-commensurable units such as `cm` versus `s`.
- Routed fallback `_quantity_base()` through the canonical
  `FP_Quantity.conv_unit_to_base()` table so supported UCUM conversions such as
  `[lb_av]` and `kg` remain commensurable.
- Added native/fallback parity coverage and native sqllogictest coverage for
  the R4 pound-vs-kg sentinel.

## Key Files Changed

- `fhir4ds/fhirpath/engine/invocations/equality.py`
- `extensions/fhirpath/src/fhirpath/evaluator.cpp`
- `fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py`
- `extensions/fhirpath/test/sql/fhirpath.test`
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension`
- `fhir4ds/fhirpath/AGENTS.md`
- `extensions/fhirpath/AGENTS.md`
- `.temp/qa/fp13_historian_fresh_probe.py`
- `fhir4ds-private/docs/prompts/.ai_loop/state/deep_research_findings.md`

## Validation

```bash
python3 .temp/qa/fp13_historian_fresh_probe.py
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_equality_parity.py -q
python3 -m pytest fhir4ds/fhirpath/tests/unit/test_conformance_regressions.py -q
cmake --build extensions/fhirpath/build/release --config Release -j 8
cp extensions/fhirpath/build/release/extension/fhirpath/fhirpath.duckdb_extension fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension
extensions/fhirpath/build/release/test/unittest "*fhirpath*"
python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_collection_operator_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q
python3 conformance/scripts/run_fhirpath_r4.py
python3 conformance/scripts/run_all.py | grep -E "FAIL|ERROR|accuracy|Suite|OVERALL|ViewDefinition|FHIRPath|CQL|DQM"
```

Final full conformance result:
- ViewDefinition: 134/134
- FHIRPath (R4): 935/935
- CQL: 1706/1706
- DQM (QI Core 2025): 47/47
- Overall: 2822/2822
