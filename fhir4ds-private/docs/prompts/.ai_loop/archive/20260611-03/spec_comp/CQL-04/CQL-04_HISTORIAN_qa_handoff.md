# QA Handoff - CQL-04 / HISTORIAN
Chunk: CQL-04 (CQL)
Sections: Logical Operators
Items: And(left, right); Implies(left, right); Not(argument); Or(left, right); Xor(left, right)
Command: python3 -m pytest fhir4ds/cql/tests/unit/test_lexer.py -q --maxfail=1
Result: PASS

No issues found.
