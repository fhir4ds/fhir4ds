# Architect Handoff — CQL-12 (EXPLORER), iteration 1

Scope: focused structural audit of this launch's diff (two fixes + two regression
tests) against the CQL translator invariants, plus drift re-assessment.

Golden-standard invariants applied (from GLOBAL_RULES + CQL AGENTS.md doctrine):
1. No silent fallbacks; typed failures over masked wrong results.
2. No SQLRaw/to_sql mid-pipeline; translator layering preserved.
3. Fixes must be class-level, never keyed to the exposing fixture.
4. Dual-engine lockstep: py fallback and native must agree (parity tests).

Audit of the fixes:
- QA-001 (udf/string.py SplitOnMatches): the parts[::groups+1] segment filter is
  general over any group count, mirrors Java Pattern.split / native semantics, and
  carries the spec citation inline. No abstraction breach. PASS.
- QA-002 (expressions/_lists.py Indexer routing): removing fhirpath_text/scalar
  from `_is_string_index_source` closes the silent-wrong-result seam at the class
  level (all chained navigation, not just the probe fields), reuses the existing
  list-returning `fhirpath` UDF + LIST_EXTRACT lowering (no new SQL paths), and is
  grounded in CQL 1.5 implicit property traversal. Literal strings, String-typed
  function results, and First()-demoted scalar defines keep the string Indexer;
  the SKEPTIC-pinned regression still passes unchanged. PASS.
- Residual (pre-existing, LOW, logged not fixed per no-fix-during-audit): the
  chain path shares the RESOURCE_ROWS LIST_EXTRACT lowering, where a negative
  DuckDB index wraps to the end of the list instead of CQL's index<0 -> null.
  Same behavior as before this launch on the rows path; recommend a shared
  guard in a future list-indexing chunk.

Drift log: the CQL AGENTS.md ARCHITECTURE DRIFT entry on chained-property typing
(ARCH-001 family) remains open for the general typing question, but the
string-Indexer manifestation is now closed with a spec-correct list semantics
and both-engine regression coverage. Noted in fhir4ds/cql/AGENTS.md.

QA quality gate: PASS, no RETRY_QA. The EXPLORER launch covered ~90 probes:
boundary/empty-needle positional operators, exact-length substring corners,
single-char indexers, nested-quantified regex with group substitution and empty
matches, Combine null-element skipping, Concatenate implicit-conversion typing,
operator chains, and full end-to-end execution over loaded FHIR resources on
both engines. Two real bugs found and fixed; one intended behavior documented;
two QA-side expectation errors were self-corrected against the live spec text.

Compressed handoff: QA found QA-001 (MEDIUM SplitOnMatches py/native parity,
spec) and QA-002 (HIGH silent character-indexing of collapsed chained
navigation, both engines); the engineer fixed both at root cause with class-level
changes and dual-engine regressions; validation held string parity 11/11 and the
full baseline 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47). All
issues terminal (VERIFIED/VERIFIED/INTENDED); clean exit at min_iterations=1.

Recommended fix order for future launches: (1) shared negative-index guard for
LIST_EXTRACT-based CQL indexer lowering; (2) the standing ARCH-001
modelinfo-backed chained typing investment.
