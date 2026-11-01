# QA Handoff - CQL-14 / EXPLORER
Chunk: CQL-14 (CQL)
Sections: Date/Time Operators Part 2
Items: Now(); On Or After precision; On Or Before precision; Same As precision; Same Or After precision; Same Or Before precision; Subtract (left DateTime, right Quantity); Time(hour, minute, second, millisecond); TimeOfDay(); Today()
Command: python3 -m pytest fhir4ds/cql/tests/unit/test_lexer.py -q --maxfail=1
Result: PASS

No issues found.
