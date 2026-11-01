# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after 50 completed chunks. Reviewed the
current rerun state with focus on SOF-VD-04 through SOF-VD-08 and related
ViewDefinition parser/types/generator/test changes around column metadata,
nested select serialization, `forEach` / `forEachOrNull`, `repeat`, and
`unionAll`. This was review-only: no remediation was implemented, no workflow
was initialized, no chunk/personality files were archived, and
`spec_schedule.json` was not modified.

## New Findings From Review-50

No new issues were found in the SOF-VD-04 through SOF-VD-08 changes reviewed
for this milestone.

Focused review confirmed the recent guards are present for:
- Singular `column.tag` parsing and direct `ColumnTag` revalidation:
  `fhir4ds/viewdef/parser.py:116`, `fhir4ds/viewdef/types.py:507`,
  `fhir4ds/viewdef/types.py:520`, `fhir4ds/viewdef/generator.py:614`.
- Nested `Select.where` serialization validation:
  `fhir4ds/viewdef/types.py:674`.
- Present-null `forEach` / `forEachOrNull` rejection:
  `fhir4ds/viewdef/parser.py:65`, `fhir4ds/viewdef/parser.py:243`.
- Empty or malformed `repeat` rejection across parser, serializer, and direct
  generator preflight: `fhir4ds/viewdef/types.py:133`,
  `fhir4ds/viewdef/types.py:636`, `fhir4ds/viewdef/generator.py:656`.
- Present empty `unionAll: []` rejection in strict parser/from_dict paths:
  `fhir4ds/viewdef/parser.py:200`, `fhir4ds/viewdef/parser.py:235`.
- Union branch schema/name/type/collection validation:
  `fhir4ds/viewdef/generator.py:1245`.

## Review-45 Status

### REV-045-001 - HIGH - Parsed root metadata still accepts present JSON null

Status: OPEN.

`parse_view_definition()` still passes optional root metadata through
`dict.get()`, which erases present JSON null into absence. Focused read-only
probe confirmed the parser still accepts present null for `resourceType`, `id`,
`url`, `version`, `status`, `title`, and `description`, then `to_dict()` silently
omits those fields.

Evidence:
- `fhir4ds/viewdef/parser.py:421` through `fhir4ds/viewdef/parser.py:429`
  pass `data.get(...)` values to `validate_root_metadata_fields()`.
- `fhir4ds/viewdef/types.py:1072` through `fhir4ds/viewdef/types.py:1100`
  treat `None` as absent for those optional metadata fields.

The parser should reject present-null root metadata before calling the shared
validator, matching FHIR JSON's no-null-property boundary.

### REV-045-002 - HIGH - Root `ViewDefinition.to_dict()` can still emit invalid `where` JSON

Status: OPEN, narrowed.

SOF-VD-05 EXPLORER closed the nested `Select.to_dict()` portion of this finding:
`Select.where` now routes through `validate_where_conditions()` and the focused
probe rejected malformed nested where entries. The root serializer path remains
open. `ViewDefinition.to_dict()` still copies root `where` entries verbatim, so
direct dataclass serialization can emit invalid official JSON such as
`{"where": [{"description": null}]}` without a required `path`.

Evidence:
- Fixed/narrowed path: `fhir4ds/viewdef/types.py:674` through
  `fhir4ds/viewdef/types.py:680` validate nested `Select.where`.
- Still-open path: `fhir4ds/viewdef/types.py:1011` through
  `fhir4ds/viewdef/types.py:1012` copy root `ViewDefinition.where` with
  `dict(condition)` and no call to `validate_where_conditions()`.
- Shared validator: `fhir4ds/viewdef/types.py:148` through
  `fhir4ds/viewdef/types.py:191`.

The root serializer should normalize/validate `ViewDefinition.where` through
the same shared helper before emitting official JSON.

## Carried-Forward Open Findings

### REV-001 - HIGH - Native FHIRPath Section 5.1 arity validation remains incomplete

Carried from review-45. Native `evalFunction` still needs exact arity guards for
collection helpers such as `exists`, `all`, `subsetOf`, `supersetOf`, `count`,
`empty`, `distinct`, `isDistinct`, `hasValue`, and Boolean aggregates.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` accepts invalid resource-backed DateTime strings

Carried from review-45. Route native resource-backed timestamp strings through
the strict DateTime parser or enforce identical range rules before returning.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Carried from review-45. Native and fallback typed wrappers should require
finite JSON-numeric `value` plus string `unit` or `code`, not only
Quantity-like shape.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` use incomplete local case tables

Carried from review-45. Replace hand-maintained native mappings with generated
Unicode data or a Unicode-aware library path, then parity-test one-to-one and
one-to-many mappings.

### REV-005 - MEDIUM - FHIR model/type knowledge remains embedded in generic FHIRPath runtime code

Carried from review-45. Native FHIRPath still embeds field primitive metadata
and type hierarchy logic that should come from generated/shared model metadata.

### REV-006 - MEDIUM - FHIRPath string/STU helper arity validation remains incomplete

Carried from review-45. Add exact signatures for `trim`, `split`, `join`,
`matchesFull`, `escape`, `unescape`, `encode`, and `decode`.

### REV-007 - HIGH - Qualified ValueSet references from included CQL libraries lower to missing CTEs

Carried from review-45. Resolve `Lib.ValueSetName` through included terminology
symbols or raise a clear translation error instead of synthesizing
`SELECT * FROM "Lib.ValueSetName"` for unknown symbols.

### REV-008 - HIGH - Generic CQL ValueSet membership embeds QICore-specific behavior

Carried from review-45. Move `qicore-notDoneValueSet` behavior out of generic
Python/native terminology membership and behind a profile/IG adapter or
registry-driven configuration.

### REV-030-002 - HIGH - Decimal `HighBoundary` / `LowBoundary` mishandle negative values and coarser precision

Carried from review-45. Decimal boundary helpers still need sign-aware
arithmetic/quantization for negative values and requested precision lower than
the authored scale, with parity coverage across translated SQL, Python
fallback, native-loaded, and no-Python extension surfaces.

## Closed Since Review-45

No complete carried-forward finding was verified closed by SOF-VD-04 through
SOF-VD-08. `REV-045-002` was partially remediated for nested `Select.where`
serialization, but remains open for root `ViewDefinition.where`.

## Validation Context

This read-only review ran focused Python probes only; it did not rerun full
conformance. Current `spec_schedule.json` shows 50 completed chunks, all
passed, with 207 bugs found, 207 fixed, and zero open chunk bugs. The latest
SOF-VD-08 pass reported full conformance 2822/2822.
