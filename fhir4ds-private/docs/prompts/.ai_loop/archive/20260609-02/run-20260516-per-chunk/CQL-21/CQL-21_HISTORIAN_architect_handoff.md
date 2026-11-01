# Architect Handoff - CQL-21 HISTORIAN

Structural audit result: acceptable with one deferred raw-SQL API surface gap.
The supported CQL translator path is sound for CQL-21 clinical operators:
`Count(ExpandValueSet(Vitals))` is classified as list-returning and evaluates
correctly, while age helpers and clinical terminology operators remain covered
across forced Python fallback and native-loaded DuckDB registration.

Issue summary:
- `QA-001` MEDIUM is terminal as `DEFERRED`. Raw direct DuckDB
  `Count(ExpandValueSet(?))` returns `1` because `Count` is DuckDB's row
  aggregate. The engineer correctly avoided a macro/UDF shadow because it breaks
  `COUNT(DISTINCT ...)`, `FILTER`, window, and row aggregate syntax. This is a
  future API design item, not a remediation-safe clinical-operator fix.

QA audit:
- No retry needed. HISTORIAN covered non-happy-path age boundaries, null
  CodeSystem/ValueSet membership, Code equality versus equivalence, and
  ExpandValueSet direct/translated behavior. The failed direct `Count` probe was
  useful and the remediation classification is justified.

Validation:
- Focused clinical/type/no-Python runtime pytest: 16 passed.
- Full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, overall 2822/2822.

Recommended next step:
- No engineer retry for this run. If the project wants a direct public CQL
  list-count SQL surface, design it separately without shadowing DuckDB's
  aggregate `Count` name.
