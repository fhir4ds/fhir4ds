# QA Handoff — CQL-02 HISTORIAN (Code/CodeSystem/Concept/ValueSet/Vocabulary)

## Verdict: CLEAN — 12 fresh cases, 0 parity diffs (1 value-checker adjudication)

Normative walk: Code selector fields; C1 is/as Code; Count(ToConcept(C1).codes)=1;
Concept ~ same-codes True / disjoint False; vocabulary-splits 6-tuple per CQL-21
doctrine (VS/CS is ValueSet/CodeSystem/Vocabulary); C1 is Vocabulary False;
versioned CS "SNOMED".id (value correct — my checker compared plain str vs
LIST-wrapped rendering, engine right); S1.code; ("LOINC" as Vocabulary) is
CodeSystem True; C1 in "LOINC" True / in "SNOMED" False.

Lesson: population-SQL output columns render singletons as LIST-wrapped strings.

Evidence: .temp/qa/speccomp2/cql02_historian_probe1.py
