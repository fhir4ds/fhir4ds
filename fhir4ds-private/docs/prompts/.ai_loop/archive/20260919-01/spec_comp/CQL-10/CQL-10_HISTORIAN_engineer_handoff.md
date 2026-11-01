# Engineer Handoff — CQL-10 HISTORIAN FIX, iteration 1 (2026-08-21)

Both QA issues resolved at root cause. Reproducers
`/mnt/d/fhir4ds/.temp/qa/cql10_historian/probe3.py` (QA-001) and `probe4.py`
(QA-002) now pass with byte-identical py↔cpp output.

**Harness trap (important)**: running probe scripts as `python3 .temp/...`
resolves `fhir4ds` from site-packages (script dir is sys.path[0], not cwd).
Validation MUST use `PYTHONPATH=/mnt/d/fhir4ds`. Earlier "still failing"
re-runs were testing the installed wheel, not the working tree.

## QA-001 (HIGH) — RESOLVED

Two-layer defect, both fixed:

1. **Translator site** (already staged by the interrupted session):
   `fhir4ds/cql/translator/expressions/_functions.py` High/LowBoundary
   branch now transports Integer/Long/Decimal boundary results through
   `TRY_CAST(CAST(... AS VARCHAR) AS DECIMAL(38, 8))` (previously
   `... AS DOUBLE`), preserving exact Decimal text and the
   fixture-mandated scale-8 rendering (`LowBoundaryDecimal` →
   `1.58700000`). The SKEPTIC fill-and-truncate UDF/macro semantics were
   NOT touched.
2. **Python UDF site** (true residual root cause):
   `fhir4ds/cql/duckdb/udf/math.py` `highBoundary`/`lowBoundary` returned
   `float(bounded)` for DECIMAL-typed inputs — a DOUBLE round-trip that
   corrupted >15-significant-digit values regardless of the translator
   cast. They now return the exact boundary text, matching the native
   extension's string-result contract (py↔cpp parity improved).
   `HighBoundary(123456789012345678901234.5, 8)` →
   `123456789012345678901234.59999999` on both engines.

## QA-002 (MEDIUM) — RESOLVED

The interrupted session had added `_ARITHMETIC_FN_STATIC_GUARDS` and its
call site but never defined the method (AttributeError on guarded paths).
Completed the fix:

- `fhir4ds/cql/translator/expressions/_functions.py`: implemented
  `_validate_static_arithmetic_operands` — rejects statically
  String/Boolean value operands for Abs/Ceiling/Floor/Exp/Ln/Log/
  High/LowBoundary, and non-Integer High/LowBoundary precision
  arguments, with a uniform typed `TranslationError`; null/Any/dynamic
  operands pass through to runtime null semantics.
- `fhir4ds/cql/translator/expressions/_operators.py`
  (`_translate_binary_entry` guard block): the numeric-only binary
  operators `/ ^ * -` now raise the same typed TranslationError for
  statically String/Boolean operands (Add already did via its string
  guard).

All 19 wrong-typed reproducer cases now raise typed TranslationError;
no silent nulls, no raw BinderException/ConversionException leaks.

## Tests

- `fhir4ds/cql/duckdb/tests/integration/test_arithmetic_operator_parity.py`:
  new `test_cql10_historian_exact_decimal_boundaries_and_typed_errors`
  (QA-001 exactness + scale-8 text + 19-case QA-002 typed-error matrix).
- Updated expectations in
  `test_cql_log_requires_base_and_boundary_default_precision` and
  `test_cql10_spec_compliance_boundaries_typing_and_promotion`:
  boundary/exp/log results are now exact `Decimal` (scale-8) instead of
  float — spec-correct improvement; `HighBoundary(-1.587,2)` renders
  `'-1.58'` (unary-minus operand takes the unwrapped boundary path on
  both engines — pre-existing shape, not regressed).

## Validation

- Arithmetic parity file: 9/9 pass.
- Full conformance gate (`conformance/scripts/run_all.py`): 2832/2832 —
  ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706, DQM 47/47;
  gate clear.

No new issues discovered.
