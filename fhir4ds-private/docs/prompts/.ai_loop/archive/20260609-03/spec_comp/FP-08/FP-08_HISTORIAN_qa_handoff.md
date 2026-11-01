# QA Handoff: FP-08 HISTORIAN

Spec grounding:
- HL7 FHIRPath Normative Release v2.0.0 §5.5.7 says `toQuantity([unit])`
  returns a Quantity when the singleton input item is Integer, Decimal,
  Quantity, convertible String, or Boolean; `convertsToQuantity([unit])`
  returns true for the same convertible shapes.
- §5.5.8 says `toString()` and `convertsToString()` include Quantity input.
- §4.5 and §5 require singleton argument/input errors for multi-item values,
  while empty input/arguments propagate empty.

HISTORIAN coverage:
- Wrote and ran a fresh native C++ vs forced Python fallback matrix at
  `.temp/qa/fp08_historian_probe.py`.
- Covered quantity string grammar, invalid leading whitespace, invalid bare
  `wk`, empty quoted units, optional unit argument arity/type/cardinality,
  String conversion arity, Time conversion precision/range/timezone rejection,
  and resource-backed FHIR Quantity values.

Finding:
- `QA-001` HIGH: FHIR Quantity path values report as Quantity through
  `is`/`ofType`, but native `toQuantity()`/`convertsToQuantity()` returned
  empty/false; both native and fallback `toString()`/`convertsToString()`
  returned empty/false. The fallback also accepted invalid Quantity objects
  with non-numeric values and rounded `5 mg -> 0 g`.

Probe result before remediation:
- `cases=39`, `mismatches=6`, `failures=13`.
