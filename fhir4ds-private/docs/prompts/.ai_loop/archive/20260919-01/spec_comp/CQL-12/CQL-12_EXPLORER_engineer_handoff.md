# Engineer Handoff — CQL-12 (EXPLORER), iteration 1

Triage:
- QA-001 MEDIUM SPEC_VIOLATION — CONFIRMED and FIXED.
- QA-002 HIGH SILENT_WRONG_RESULT — CONFIRMED and FIXED (root cause at the
  Indexer lowering seam; the deep modelinfo chained-typing debt remains as
  previously deferred, but the silent-wrong-result surface is closed).
- QA-003 LOW — INTENDED (typed CQLRegexPatternRejected for '$1' over a pattern
  with no capture groups; Java-consistent; documented in AGENTS.md).

QA-001 fix (root cause, no workarounds):
1. fhir4ds/cql/duckdb/udf/string.py — cqlRegexSplitOnMatches kept the raw
   Python re.split result, which interleaves capture-group values into the
   split list. CQL Appendix B SplitOnMatches has no group-inclusion clause and
   the reference engine (Java Pattern.split) plus the native extension exclude
   groups. Fix: keep only the separator-delimited segments (parts[::groups+1]).
2. Regression: test_string_operator_parity.py::
   test_cql_string_splitonmatches_excludes_capture_groups (single group,
   double group, no group; both engines).

QA-002 fix (root cause, no workarounds):
1. fhir4ds/cql/translator/expressions/_lists.py — _is_string_index_source
   classified fhirpath_text/fhirpath_scalar chains as String indexer sources,
   so chained navigation (Patient.name.given[0],
   First([Observation]).code.coding[0]) was character-indexed after the scalar
   collapse ('J', '{'). Per CQL 1.5 implicit property traversal these sources
   are element LISTS. Removed both names from the string-source set; the
   existing list path already rewrites fhirpath_text -> list-returning
   fhirpath UDF (extended the rewrite to fhirpath_scalar) + LIST_EXTRACT.
   Unchanged and still spec-correct: literal String indexing ('abc'[1]='b'),
   First()-scalar defines (define Fam: First([Patient]).name.family; Fam[3]='t'
   — First() demotes the chain to a scalar String), and RESOURCE_ROWS list
   indexing.
2. Regression: test_string_operator_parity.py::
   test_cql_string_indexer_over_fhirpath_chain_is_list_indexing — over loaded
   Patient/Observation resources on BOTH engines: given[0]='Joel',
   given[1]='Ray', given[5]=null, coding[0].code='8480-6' (previously '{' and
   None), 'abc'[1]='b'.

Validation (Recovery Gate):
- String parity suite: 11/11 passed (9 prior + 2 new; prior SKEPTIC
  scalar-string Indexer regression still green).
- Full conformance: fresh filtered run_all.py — see architect handoff /
  GLOBAL_KNOWLEDGE row for counts (must hold the PROC_VALIDATION baseline
  2832/2832).

No new issues discovered during remediation.
