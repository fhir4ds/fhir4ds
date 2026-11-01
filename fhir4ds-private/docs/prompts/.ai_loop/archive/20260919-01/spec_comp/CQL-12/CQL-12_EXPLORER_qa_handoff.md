# QA Handoff — CQL-12 (EXPLORER), iteration 1

Chunk: CQL 1.5 String Operators (Combine, Concatenate, EndsWith, Indexer, LastPositionOf,
Length, Lower, Matches, PositionOf, ReplaceMatches, Split, SplitOnMatches, StartsWith,
Substring, Upper).

Personality: EXPLORER — boundary conditions, combinations, chained operators, and
retrieved-FHIR end-to-end execution, probing corners the SKEPTIC/HISTORIAN launches did
not reach. Spec text verified live against cql.hl7.org Appendix B (String Operators):
PositionOf not-found=-1 / empty-pattern=0; LastPositionOf not-found=-1 /
empty-pattern=length; Substring out-of-range=null; Indexer 0-based null out-of-range;
Combine null-elements-ignored; Concatenate + null-propagating / & null-as-empty;
conversion table has NO implicit conversion to String (Integer/Date/Quantity ->
String all Explicit).

Probes: /mnt/d/fhir4ds/.temp/qa/cql12_explorer_2026_08_21/{probe1.py,probe2.py} plus
inline decomposition probes. 62 translated cases + typing probes + 11-column
end-to-end over loaded Patient/Observation resources, each on BOTH the Python-only
fallback and the native extension engine.

Verified clean (both engines, translated + executed):
- PositionOf/LastPositionOf overlaps ('aa' in 'aaaa'=0/2, 'aaa' in 'aaaaa'=2),
  empty needles (0 / length / 0-on-empty), not-found -1, pattern-longer-than-string -1,
  null arguments.
- Substring exact-length boundaries (start=len -> null, start=len-1 -> last char,
  start past len -> null, negative -> null), zero length -> '', length beyond rest ->
  clamped, null length -> null, empty-string corners, Substring('',0) -> null
  (consistent with pinned 'start >= length -> null' doctrine).
- Indexer last-char index, single-char strings, negative/empty/null index.
- Length('')=0 vs Length(null)=null. Lower/Upper empty/null. StartsWith/EndsWith
  equal/longer-prefix/empty-argument corners (all false except equal).
- Regex: nested quantified groups (?:ab)+, optional groups in substitution ($2 absent),
  empty-match replace ('' -> '-', mid-string), $1 with unmatched pattern (typed
  CQLRegexPatternRejected, Java-consistent, INTENDED = QA-003).
- Combine literal lists with null elements (skipped per spec), all-null -> null,
  empty-string elements preserved. Concatenate over Integer/Date/Quantity operands ->
  typed translate-time errors (spec conversion table has no implicit ToString);
  ToString() overloads work.
- Chains Split->Indexer->Substring over literals; Split on empty string -> [''].
- End-to-end over FHIR: Matches on Patient.id and coding.code (typed FHIR.code),
  Upper/Substring/EndsWith on name.family, StartsWith/Split/LastPositionOf over
  Observation valueString, query where-clause with cast-to-string. py == cpp on every
  column. LastPositionOf('o','Hello world foo')=14 confirmed correct.

Issues:
- QA-001 (MEDIUM, OPEN): SplitOnMatches with capture groups includes the group
  captures in the Python fallback (re.split dialect leak) but not in the native
  engine; spec (no group-inclusion clause; Java Pattern.split reference semantics)
  matches native. Parity + spec violation on the Python path.
- QA-002 (HIGH, OPEN): silent wrong results from Indexer over collapsed chained
  navigation on BOTH engines: Patient.name.given[0] -> 'J' (character, expected
  'Joel'), First([Observation]).code.coding[0] -> '{' (character of raw JSON),
  .code.coding[0].code -> None. Root cause is the deferred ARCH-001 chained-typing
  debt: navigation lowers to scalar fhirpath_text, then the (spec-correct) scalar
  string Indexer character-indexes it. Both engines agree, so it is a correctness
  bug, not a parity bug.
- QA-003 (LOW, INTENDED): ReplaceMatches '$1' referencing an uncaptured group raises
  a typed rejection rendered as "Unsupported feature: ReplaceMatches" (message wording
  slightly misleading; behavior intended, Java-consistent).

Two probe expectations of mine were wrong and re-verified as engine-correct:
ReplaceMatches backtracking group values; LastPositionOf on 'Hello world foo'.
