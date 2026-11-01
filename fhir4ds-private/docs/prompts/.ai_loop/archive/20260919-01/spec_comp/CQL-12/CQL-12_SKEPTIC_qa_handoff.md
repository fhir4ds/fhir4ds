# QA Handoff — CQL-12 (SKEPTIC), iteration 1

Chunk: CQL 1.5 String Operators (Combine, Concatenate, EndsWith, Indexer, LastPositionOf,
Length, Lower, Matches, PositionOf, ReplaceMatches, Split, SplitOnMatches, StartsWith,
Substring, Upper).

Method: verified normative semantics against cql.hl7.org Appendix B (String Operators),
then probed actual behavior through (a) translate_cql + DuckDB execution on BOTH the
native/C++ extension connection and the Python-supplement-only connection, and (b)
end-to-end evaluate_measure over loaded FHIR Patient data (retrieved .name.family values
and where-clause usage).

Probes: /mnt/d/fhir4ds/.temp/qa/cql12_string/{probe1,probe2,probe3,probe4}.py

Results:
- 77-case spec-example matrix (probe1): all pass on both engines except SplitOnMatches
  trailing-empty (QA-002). Spec examples verified include PositionOf empty pattern -> 0,
  not-found -> -1; LastPositionOf('B','ABCDEDCBA')=7, ('','ABCDE')=5, not-found -> -1;
  Substring 0-based with truncation (len overrun returns remainder), invalid starts/lengths
  -> NULL; Combine null/empty-list -> NULL, null separator ignored; +/Concatenate null
  propagation, & null-to-empty; StartsWith/EndsWith case-sensitive, empty prefix true;
  Matches/ReplaceMatches single-line mode, $1 group substitution, escaped dollars.
- Nested composition (probe5): Length(Split(...)), Split(...)[1], Substring(Upper(...)),
  PositionOf(Lower(...),...) all correct both engines.
- End-to-end over retrieved data (probe4): all operators correct through evaluate_measure
  EXCEPT the string Indexer on a dynamic scalar string define -> QA-001 (HIGH).
- Cross-engine parity: py vs cpp agreed on every probe output.

Issues: QA-001 (HIGH, OPEN), QA-002 (LOW, OPEN). See evolution.json.
