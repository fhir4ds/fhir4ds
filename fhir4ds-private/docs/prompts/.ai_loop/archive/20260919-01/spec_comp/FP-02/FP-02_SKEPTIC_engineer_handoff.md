# Engineer Handoff — FP-02 SKEPTIC iteration 1 (2026-08-16)

## Triage
| ID | Severity | Category | Disposition |
|---|---|---|---|
| QA-003 | HIGH | SPEC_VIOLATION (§6.6.1/§6.6.2) | RESOLVED (both engines, native rebuilt) |
| QA-001 | MEDIUM | SPEC_VIOLATION (§6.8 precedence) | RESOLVED (fallback validity precheck) |
| QA-004 | MEDIUM | SPEC_VIOLATION (§6.2 ordering parity) | RESOLVED (found during fix verification) |
| QA-002 | LOW | SPEC_VIOLATION (is_valid doctrine) | RESOLVED (Python + native classification) |

## Fixes (all spec-grounded, minimal footprint)

### QA-003 — quantity unit exponent algebra (HIGH)
- Python `fhir4ds/fhirpath/engine/nodes.py`: new `_parse_unit_exponents` /
  `_render_unit_exponents` / `_unit_reduces_to_base`; `conv_unit_to_base`
  converts multi-term/exponent UCUM expressions term-by-term with exponent
  merging; `conv_unit_to` gained a base-reduction bridge; `__mul__` /
  `__truediv__` / `__rtruediv__` compose units by merged exponents
  (m.m2 → m3, m2/m → m, dimensionless stays '1' instead of '12').
- `fhir4ds/fhirpath/engine/invocations/equality.py::_quantity_base` accepts
  reducing units.
- Native `extensions/fhirpath/src/fhirpath/evaluator.cpp`:
  `fhirpathSplitUnitTerm` / `fhirpathParseUnitExponents` /
  `fhirpathRenderUnitExponents` / `fhirpathComposeQuantityUnits`;
  `convertQuantityToBase` multi-term fallback (offset-temperature sentinel
  factors excluded); the `*`, `/`, and number/`1/x` composition sites use
  merged exponents. Render sorts symbols alphabetically — Python and C++
  emit byte-identical spellings ('g.m', '1/s', 's/g', 'm3').
- Extension rebuilt and redeployed to
  `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` and the
  user site-packages copy. Shared `ucum_units.hpp` untouched (CQL extension
  not rebuilt; CQL conformance 1706/1706 held).
- Spec examples now pass in both engines: `12 'cm2' / 3 'cm'` → `0.04 'm'`
  with `= 4 'cm'` true; `3 'cm' * 12 'cm2'` → `0.000036 'm3'` with
  `= 36 'cm3'` true; `1 'm2/m' = 1 'm'` / `<` / `~` work;
  `1 'm2/cm2' = 10000` (dimensionless reduction) works.

### QA-001 — §6.8 union/arithmetic precedence in fallback validity
- `fhir4ds/fhirpath/duckdb/udf.py`: new `_split_top_level_pipe_segments`;
  `_has_invalid_math_literal_operands` splits top-level `|` segments first
  and recurses per segment. Valid mixes (`1 + 2 | 3` → `(1+2)|3`) now
  is_valid=True in the fallback, matching the native extension; true
  positives (`(1 | 2) + 3`, `1 + (2 | 3)`, `1 < 2 | 3`) stay invalid.

### QA-004 — quantity ordering base-table parity (found during verification)
- `nodes.py FP_Quantity.compare()`: when `conv_unit_to` (special groups)
  fails, fall back to `conv_unit_to_base` comparison — the same
  comparability the equality path uses. `1 'mm[Hg]' < 200 'Pa'` now true in
  the fallback (was empty; native already true — pre-existing divergence).
  Offset temperatures (Cel vs K), unknown units, and calendar-vs-UCUM pairs
  still return empty.

### QA-002 — unary type-error validity classification
- Python `_is_valid_empty_result_error` + native `FhirpathIsValidFunction`
  accept unary non-numeric type errors as execution errors (valid per the
  GLOBAL_RULES is_valid doctrine). Singleton violations stay invalid.
- One stale pin updated with justification:
  `test_conversion_parity.py` FP-06 case `-1.convertsToInteger()` is_valid
  False → True. Official fixtures mark BOTH unary testPrecedence1 and
  binary testMinus4 `invalid="execution"`; the strict core still errors
  (conformance unaffected), and the binary twin `'a' - 'b'` was already
  classified valid — the old pin contradicted the doctrine.

## Regression tests added
- `test_arithmetic_parity.py`:
  `test_quantity_unit_exponent_merge_both_backends_fp02_skeptic` (9 cases),
  `test_quantity_unit_reduction_comparisons_both_backends_fp02_skeptic`
  (22 cases), updated `m.m2` → `m3` pin.
- `test_operator_parity.py`:
  `test_union_precedence_validity_matches_native_fp02_skeptic` (15 cases),
  `test_unary_type_error_validity_classification_fp02_skeptic` (4 cases).
- `test_comparison_parity.py`:
  `test_quantity_ordering_base_table_parity_fp02_skeptic` (11 cases) +
  pytest import.

## Validation (Recovery Gate)
- Focused parity: operator/arithmetic/boolean/comparison/equality/collection
  307 passed; comparison+conversion 65 passed (post QA-004/QA-002-pin fixes).
- Full conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held (run pre-dated the QA-004 edit; a final re-run is
  scheduled by the orchestrator).
- fhirpath package pytest: 1608 passed pre-QA-004 (1 failure found was the
  stale FP-06 pin, since updated); full re-run in flight.
- Probes: 0 native↔fallback divergences across all QA-003/QA-004 verification
  batteries.

## New issues discovered
- QA-004 (see above; discovered during QA-003 verification, resolved same
  iteration).
