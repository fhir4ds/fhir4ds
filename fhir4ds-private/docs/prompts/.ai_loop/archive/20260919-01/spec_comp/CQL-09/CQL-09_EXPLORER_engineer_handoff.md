# Engineer Handoff — CQL-09 Comparison Operators (EXPLORER, iteration 1)

## Triage
QA-001 MEDIUM SPEC_VIOLATION CONFIRMED → RESOLVED.
QA-002 MEDIUM SPEC_VIOLATION CONFIRMED → RESOLVED.
QA-003 LOW SPEC_AMBIGUITY → DEFERRED (documented boundary).

## Fixes
File: `fhir4ds/cql/translator/expressions/_operators.py`
1. QA-001 (=, !=, <, <=, >, >=): in the two mixed quantity/non-quantity
   branches, a bare static numeric literal vs a STATIC Quantity literal is
   now promoted to a unit-'1' quantity (CQL 1.5 Table 9-E implicit
   Integer/Decimal→Quantity conversion; helper `_quantity_operand_for_arithmetic`)
   and routed through `quantity_compare`. Incompatible units now yield NULL
   (§9.5) instead of unit-dropped raw-value booleans.
2. QA-002 (~, !~): same promotion added in `_translate_equivalence_op`
   (restricted to static `parse_quantity` literals) — `1 ~ 1 'm'` now false
   (§9.7 never null) instead of a DuckDB BinderException; `1 !~ 1 'm'` true.
3. Scope narrowing (regression-driven): the promotion intentionally does NOT
   apply to dynamic FHIR-sourced quantities. First attempt applied it
   globally and regressed DQM 45/47 (CMS190 numerator, CMS72 denominator
   exception, one patient each). A/B SQL diff isolated the cause: CMS72
   `INR.value as Quantity > 3.5` where the fixture valueQuantity is
   `{"value":100,"unit":"0"}` (no `code`); FHIRHelpers maps unit
   Coalesce(code, unit, '1') → "0", and quantityCompare cannot convert
   "0"→'1' (null), while official fixtures pin numeric comparison. Dynamic
   path keeps `_dynamic_quantity_literal_comparison` / `quantity_value`
   numeric fallback; doctrine documented in fhir4ds/cql/AGENTS.md.

## Regression test
`test_comparison_operator_parity.py::test_cql_bare_numeric_vs_quantity_promotes_unit_aware`
(18 cases × py+cpp backends). Suite 15/15.

## Validation
- CMS190/CMS72 re-run: 100% each (targeted runner).
- Full conformance gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — baseline held.
- Dual-path probes re-verified: 25/25 mixed-literal cases OK, zero
  native-vs-Python divergence.

## Institutional memory
Updated `fhir4ds/cql/AGENTS.md`: corrected the `5 'mg' = 5 → True` doctrine
(now null, spec-grounded), pinned the CMS72/CMS190 dynamic-quantity numeric
doctrine, logged QA-003 deferred boundary.
