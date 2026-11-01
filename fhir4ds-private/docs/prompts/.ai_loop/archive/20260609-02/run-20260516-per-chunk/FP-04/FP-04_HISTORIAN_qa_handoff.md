# QA Handoff - FP-04 HISTORIAN

Scope: FHIRPath §5.2 filtering/projection: where(criteria), select(projection), repeat(projection), ofType(type).

Spec basis: FHIRPath Normative Release §5.2.1 requires where criteria to be a single Boolean; §5.2.2 requires select to flatten projection collections; §5.2.3 requires repeat to add projection results only while they are new as determined by `=`; §5.2.4 requires ofType to include the requested type and subclasses.

Probed native DuckDB extension and Python fallback using synthetic Questionnaire, Bundle, duplicate-child, and literal-sequence cases. where/select/ofType matched expected behavior in the covered cases.

Findings:
- FP04-HISTORIAN-001: Python fallback repeat() does not de-duplicate duplicates produced within the same projection evaluation. Reproducer: `item.repeat(item).linkId` over one item with two identical child `item` objects returns `["same", "same"]`; expected one result.
- FP04-HISTORIAN-002: Native C++ repeat() incorrectly pre-seeds the seen set with input and includes numeric/temporal input seeds via a special heuristic. Reproducers: `'a'.repeat($this)` returns empty native but `['a']` fallback; `1.repeat(iif($this < 3, $this + 1, {}))` returns `[1,2,3]` native but expected `[2,3]`.

Suggested regression coverage: extend `fhir4ds/fhirpath/duckdb/tests/integration/test_filter_projection_parity.py` to compare native and forced fallback for repeat self-projection, duplicate child objects, and bounded numeric projection.
