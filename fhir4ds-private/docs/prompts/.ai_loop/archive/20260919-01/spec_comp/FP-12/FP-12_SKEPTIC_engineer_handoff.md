# Engineer Handoff — FP-12, iteration 1 (2026-08-17)

## QA-001 (HIGH, PARITY) — RESOLVED

- Root cause: `fhir4ds/fhirpath/engine/util.py::parse_value` returned
  `parse_complex_value(...)`'s `None` sentinel directly for (a) ResourceNodes
  whose type info is `Quantity` and (b) Quantity-shaped dicts, whenever the
  data lacked a usable `unit`/`code`. `equality()` then unwrapped both
  operands to `None` and returned `None == None → True`, so distinct
  unitless Quantity wrappers (e.g. `{"value":120}` vs `{"value":80}` reached
  via `children()`/`descendants()`) compared equal — diverging from the
  native engine and violating §5.8.2 (`descendants()` ≡ `repeat(children())`
  requires `=` to distinguish them) and §6.1.1.
- Fix (surgical, general): both branches now fall through to the original
  value when `parse_complex_value` returns None. Python-only; the native
  path was already correct, so no extension rebuild.
- Validation: probe 57/57 parity (0 diffs); `repeat(children()).count()`
  now equals `descendants().count()` (6 = 6 on the minimal repro; 15 = 15 on
  the NESTED probe case); full fhirpath pytest tree 1809 passed; tree
  utility parity file 18 passed; conformance **2832/2832** (ViewDef 144,
  FHIRPath 935, CQL 1706, DQM 47) — baseline held.

## QA-002 (MEDIUM, API_GAP) — RESOLVED

- Added `fhir4ds/fhirpath/duckdb/functions/navigation.py` (new module):
  - `children(data)` — §5.8.1: key-order child values, arrays flattened in
    order, null children preserved, `resourceType`/`_`-props skipped,
    primitives → empty, unsupported types raise `FHIRPathError`.
  - `descendants(data)` — §5.8.2: iterative `repeat(children())` semantics
    with `=`-dedup; `_equals` compares numerics via Decimal (1 = 1.0) and
    delegates Quantity-shaped dicts to engine `FP_Quantity` unit-aware
    equality.
  - `trace(value, name[, projection])` — §5.9.1: logs via `logging`,
    returns input unchanged, requires a non-empty string name.
  - Exported from `functions/__init__.py` with `NAVIGATION_FUNCTIONS`
    registry (8th instance of the "exported helper API forgotten" family).
- Validation: `TestTreeNavigationHelpersFp12Skeptic` (9 cases) in
  `fhir4ds/fhirpath/duckdb/tests/unit/test_navigation.py` — 36/36 passed.

## Files changed

- `fhir4ds/fhirpath/engine/util.py` (QA-001 fix + comment)
- `fhir4ds/fhirpath/duckdb/functions/navigation.py` (new)
- `fhir4ds/fhirpath/duckdb/functions/__init__.py` (exports)
- `fhir4ds/fhirpath/duckdb/tests/unit/test_navigation.py` (helper tests)
- `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py`
  (QA-001 parity regression)

No regressions found during fix verification; no new issues logged.
