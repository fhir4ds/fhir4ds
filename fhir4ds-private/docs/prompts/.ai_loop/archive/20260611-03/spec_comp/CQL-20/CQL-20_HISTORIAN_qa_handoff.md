# QA Handoff - CQL-20 / HISTORIAN
Chunk: CQL-20 (CQL)
Sections: Aggregate Functions
Items: AllTrue(list); AnyTrue(list); Avg(list); Count(list); GeometricMean(list); Max(list); Min(list); Median(list); Mode(list); PopulationStdDev(list); PopulationVariance(list); Product(list); StdDev(list); Sum(list); Variance(list)
Command: python3 -m pytest fhir4ds/cql/tests/unit/test_lexer.py -q --maxfail=1
Result: PASS

No issues found.
