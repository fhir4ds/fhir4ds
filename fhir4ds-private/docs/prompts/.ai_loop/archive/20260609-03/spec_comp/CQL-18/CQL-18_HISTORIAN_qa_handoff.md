# QA Handoff: CQL-18 HISTORIAN

Personality: HISTORIAN
Chunk: CQL-18, List Operators Part 1

Spec anchor:
- CQL Reference v1.5.3 Appendix B, List Operators: list `contains`, `=`, `~`, `except`, `included in`, `IndexOf`, and `intersect` are defined in terms of element equality/equivalence with specific null behavior.
- CQL Reference v1.5.3 Appendix B, Clinical Operators: Code/Concept equality uses tuple equality by element name; Code/Concept equivalence ignores display/version and uses Code system+code intersection for Concepts.
- CQL Reference v1.5.3 Appendix B, Comparison Operators: Quantity equality returns null when dimensions are incompatible.

Fresh probe:
- `.temp/qa/cql18_historian_probe.py`

Findings:
- `QA-001` HIGH: public list equality helpers compare Code/Concept-shaped JSON through raw JSON equality. Same Code fields in different JSON key order return false instead of true; same code/system with a display component present on only one side returns false instead of null.
- `QA-002` HIGH: public list equality/containment helpers coalesce `quantityCompare(..., '==')` null results to false. Incompatible Quantity dimensions such as `1 'cm'` vs `1 'cm2'` should propagate unknown/null for list equality and containment when no definitive match exists.

Observed affected surfaces:
- Forced Python registration
- Native-loaded registration
- No-Python/browser-style macro surface

No source files were modified during QA.
