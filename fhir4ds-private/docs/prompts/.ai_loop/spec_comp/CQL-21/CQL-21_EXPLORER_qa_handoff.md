# QA Handoff — CQL-21 HISTORIAN + EXPLORER (combined fresh battery)

## Verdict: CLEAN — 12/12 dynamic rows, PARITY OK native==fallback
(`[('p1', True, '46', True, True, True, True, False, True, True, 'adult', True, True)]`)

Evidence: .temp/qa/speccomp2/cql21_historian_explorer_probe1.py
H: AgeInYears(Patient.birthDate)>=50 True; AgeInYearsAt(@2021-02-28)='46' (string render);
CalculateAgeInYearsAt(Feb-29)=21; AgeInMonths>500; AgeInYears>=40.
E: AgeInDaysAt(birthDate,Today())>18000; CalculateAgeInMonthsAt=13;
AgeInYears=AgeInYearsAt(Today()); if-age adult; AgeInYearsAt(2038)>At(2021);
CalculateAgeInWeeksAt=4.

FINDING carried (CQL-21-F01): ToConcept(X)=ToConcept(Y) crashes the forced-Python
fallback UDF (TypeError float() None) while native returns False. ToConcept rows
EXCLUDED from this battery per the SKEPTIC adjudication. Probe-harness note: the
static `code in "CodeSystemName"` spelling emits structured-JSON IN-list SQL
(known CQL-02 HISTORIAN family binder behavior) — avoided here in favor of age rows.
