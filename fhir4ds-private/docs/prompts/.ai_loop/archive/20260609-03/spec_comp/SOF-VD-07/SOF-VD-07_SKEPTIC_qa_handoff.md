# QA Handoff - SOF-VD-07 SKEPTIC

## Scope
Fresh SKEPTIC pass for SQL-on-FHIR ViewDefinition `select.repeat`. I read the loop rules, current state, global rules/knowledge, root AGENTS, and `fhir4ds/viewdef/AGENTS.md`. Spec anchors checked: SQL-on-FHIR latest ViewDefinition `repeat` section and FHIR JSON array-shape rules.

## Hypotheses Tested
- `repeat` parser/direct dataclass shape validation may distinguish absent/null/non-array members but miss present empty arrays.
- SQL generation may treat a present empty repeat as no iterator and evaluate columns against the root context.
- Repeat execution should keep native/fallback parity for expression entries, multiple paths, ordering, `%rowIndex`, nested forEach composition, and deep traversal.

## Finding
- `SOFVD07-SKEPTIC-001` HIGH OPEN: present `repeat: []` is accepted by parser, direct dataclass `to_dict()`, and direct SQL generation. SQL generation then skips `fhirpath_repeat` because the list is falsey, so invalid JSON behaves like repeat absence/default `$this`.

## Fresh Evidence
Inline probe in this fresh run:
- malformed/null/non-array/non-string repeat inputs were rejected.
- `repeat: []` was accepted with `vd.select[0].repeat == []` and generated SQL lacking `fhirpath_repeat`.
- direct `Select(repeat=[])` serialized `repeat: []` and generated SQL lacking `fhirpath_repeat`.

## Remediation Target
Centralize the fix in `validate_repeat_paths()` so parser, `ViewDefinition.from_dict()`, `Select.to_dict()`, and direct `SQLGenerator` preflight all reject a present empty repeat array. Add parser, generator, serializer, and execution-focused regression coverage, then run focused ViewDefinition repeat tests, ViewDefinition conformance, and full conformance.
