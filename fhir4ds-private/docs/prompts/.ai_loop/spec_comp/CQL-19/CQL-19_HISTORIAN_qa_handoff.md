# QA Handoff — CQL-19 HISTORIAN (list operators Part 2, dynamic-source)

## Verdict: CLEAN — 16-case combined H/E battery, parity OK, value-checks ALL OK

Normative rows over the DYNAMIC multi-valued field Patient.name.given
(name.given = [John, Kim]): Length 2; Last 'Kim'; First 'John';
Count(Skip(.,1))=1; Count(Take(.,1))=1; Count(Tail(.))=1;
union {'Extra'} -> 3; contains 'Kim' True; {1,2,3} properly includes
{2,3} True; Skip(.,0)=2 identity; Take(.,5)=2 clamp; singleton from
Take(.,1)='John' (single-element dynamic source); Tail({1,2,3,4})=3;
Skip({1,2,3,4},2)=2; Last({1.5,2.5,0.5})=Decimal 0.5.
The dynamic-list promotion doctrine holds end-to-end (full projection,
no fhirpath_text truncation).

Evidence: .temp/qa/speccomp2/cql19_historian_explorer_probe1.py
