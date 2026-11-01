# QA Handoff — FP-17 HISTORIAN (§6.5 Boolean Logic)

## Verdict: CLEAN — 41 value-asserted truth-table rows; 2 MISS both adjudicated probe-expectation errors

Full §6.5 truth tables WITH value assertions. The 2 MISS rows — ({} and false) →
['false'] and ({} or true) → ['true'] — are SPEC-CORRECT per the ABSORBING-CELL
doctrine pinned by official fixtures testBooleanLogicAnd8 ({} and false) = false →
TRUE and testBooleanLogicOr7 ({} or true) = true → TRUE (tests-fhir-r4.xml
:1140/:1147): false-and-X and true-or-X are absorbing REGARDLESS of the other
operand being empty. My [] expectations ignored the absorbing rows; both engines
byte-identical on all 41 rows. not() rows value-asserted (true.not()→false,
{}.not()→empty, active.not()→false).

Evidence: .temp/qa/speccomp2/fp17_historian_probe1.py
