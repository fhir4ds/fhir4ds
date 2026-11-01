# QA Handoff — CQL-02 EXPLORER (iteration 1, 2026-08-19)

Personality: EXPLORER (boundary/combination probing). Chunk: CQL 1.5 Types — Clinical
(Code, CodeSystem, Concept, ValueSet, Vocabulary).

## Spec grounding
cql-master 09-b-cqlreference.md (local cache /mnt/d/cql_agent/data/cql-master):
- Equivalent: String equivalence ignores case+locale and normalizes whitespace; null is
  NOT equivalent to ''. Code equivalence: code+system elements only. Concept: non-empty
  code intersection. Equivalent is total (always true/false).
- Equal (tuple): true iff values for all elements *that have values* are equal
  (conjunction of equality comparisons).
- union/intersect/distinct (List<T>): equality semantics, nulls considered equal.
- ToConcept(Code) propagates display; ToConcept(List<Code>) no display; null->null.
- ToString: no Code/Concept overload (returns null).

## Probed (both native C++ and Python fallback, translation + DuckDB execution)
- Whitespace/unicode boundaries in Code ~ (casefold ß/SS, accents, tab/leading/trailing
  spaces in code and system): all correct on both backends.
- = vs ~ matrices incl. display/version differences, null literals: correct.
- List ops over List<Code> (distinct/union/intersect, case variants, display variants):
  correct equality-keyed semantics on both backends.
- Coalesce/case/is null with Code/Concept, First((...).codes).code, display accessors,
  ToConcept roundtrips (Count of codes, display propagation), Concept.codes aggregates
  (Count, exists, distinct), empty/null pathological codes and systems: correct
  (earlier fhirpath_text errors were a harness artifact of registering without
  include_fhirpath=True; full registration executes cleanly).
- Named code accessors (.code/.system/.display) and cross-literal equivalence with
  trailing-space systems: correct.

## Issues found
- QA-001 (HIGH, OPEN): absent system vs explicit `system: null` asymmetry in Code
  static equality and equivalence. `Code { code: 'x' } ~ Code { code: 'x', system: null }`
  -> False (expected True); `=` likewise False (expected True). Both backends; shared
  translator-layer root cause (_normalize_static_clinical_code always emits system key;
  _code_key treats None vs '' inconsistently with no null-vs-null handling).
- QA-002 (HIGH, OPEN): `(Concept { ... }).codes ~ <List<Code>>` (and ToConcept(...).codes,
  alias .codes) falls through to generic CQLListEquivalentEq byte-wise JSON comparison ->
  case-sensitive, returns False where spec-correct answer is True. Direct list-literal ~
  list-literal is correct, so the divergence is specific to the statically folded
  `.codes` SQLArray operand shape.

## Verified clean (no issue)
codesystem-alias-through-included-library remains the known LOW observation from the
HISTORIAN launch (not re-tested; unchanged).

Probe files: .temp/qa/cql02_explorer_fresh_probe.py, .temp/qa/cql02_explorer_followup1.py.
