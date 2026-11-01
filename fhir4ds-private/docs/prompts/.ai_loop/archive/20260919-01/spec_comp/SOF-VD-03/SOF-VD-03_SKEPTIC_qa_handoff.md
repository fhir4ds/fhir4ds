# QA Handoff — SOF-VD-03 (Select elements), iteration 1, personality SKEPTIC

## Spec anchors verified (local IG clone /mnt/d/sql-on-fhir-v2, input/fsh/models.fsh + pagecontent/StructureDefinition-ViewDefinition-notes.md)
- select 1..*, column 0..*, column.path 1..1, column.name 1..1 obeys sql-name `^[A-Za-z][A-Za-z0-9_]*$`, description 0..1 markdown.
- Multiple sibling selects are CROSS JOINED (notes "Multiple Select Expressions"), not unioned.
- Column ordering: parent columns, then nested selects, unionAll last.
- unionAll branches MUST produce identical columns (count/names/order).
- collection=false + multiple values → implementations SHALL report an error.

## Probes executed (parser + generator + DuckDB execution, native extension path)
- Missing/empty select array, non-list select, non-object select item: all rejected. PASS
- Empty `column: []` array and bare `{}` select: accepted (model 0..* — spec-legal). PASS
- sql-name invariant: rejects `1abc`, `_x`, `a b`, `a-b`; accepts `select`/`order`/`group` (quoted identifiers in SQL, execute fine). PASS
- Duplicate names within select, across siblings, parent-vs-unionAll: rejected. PASS
- unionAll branch column mismatch (names/count): parse OK, generation raises with precise branch diff (acceptable error-report point). PASS
- Empty `unionAll: []` rejected. PASS
- forEach context: column inside forEach sees iterated element (postalCode/city correct). PASS
- Nested select without forEach inherits parent (root) context. PASS
- %resource / %rootResource inside nested select under forEach resolve to the root resource. PASS
- Sibling selects cross join: two sibling forEach selects produced 2x2 cross product. PASS (matches spec; note: launch-prompt hypothesis "multiple selects = UNION" is WRONG per spec — siblings cross join)
- Column ordering parent(a,b) → nested(c,d) → unionAll(e): output `a,b,c,d,e`. PASS
- Multi-value without collection=true: runtime Invalid Input Error raised (spec SHALL satisfied). PASS
- collection=true returns list aggregation. PASS
- description survives to_dict() roundtrip verbatim; no DDL COMMENT emitted (spec does not require one). PASS
- Identifier collisions with internal helper names (resource, row_num, idx, value, parent_resource): all execute correctly. PASS

## Issues found (both LOW)
- QA-001: generation-time preflight warning text ("only the first will be used") contradicts the actual runtime behavior (error raised, not truncation). generator.py:1236.
- QA-002: runtime guard message conflates multi-value cardinality violation with missing column.type ("non-primitive outputs require column.type" fired for a multi-valued primitive). Error is raised — spec-compliant; message quality only. Test suite pins the fragment.

Zero CRITICAL/HIGH/MEDIUM issues found.
