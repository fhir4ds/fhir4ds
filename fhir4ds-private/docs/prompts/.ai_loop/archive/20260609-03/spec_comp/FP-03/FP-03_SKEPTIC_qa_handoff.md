# QA Handoff - FP-03 SKEPTIC

## Scope

- Chunk: FP-03, FHIRPath Section 5.1 Existence.
- Personality: SKEPTIC.
- Functions probed: `empty()`, `exists([criteria])`, `all(criteria)`, `allTrue()`, `anyTrue()`, `allFalse()`, `anyFalse()`, `subsetOf(other)`, `supersetOf(other)`, `count()`, `distinct()`, `isDistinct()`.
- Spec source: HL7 FHIRPath Normative Release, Section 5.1, https://hl7.org/fhirpath/N1/

## Spec Grounding

Section 5.1 defines existence functions over collections. The key rules used for expectations were:

- `empty()` is true only for an empty input collection; `exists()` is its opposite and `exists(criteria)` is equivalent to `where(criteria).exists()`.
- Expression parameters are evaluated per item and may refer to `$this` and `$index`.
- `all(criteria)` is vacuously true for empty input and false when any item criterion is not true.
- Boolean aggregate functions operate on Boolean collections with empty defaults: `allTrue()` and `allFalse()` true; `anyTrue()` and `anyFalse()` false.
- `subsetOf()`, `supersetOf()`, `distinct()`, and `isDistinct()` use FHIRPath `=` semantics for item comparison.
- `count()` returns an Integer count and returns `0` for empty input.

## SKEPTIC Hypotheses

1. Native `exists(criteria)` or `all(criteria)` might expose `$this` but forget `$index`.
2. Early-return paths in `exists(criteria)` or `all(criteria)` might leak `$index` into the outer chain.
3. Criteria functions might treat strings, numbers, or multi-item results as truthy instead of requiring a single Boolean.
4. Boolean aggregates might short-circuit before validating every item is Boolean.
5. Empty-input defaults for `all`, `allTrue`, `anyTrue`, `allFalse`, `anyFalse`, `subsetOf`, or `supersetOf` might drift between native and fallback.
6. Set-style existence functions might compare with host-language equality instead of FHIRPath `=`, especially for `1` vs `1.0`, compatible quantities, and structural JSON.
7. FHIR Quantity path values might not be materialized before `distinct()` or `subsetOf()` equality checks.
8. Public DuckDB typed wrappers might hide a native/fallback semantic mismatch, so probes compared `fhirpath`, `fhirpath_json`, `fhirpath_bool`, `fhirpath_number`, and `fhirpath_text`.

## Probe Results

- Created `.temp/qa/fp03_skeptic_existence_probe.py`.
- Ran 35 targeted native-vs-forced-fallback cases.
- Result: `failure_count=0`.
- Focused pytest: `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_existence_parity.py -q` -> `9 passed`.
- Full conformance summary: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.

## Issues

No CRITICAL/HIGH/MEDIUM/LOW issues were found. `evolution.json.issues` remains empty.

## Notes For Remediation

No source remediation is required. The required FIX handoff should explicitly record a no-op pass and preserve the clean state.
