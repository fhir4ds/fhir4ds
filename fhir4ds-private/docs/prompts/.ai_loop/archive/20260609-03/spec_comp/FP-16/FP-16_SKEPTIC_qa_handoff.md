# QA Handoff - FP-16 SKEPTIC

Scope: FHIRPath Section 6.4 collection operators, especially `|`, `in`, and
infix `contains`, compared across native-loaded DuckDB/C++ and forced Python
fallback registrations.

Spec basis: the normative FHIRPath Section 6.4 text says union removes
duplicates with equality semantics; `in` requires the left operand to be empty
or a singleton and throws on multiple left items; `contains` is the converse
and requires the right operand to be empty or a singleton.

Probe: `.temp/qa/fp16_skeptic_probe.py` exercised union duplicate elimination,
numeric equality, temporal and Quantity membership, object/Quantity equality,
empty propagation, string-function `s.contains(term)` versus infix
`s contains term`, and precedence controls.

Finding: `QA-FP16-SKEPTIC-001` found that forced Python fallback
`fhirpath_is_valid()` returned true for `(1 | 2) in arr` and
`arr contains (1 | 2)`, while native returned false. Public result wrappers on
both backends already returned empty/NULL for the runtime singleton error.
