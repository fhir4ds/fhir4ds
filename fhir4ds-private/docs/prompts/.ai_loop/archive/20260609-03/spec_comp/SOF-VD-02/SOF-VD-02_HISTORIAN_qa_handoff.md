# QA Handoff: SOF-VD-02 / HISTORIAN

Scope: SQL-on-FHIR ViewDefinition constants: `ViewDefinition.constant`,
`constant.name`, and `constant.value[x]`.

Personality: HISTORIAN. I walked the current SQL-on-FHIR v2 logical model for
constants against parser, public constructor, serializer, constant resolver,
SQL generation, and DuckDB execution.

Spec anchors:
- `ViewDefinition.constant` is `0..*` BackboneElement.
- `ViewDefinition.constant.name` is `1..1 string` with the `sql-name`
  invariant `^[A-Za-z][A-Za-z0-9_]*$`.
- `ViewDefinition.constant.value[x]` is `1..1` and currently allows only the
  primitive choices `base64Binary`, `boolean`, `canonical`, `code`, `date`,
  `dateTime`, `decimal`, `id`, `instant`, `integer`, `integer64`, `oid`,
  `string`, `positiveInt`, `time`, `unsignedInt`, `uri`, `url`, and `uuid`.
- Constants are referenced as FHIRPath external constants with `%name`; built-in
  environment variables such as `%resource`, `%rootResource`, and `%rowIndex`
  remain runtime variables, not user constants.

Fresh probe:
- `.temp/qa/sof_vd02_historian_probe.py`
- Covered all 19 supported value fields through `parse_view_definition()`,
  `ViewDefinition.from_dict()`, `Constant.to_dict()`, direct `Constant`
  validation, undefined `%name` failures, lexical substitution that skips string
  literals/comments, built-in environment variable pass-through, and executable
  native-loaded plus forced Python fallback views.
- Result: PASS.

Validation:
- Focused constants parser/integration pytest:
  `40 passed`.
- ViewDefinition spec compliance pytest:
  `435 passed`.
- ViewDefinition conformance:
  `134/134`, including `constant.json 8/8` and `constant_types.json 14/14`.
- Full conformance:
  `2822/2822` overall: ViewDefinition `134/134`, FHIRPath `935/935`, CQL
  `1706/1706`, DQM `47/47`.

Issues found: none.

No code remediation is required for this pass. The recent SKEPTIC fixes for
singular `constant`, duplicate names, undefined user constants, and direct
`Constant` validation held under fresh HISTORIAN verification.
