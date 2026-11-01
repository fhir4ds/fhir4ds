# Engineer Handoff — FP-08 EXPLORER remediation (iteration 1, 2026-08-17)

## QA-001 (HIGH) — fallback direct-key unit conversions
**Root cause**: `FP_Quantity.conv_unit_to`
(`fhir4ds/fhirpath/engine/nodes.py`) only reached base reduction when
`_unit_reduces_to_base(fromUnit)` was true; that helper deliberately
returns False for direct `_ucum_base_conversion_factor` keys, so derived
families (J/kJ, N/kN, W/kW, V/mV), exponent keys (m2/cm2), and
direct→expression pairs never converted.

**Fix**: new direct-key base-bridge branch in `conv_unit_to` — when the
from-unit is a direct key and the to-unit is a key or reducible
expression, reduce both through `conv_unit_to_base`, convert on matching
base units, EXCLUDING base unit `'s'` so the calendar-vs-UCUM doctrines
(§5.5.7 category table, §6.1.1 fixture pins: `1 year -> 's'` empty,
`1 'month' = 1 'mo'` empty) and offset-temperature rejection remain.
Rendering via `_divide_and_render` (28-sig-digit Decimal, trailing-zero
trim for exact quotients).

## QA-002 (MEDIUM) — native metric conversion precision
**Root cause**: native `convertQuantityUnit`
(`extensions/fhirpath/src/fhirpath/evaluator.cpp`) used
`exactDecimalRatioText` only for the duration table; the metric base path
kept the binary64 15-sig-digit shortest-round-trip mask.

**Fix**: added `decimalFactorRatio()` (converts a plain-decimal conversion
factor to an exact integer num/den, with integral-factor and length
guards) and an exact rendering branch in the metric path routing through
`exactDecimalRatioText` (§4.1.4: 28 significant digits ROUND_HALF_EVEN);
guards fall back to the previous binary64 path for exotic inputs (e.g.
scientific-notation value text). Shared `ucum_units.hpp` untouched — CQL
extension not rebuilt, CQL conformance 1706/1706 held.

## Deployment
`make fhirpath_loadable_extension` rebuilt; `fhirpath.duckdb_extension`
copied to repo bundle (`fhir4ds/fhirpath/duckdb/extensions/`),
`~/.local/lib/python3.10/site-packages/...`, and both
`~/.duckdb/extensions/{v1.5.2,v1.3.0}/...` caches.

## Validation
- Reproducer probe: 95/95 pass (was 83/12), zero parity diffs.
- Regression: 2 new tests in
  `fhir4ds/fhirpath/duckdb/tests/integration/test_fp08_spec_quantity_time_parity.py`
  (`test_toquantity_derived_and_direct_key_base_bridge_fp08_explorer`,
  `test_toquantity_metric_conversion_28_digit_decimal_parity_fp08_explorer`);
  full file 7 passed; `test_conversion_parity.py` 39 passed.
- Full fhirpath tree: 1745 passed, 0 failed.
- Full conformance: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).
  Baseline held — no regression.

QA-003 (LOW) classified INTENDED — shared both-engine convention, no fix.
