# QA Handoff — SOF-VD-10 SKEPTIC (2026-08-23)

Chunk: SQL-on-FHIR v2 ViewDefinition cross-cutting validation sweep —
sql-name / sql-expressions / required fields / bindings / expectError runner /
strict-permissive boundary.

## Spec verified against
Canonical v2 SD fetched fresh from FHIR/sql-on-fhir-v2 releases ig/2.0.0
(`.temp/qa/sof_vd10_skeptic_2026_08_23/sd-vd-v2.json`):
- sql-name = `^[A-Za-z][A-Za-z0-9_]*$` on ViewDefinition.name (0..1),
  constant.name (1..1), column.name (1..1). NO length cap in the SD.
- sql-expressions = `(forEach | forEachOrNull).count() <= 1` (repeat absent
  from SD 2.0.0; our <=1-of-3 rule is the fixture-pinned superset).
- Required: resource 1..1, select 1..*, column.path 1..1, column.name 1..1,
  constant.name 1..1, constant.value[x] 1..1, where.path 1..1.
- ViewDefinition.profile carries NO constraint in 2.0.0 (canonical \S*).

## Probes (86 + 8 + 1 dual-engine assertions, all green after triage)
- sql-name edges on all three fields at parse boundary: leading digit,
  underscore, hyphen, dot, space, unicode, dollar, empty → typed ParseError;
  keyword names (`select`) and 65/300/1000-char names ACCEPTED (no SD cap).
- sql-expressions: all 2-of-3 and 3-of-3 combos rejected at root, depth-2,
  and inside unionAll branches; singles accepted; direct-dataclass combo
  rejected at generate (typed ValidationError).
- Required fields: every mandated field missing → typed rejection, including
  depth-3 nesting and unionAll branches (probe2 P2).
- resource binding: array/case/whitespace/unknown/empty/numeric/object/null
  all rejected; fhirVersion: non-array/bad codes/null/empty rejected
  (24-code two-segment binding intact per SOF-VD-01).
- profile: whitespace/empty/non-array/non-string rejected; `|` and `#`
  ACCEPTED — NOT A BUG (no 2.0.0 constraint, canonical regex \S*).
- expectError runner audit: 11/144 fixtures carry expectError;
  `assert_spec_error_is_raised` fails explicitly via pytest.fail if a view
  is accepted (asserted at generation AND execution tests); probe re-ran all
  11 independently — every one raises. Parse-level test tolerates either
  outcome by design (error may surface at generation) — acceptable.
- Strict/permissive boundary: `validate_where_conditions` permissive split
  intact (SOF-VD-09); permissive validator WARNS (never raises) for sql-name,
  empty column.path, iterator combos, mutated where; strict parse/from_dict/
  to_dict/generate all reject the same shapes.
- Dual-engine DuckDB execution: valid VD with keyword column names
  (`select`, `order`), constant-in-where, forEach → native and forced-Python
  fallback both return [('p1','Doe')] — parity.

## Findings
- 0 CRITICAL / 0 HIGH / 0 MEDIUM.
- QA-001 LOW INTENDED: plain ValueError (not typed ValidationError) at the
  direct-dataclass __post_init__ boundary; parser wraps all into typed
  ParseError; SQLOnFHIRError subclasses ValueError so catching is identical.
- QA-002 LOW INTENDED: profile canonical arrays accept `|`/`#` per 2.0.0 SD
  (no constraint) + canonical datatype rules.

## Gates
viewdef pytest 1227/1227; conformance 2832/2832 (ViewDef 144/144, FHIRPath
935/935, CQL 1706/1706, DQM 47/47). Binary md5s repo==site-packages:
cql c5b22d58310c1eb7bafa17ce7877f989, fhirpath 57d0634b6ee6eddee9fc06a1355bef5a.
