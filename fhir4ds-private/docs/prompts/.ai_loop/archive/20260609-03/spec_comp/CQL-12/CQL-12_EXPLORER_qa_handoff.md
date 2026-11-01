# QA Handoff - CQL-12 EXPLORER

Scope: CQL string operators, EXPLORER personality. I used the current CQL
Reference string operator section and stressed query/list composition, dynamic
FHIR string paths, nested regex/string chains, typed nulls, Unicode indexing,
regex rejection, no-Python/native extension helpers, and string-derived
FHIRPath literal escaping.

Findings:

- `QA-001` HIGH: `Combine((from { 'A', null, Lower('B') } S return S), '|')`
  lowered to `CombineSep((SELECT S FROM ...), '|')`. DuckDB rejected the row
  subquery as an invalid list argument, but CQL `Combine` accepts
  `List<String>` sources and query expressions are list-producing values.
- `QA-002` HIGH: `Patient.ext(url)` embedded the CQL string argument directly
  into `extension.where(url='...')`. A URL containing an escaped quote and
  predicate text escaped the FHIRPath string literal and evaluated as
  `... or true ...`, returning `"true"` on a nonmatching resource.

Fresh probe:

- `.temp/qa/cql12_explorer_probe.py`

Initial repro evidence:

- Before remediation, the malicious `ext()` expression returned `('true',)` on
  a Patient with only safe extensions.
- Before remediation, the query-produced `Combine` probe raised DuckDB
  `Invalid LIST argument during lambda function binding`.

