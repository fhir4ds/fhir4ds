# QA Handoff — CQL-22 HISTORIAN (Message operator)

## Verdict: CLEAN — 12/12 fresh cases (combined H/E battery), 0 parity diffs

Normative rows verified: dynamic-source Message passthrough (AgeInYears(birthDate)=51
int today-anchored; 1+2=3; Patient.name.given LIST ['John','Kim'] unmodified;
@2024-06-15 date; 5 'mg' Quantity JSON unmodified); false-condition fold ('x');
nested chained Message -> innermost source (2); Count/Length sources (2/4);
lowercase-severity 'warning' passthrough (9); null-source Trace passthrough (None);
Today() source passthrough (non-null date string).

3 expectation corrections were checker-side (H1 stale 46->51 today-math;
H3/H4/H5 want-None placeholders -> actual unmodified sources list/date/qty-JSON
— passthrough IS the doctrine).

Evidence: .temp/qa/speccomp2/cql22_historian_explorer_probe1.py
