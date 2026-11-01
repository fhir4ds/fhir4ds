# QA Handoff - SOF-VD-02 EXPLORER

## Scope

Fresh EXPLORER pass over SQL-on-FHIR ViewDefinition constants using current
source and spec citations only. I tested parser validation, constant reference
extraction/substitution, SQL generation, DuckDB execution, official constants
fixtures, and native C++ vs forced Python fallback where FHIRPath UDFs were
involved.

## Spec Anchors

- SQL-on-FHIR v2.0.0: `ViewDefinition.constant` is 0..*, `constant.name` is
  1..1 and referenced as `%[name]`, and `constant.value[x]` is 1..1 over the
  listed primitive choices.
- SQL-on-FHIR v2.0.0 "Using Constants": constants are placeholders in
  FHIRPath expressions and are replaced before the expression is evaluated.
- FHIRPath N1 grammar: string literals and external constants are distinct
  terms; an external constant is `%` plus an identifier/string.
- FHIRPath N1 string literals use backslash escapes, including `\'` for a
  single quote and `\\` for backslash.
- FHIR R5 JSON: all primitives except integer, unsignedInt, positiveInt,
  decimal, and boolean are JSON strings, explicitly including integer64.

## Probes Run

- `PYTHONPATH=/mnt/d/fhir4ds python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_02_explorer_constants_probe.py`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/test_spec_compliance.py::TestSpecConstants -q`
- `PYTHONPATH=/mnt/d/fhir4ds python3 -m pytest fhir4ds/viewdef/tests/unit/test_constants.py fhir4ds/viewdef/tests/unit/test_parser.py -q`

## Findings

### QA-001 HIGH - Constant substitution is not FHIRPath-lexical

Current regex substitution and validation treat `%name` inside FHIRPath string
literals as a constant reference. Reproducer log:
`fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/sof_vd_02_explorer_constants_probe.log`.

Observed:

- `path: "'%idx'"` with `valueInteger: 1` returns `"1"` in both native and
  forced fallback, but `%idx` is inside a string literal and should remain the
  literal string `"%idx"`.
- `path: "'%missing'"` raises `ValidationError: Undefined constant(s)
  referenced: missing`, though the percent sequence is literal text.
- `valueString: "O'Reilly"` is resolved as SQL-style `O''Reilly` instead of a
  FHIRPath-escaped string. Native execution raises invalid FHIRPath; fallback
  returns NULL after evaluation error.

### QA-002 MEDIUM - `valueInteger64` accepts JSON numbers

`parse_view_definition` accepts `{"valueInteger64": 1234567890123}`. FHIR JSON
requires `integer64` values to be encoded as JSON strings, so this invalid
ViewDefinition should be rejected before SQL generation.

## Passing Controls

- Official constants spec fixture tests passed: 6/6.
- Existing constants/parser unit tests passed: 111/111.

## Handoff

Remediation should centralize lexical constant scanning in
`fhir4ds/viewdef/constants.py`, reuse it from `SQLGenerator._extract_constant_references`,
escape primitive string-like constants as FHIRPath literals before SQL escaping,
and tighten `valueInteger64` validation to JSON strings.
