# FP-16 QA Handoff (SKEPTIC, iteration 1, 2026-08-18)

Chunk: FHIRPath §6.4 Collections — `|` (union), `in` (membership), `contains` (containership).

Method: 37-case dual-path probe (native C++ extension vs forced Python fallback) at
`/mnt/d/fhir4ds/.temp/qa/fp16_skeptic_probe.py`, verified against normative spec text
fetched from hl7.org/fhirpath §6.4 plus official R4 fixtures (testUnion/testIn/
testContainsCollection groups in tests-fhir-r4.xml).

Findings:
- ZERO native-vs-fallback parity mismatches.
- All §6.4 semantics correct on both public UDF paths: union dedups at construction via
  `=` (incl. Integer=Decimal `1|1.0`→1, quantity `1 'cm'|10 'mm'`→1, deep-object
  `(name|name)`→1, `combine` then `|` dedups); `in` left-empty→empty, right-empty→false,
  multi-item left→error; `contains` right-empty→empty, left-empty→false, multi-item
  right→error; quantity/temporal/deep equality flow through membership; contains-operator
  vs contains(substring)-function disambiguation correct ('abc' contains 'b' → false op;
  '12345'.contains('5') → true fn); `1 + 2 | 3` precedence per §6.8.
- QA-001 (MEDIUM, RESOLVED): exported helper API `operators.membership()/contains()`
  swallowed multi-item singleton violations (returned {}) where engine/native raise.
  12th instance of the "exported helper API forgotten" family.

No code regressions: conformance 2832/2832 held after poking.
