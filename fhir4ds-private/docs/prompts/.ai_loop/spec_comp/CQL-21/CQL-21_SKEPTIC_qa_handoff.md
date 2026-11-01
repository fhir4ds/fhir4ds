# QA Handoff — CQL-21 SKEPTIC (clinical operators: AgeIn*/CalculateAgeIn*/Code-Concept equality/In(CS)/ExpandValueSet)

## Verdict: CLEAN with 1 finding (CQL-21-F01) — 20 fresh cases flagged=0 + bisection micro-probes

Age family verified via *At spellings: AgeInYearsAt(@2021-02-28)=21 on Feb-29 birthday
(leap-year last-valid-day doctrine live-confirmed); CalculateAgeInMonthsAt
(@2020-01-15,@2021-03-10)=13 (13 complete months + 23 days); WeeksAt=4, DaysAt=59,
HoursAt=5, MinutesAt=45, SecondsAt=30; Patient-context AgeIn* = 46y/558m/18263d for
birthDate 1974-12-25. DOCTRINE: registered overloads are 1-arg CalculateAgeIn*(VARCHAR)
Patient-context + 2-arg *At(birthDate,asOf) + 1-arg AgeIn* + 2-arg AgeIn*At — there is
NO 2-arg CalculateAgeIn* (BinderException is correct behavior, my spelling error).
Code/Concept: C1=C1 True, C1=C2 False, C1~C1 True, C1~C2 False, ToConcept(C1)~ToConcept(C2)
False (codes-intersection), C1 in "LOINC" True, C1 in "SNOMED" False, S1 in "SNOMED" True.
ExpandValueSet: Count(ExpandValueSet("VS1")) → None (empty VS1 renders None at the
population surface). Population surface renders age scalars as STRINGS — norm() int-normalizes.

## FINDING CQL-21-F01 (LOW, findings-only, NOT patched)
R5 `ToConcept(C1) = ToConcept(C2)` (and self-equality) → native False (spec-correct;
unequal concepts) but forced-Python-fallback → InvalidInputException
'TypeError: float() argument must be a string or a real number, not NoneType'.
Concept construction is healthy on fallback (Count(ToConcept(C1).codes)=1); the =
comparison path lowers through parse_quantity/quantity_compare machinery and the
fallback UDF crashes on a NULL operand. Fix direction for the human: guard/NULL-propagate
the float() call in the concept-equality/quantity_compare fallback chain (udf.py/macros);
add a dual-engine parity pin. Excluded from the green probe lib per findings-only discipline.

Evidence: .temp/qa/speccomp2/cql21_skeptic_probe1.py + /tmp/opencode/cql21_bisect.py
