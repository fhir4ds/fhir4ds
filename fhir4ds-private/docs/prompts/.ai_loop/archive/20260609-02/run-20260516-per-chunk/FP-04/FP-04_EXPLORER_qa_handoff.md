# QA Handoff - FP-04 EXPLORER

Scope: FHIRPath N1 section 5.2 filtering/projection: `where(criteria)`, `select(projection)`, `repeat(projection)`, and `ofType(type)`.

Spec anchor:
- Section 5.2 expression parameters evaluate once per input item with `$this` and `$index`.
- `where()` includes only items whose criterion evaluates to a single Boolean `true`; false/empty are excluded, and non-singleton/non-Boolean criteria signal an error.
- `select()` flattens projection collections and omits empty results.
- `repeat()` emits projection results while they are new by FHIRPath `=` equality; the order is undefined and seeds are only work queue inputs.
- `ofType()` returns items of the requested type or subclass.

Exploration performed:
- Compared native C++ DuckDB UDFs and forced Python fallback in fresh processes for nested `where`, `select`, `repeat`, `$index`, duplicate projection results, and `ofType(Resource/DomainResource/Patient)`.
- Ran focused direct Python probes against `fhir4ds.fhirpath.duckdb.functions.filter` helper APIs.

Finding:
- QA-001 MEDIUM: exported DuckDB helper functions in `fhir4ds.fhirpath.duckdb.functions.filter` retain non-compliant semantics. `repeat()` returns seed inputs and de-duplicates by `repr`; `where()` accepts truthy non-singleton criteria instead of rejecting them; `of_type()` cannot match concrete FHIR resource names or `DomainResource` supertypes.

Native/fallback UDF status:
- Fresh-process native C++ and forced Python fallback agree for probed FP-04 UDF cases, including `repeat($this)`, duplicate child projection de-duplication, `$index` inside `repeat`, strict `where` wrapper resilience, and resource subtype `ofType()`.
