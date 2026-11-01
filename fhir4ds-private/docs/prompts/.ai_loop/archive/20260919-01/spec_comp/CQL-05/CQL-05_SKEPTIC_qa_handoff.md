# QA Handoff — CQL-05 Structural Type Operators (SKEPTIC, iteration 1)

## Scope probed
CQL 1.5 As<T>, Children, Convert to<T>, Descendants, Is<T> — via parse, translation, and DuckDB
execution (registered native C++ path and forced-Python fallback path, parity compared), over
literals, tuples, and retrieved FHIR resources in population SQL.

## Spec verification (cql.hl7.org/09-b-cqlreference.html)
- As: runtime type check; null on mismatch; `cast as` raises. Confirmed OK in existing+new probes
  (`5 as Decimal` → null is spec-correct: As is not a conversion).
- Is: `null is T` → false ✓; subtype rule ✓.
- Children/Descendants: recursive element traversal, list flattening, null input → null ✓
  (`Children(null)` → null verified). Children of homogeneous list → [] ✓.
- Convert: null when no conversion exists ✓ (Interval/List → String null is spec-consistent).

## Verified-good surfaces (py/cpp parity held on every probe)
null semantics, System./FHIR.-qualified specifiers, Quantity As/Is (System+FHIR), convert-to-String
for Boolean/Integer/Decimal/Date/DateTime/Time/Long/Quantity/Ratio, convert to Quantity/Concept/Ratio,
Is/As on choice types over retrieves (value[x]), Is on resource types from retrieves (`First([Observation])
is Observation` → True — but see QA-001 for the `as`/bare-First execution gap).

## Issues opened
- QA-001 (HIGH): First/Last/`singleton from` over bare retrieves generate invalid SQL
  (LIST_EXTRACT("Observation",1) with no FROM). Breaks `First([Observation]) as Observation` end-to-end.
- QA-002 (HIGH): where-clause alias over Children()/Descendants() binds the whole list, not items:
  `D is Quantity` → ltrim(VARCHAR[]) binder error over retrieves; wrong False over literals.
- QA-003 (MEDIUM): `O.status is String` / `O.id is FHIR.string` → False; FHIRPath type().name reports
  'code' and the is-check lacks a FHIR string-family → System.String mapping.
- QA-004 (MEDIUM): `exists ({1, 2} N where N is Integer)` → binder error, alias N unbound.

## Notes for FIX
- Model knowledge must stay data-driven: string-family mapping should come from FHIR schema metadata
  (fhir_schema.py type info), not a hardcoded clinical list.
- Reproducer scripts live in /mnt/d/fhir4ds/.temp/qa/probe*.py.
- Existing suite fhir4ds/cql/duckdb/tests/integration/test_structural_type_parity.py (14 tests) passes
  on both paths — extend rather than replace.
