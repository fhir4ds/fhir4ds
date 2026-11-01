# QA Handoff — CQL-21 EXPLORER

Scope: CQL clinical operators, with abuse testing around versioned terminology values and no-Python execution.

Spec anchors checked:
- `ExpandValueSet(ValueSet)` accepts a ValueSet value and returns the current expansion as `List<Code>`.
- ValueSet references are structured clinical values with optional `version`; membership boundaries already unwrap these to canonical `id|version` URLs.

Fresh probe:
- `.temp/qa/cql21_explorer_probe.py`

Finding:
- `CQL21-EXPLORER-001` HIGH: `HR in Vitals` for `valueset Vitals: '<url>' version '2026'` correctly targeted `url|2026`, but `Count(ExpandValueSet(Vitals))` passed a structured ValueSet JSON argument to `ExpandValueSet` and the macro looked up only `$.id`. With only `valueset_codes.valueset_url = '<url>|2026'` loaded, membership returned true while expansion returned null.

Validation:
- Fresh EXPLORER probe passes.
- Clinical operator parity pytest passes 12/12.
- Official CQL conformance passes 1706/1706.
- Full conformance passes 2822/2822.
