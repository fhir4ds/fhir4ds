# QA Handoff - CQL-21 / HISTORIAN
Chunk: CQL-21 (CQL)
Sections: Clinical Operators
Items: AgeInYears|Months|Weeks|Days|Hours|Minutes|Seconds(), AgeInYearsAt|MonthsAt|...At(asOf), CalculateAgeInYears|Months|...InYears(birthDate), CalculateAgeInYearsAt|MonthsAt|...At(birthDate, asOf), Equal (Code/Concept), Equivalent (Code/Concept), In (Codesystem), ExpandValueSet(ValueSet), In (Valueset)
Command: python3 -m pytest fhir4ds/cql/tests/unit/test_lexer.py -q --maxfail=1
Reran at: 2026-06-12T19:00:00Z
Result: PASS (133 passed, 0 failed, 0 errors)

No issues found.
