# QA Handoff — CQL-12 (HISTORIAN), iteration 1

Chunk: CQL 1.5 String Operators (Combine, Concatenate, EndsWith, Indexer, LastPositionOf,
Length, Lower, Matches, PositionOf, ReplaceMatches, Split, SplitOnMatches, StartsWith,
Substring, Upper).

Personality: HISTORIAN — spec walk against cql.hl7.org Appendix B (verified normative text
live: Combine null-element skip, Indexer 0-based null out-of-range, LastPositionOf empty
pattern = length, SplitOnMatches returns List<String>, PositionOf empty pattern = 0),
plus institutional memory (prior SKEPTIC launch, doctrine registry) to hunt NEW divergences
beyond the archived probes.

Probes: /mnt/d/fhir4ds/.temp/qa/cql12_hist/{probe1.py,probe2.py} plus inline probes.

New coverage beyond the SKEPTIC launch:
- Unicode/multibyte: Length('José')=4, Indexer/Substring/PositionOf/LastPositionOf over
  'Müller'/'José', Upper('naïve')='NAÏVE', Lower('GRÜẞE')='grüße', Split on 'é' — all
  correct on BOTH native and Python engines (DuckDB length/substring are
  character-based; no byte/codepoint divergence found, unlike the FHIRPath C++ pitfalls).
- Composition: Combine(Split(...)), CombineSep over dynamic lists, Length(Split(...)),
  Split(...)[i] including out-of-range NULL.
- Regex dialect edges on both engines: anchors ^/$, alternation, {m,n} quantifiers,
  char classes, escaped dot, empty-match replace ('x*' -> '-a-b-c-'), empty-match
  SplitOnMatches, multibyte patterns, multi-group $1/$2 substitution — all agree and
  match spec (partial, single-line, case-sensitive).
- Boundary: Split null separator (spec-silent; engines agree -> ['A B'], INTENDED),
  typed-null Combine lists -> NULL, '&' null-to-empty chains, empty-string list
  elements preserved by Combine.
- Regression re-verification of prior SKEPTIC fix (QA-001 old): scalar string define
  Fam[3] -> 't', Fam[0] -> 'M', Fam[99] -> NULL via evaluate_measure on BOTH engines.
  Fix holds and is regression-free.

Issues:
- QA-001 (MEDIUM, OPEN): Combine(First([Patient]).name.given, '+') — spec-valid
  List<String> source lowered as scalar fhirpath_text (first-element-only) due to the
  deferred ARCH-001 chained-typing debt, and the CombineSep macro then crashes with an
  opaque DuckDB BinderException (lambda bound against scalar before the macro type
  guard can fire). Needs a typed translate-time failure (QA-004 precedent).
- QA-002 (LOW, INTENDED): Split with null separator — spec-silent, engine-consistent.

Three apparent probe failures were QA authoring errors (regex literal escaping; two
wrong expected values), all re-verified correct on both engines.
