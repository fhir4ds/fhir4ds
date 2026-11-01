# QA Handoff - FP-04 SKEPTIC

Scope: FHIRPath §5.2 Filtering and Projection (`where`, `select`, `repeat`, `ofType`).

Spec anchor: HL7 FHIRPath Normative Release §5 says expression parameters evaluate per input item and may use `$this`/`$index`; §5.2.1 requires `where()` criteria to be a single Boolean; §5.2.2 requires `select()` flattening; §5.2.3 requires `repeat()` to keep applying projection to newly found items; §5.2.4 requires `ofType()` to include subclasses.

Hypotheses tested:
- Criteria strictness for `where()` on non-Boolean and multi-item results.
- `$index` binding and scope restoration across `where()`, `select()`, and `repeat()`.
- `select()` flattening of multi-item projections.
- `repeat()` recursive queue behavior and deduplication.
- `ofType()` exact-type vs subtype behavior for FHIR resources.

Findings:
- `QA-001` (`MEDIUM`): `ofType(Resource)` and `ofType(DomainResource)` return empty for Patient/Observation resources in both Python core and native/fallback DuckDB paths. Expected: resources match their FHIR supertypes.
- `QA-002` (`MEDIUM`): Python fallback leaks `$index` after `where()`/`select()` and does not bind `$index` during `repeat()`. Native C++ binds/restores for the tested cases, creating backend divergence and fallback-only data corruption.

Evidence commands used:
- Ad hoc public DuckDB native vs forced fallback probes under `.temp/qa`, using `register_fhirpath()` with normal DuckDB and with `duckdb.__version__ = "0.0.0-forced-python-fallback"`.
- Direct Python core probe: `fhir4ds.fhirpath.evaluate(bundle, "entry.resource.ofType(Resource).id")`.

Recommended remediation:
- Python: restore previous `$index` after lambda-style macros and bind `$index` inside `repeat_macro`; change `of_type_fn` to use subtype-aware `TypeInfo.is_()`.
- C++: change `evalOfType()` to subtype-aware matching and add resource hierarchy checks for `Resource`/`DomainResource`.
- Add parity regression tests covering native and forced Python fallback surfaces.
