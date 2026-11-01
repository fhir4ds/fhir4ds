# QA Handoff — SOF-VD-04 EXPLORER iter 1 fresh run (2026-07-03)

## Personality: EXPLORER (Role C — Fuzzer / Abuser)

## Mission
Throw pathological inputs at the API, chain functions in unexpected ways,
pass deeply nested or malformed resources. Focus on discovery through chaos
for `column.collection`, `column.type`, `column.tag` (chunk SOF-VD-04).

## Authoritative Spec Reference
- Source: https://build.fhir.org/ig/FHIR/sql-on-fhir-v2/StructureDefinition-ViewDefinition.html (v2.1.0-pre)
- Key normative text:
  - **§Column Types**: "All values in a given column must be of a single data type."
  - **§Processing Algorithm > Process(S, N) step 2.2.1**: cardinality guard
    raises "Multiple values found but not expected for column".
  - **§column.tag**: 0..* repeating element; each tag has required `name` (1..1)
    and `value` (1..1).

## Probe Coverage
68-assertion / 7-battery pathological/abuse probe at
`/mnt/d/fhir4ds/.temp/qa/sof_vd04_explorer_2026_07_03/probe.py`.

Batteries:
- **Item 1 — collection type chaos**: 18 assertions covering direct + parser
  rejection of non-bool truthy/falsy values (`1`, `0`, `"true"`, `"false"`,
  `"yes"`, `None`, `[True]`, `{"x":1}`), `True`/`False` acceptance at both
  boundaries, and post-construction mutation of `collection` to `"yes"` being
  rejected by `to_dict()` (re-validation).
- **Item 2 — multi-value cardinality chaos**: 2 assertions covering
  pathological paths (`name.given`, `identifier.where(...).value`) — both
  emit the `array_length ... violates collection=false` SQL guard.
- **Item 3 — collection=true with chaos data**: 5 assertions covering
  `collection=True` SQL generation with `type=None`, `"string"`, full URI
  form; dataclass `to_dict()` round-trip with description.
- **Item 4 — type URI chaos**: 25 assertions covering rejection of empty,
  whitespace-only (`"   "`, `"\t\n"`), non-string (`123`, `4.5`, `[]`, `{}`,
  `True`, `b"bytes"`) types; control-char URI handling; unicode external URI
  preservation (`http://example.com/Unïcode`); parser explicit-null type
  rejection; case-sensitivity (`string` → `ColumnType.STRING`, `String` →
  preserved as unknown external URI).
- **Item 5 — type-mismatch in iterator context**: 2 assertions covering type
  guards under nested `forEach` iteration and unknown external URI SQL
  generation without crash.
- **Item 6 — tag chaos**: 16 assertions covering type confusion (`42`,
  `3.14`, `True`, `None`, `[1,2]`, `(1,2)`, `{1,2}`, `"not-a-dict"`), extra
  fields in tag dict, 10000-char name/value stress, unicode name/value,
  post-construction mutation to empty name (rejected by `to_dict`), parser
  non-array tag rejection, parser `None` tag rejection, missing name/value
  rejection, 1000-tag stress, post-construction mutation of `Column.tag` to
  `None` (rejected by `to_dict`).
- **Cross-cutting chaos**: 7 assertions combining pathological inputs
  (empty path+name with tag, non-string path/name/description, full
  `to_dict()` round-trip + parser round-trip stability).

## Results
**68 PASS / 0 FAIL / 0 INFO**

All six SOF-VD-04 spec items verified CLEAN under pathological inputs.
Notable confirmations:

- **Item 1**: `Column.collection` rejects all non-bool truthy/falsy values
  (`1`, `"true"`, `"yes"`, `None`, `[True]`, `{"x":1}`) at both direct
  construction and parser. Critically, post-construction mutation
  (`c.collection = "yes"; c.to_dict()`) is rejected because `to_dict()`
  re-validates via `validate_optional_boolean` — no silent fallback.
- **Item 2**: The SQL cardinality guard survives function-call paths
  (`name.given`) and `.where(...)` paths — both emit
  `array_length(...) > 1 ... violates collection=false`.
- **Item 3**: `collection=True` columns generate valid SQL with all type
  hints (`None`, `"string"`, full URI). No cardinality guard on outer
  projection (correct per spec §2.2.1 step 3).
- **Item 4**: All pathological type strings rejected. Unicode external URIs
  preserved verbatim. Case-sensitivity is correct: `"string"` →
  `ColumnType.STRING`, `"String"` → preserved as unknown (spec has no
  case-normalization rule for external URIs).
- **Item 5**: Type guards emit under `forEach` iteration context (not just
  top-level). Unknown external URIs (`http://example.com/Foo`) do not crash
  SQL generation — the type is opaque per spec §Column Types.
- **Item 6**: All type-confusion tag items rejected. Tag dict with extra
  fields accepted (extra ignored). 10000-char name/value accepted. Unicode
  name/value accepted. Critical: post-construction mutation to empty name or
  to `tag=None` is rejected by `to_dict()` because both re-validate — no
  silent fallback. Parser rejects non-array tag and `None` tag. 1000-tag
  stress passes.
- **Cross-cutting**: Full `to_dict()` → parser round-trip stable for
  fully-populated column (path, name, type, collection, description, tag).

## Validation
- ViewDefinition pytest: **1055/1055** PASS (no regressions)
- Full conformance baseline preserved per `PROC_VALIDATION.md`.

## Conclusion
**CLEAN.** Zero non-terminal CRITICAL/HIGH/MEDIUM issues identified for
SOF-VD-04 under EXPLORER's pathological/abuse probe. Per `GLOBAL_RULES.md`
§Orchestration, clean exit is allowed at `min_iterations=1`. The SOF-VD-04
collection/type/tag surface is robust against:
- Type confusion at the dataclass boundary (truthy/falsy non-bools).
- Pathological URI strings (control chars, unicode, whitespace).
- Tag type confusion and stress (1000 tags, 10000-char values).
- Post-construction mutation (re-validated by `to_dict()`).
- Pathological FHIRPath paths in iterator contexts.

All earlier SOF-VD-04 hardening (post-SOF-VD-03 SKEPTIC `__post_init__`,
SOF-VD-03 EXPLORER whitespace rejection, multi-value cardinality guard,
type-mismatch runtime reporting) remains intact under chaos inputs.
