# Code Review Findings

Scope: SPEC COMPLIANCE MILESTONE REVIEW after 45 completed chunks. Reviewed the
current rerun state for CQL-21, CQL-22, SOF-VD-01, SOF-VD-02, and SOF-VD-03,
with focused inspection of CQL clinical/message changes and ViewDefinition
parser/types/constants/generator/tests. This was review-only: no remediation
was implemented, no workflow was initialized, no chunk/personality files were
archived, and `spec_schedule.json` was not modified.

## New Findings From Review-45

### REV-045-001 - HIGH - Parsed root metadata still accepts present JSON null

`parse_view_definition()` passes optional root metadata through `dict.get()`,
which erases the difference between an absent field and a present JSON null.
As a result, invalid official JSON such as `{"resourceType": null}`,
`{"id": null}`, `{"url": null}`, `{"version": null}`, `{"status": null}`,
`{"title": null}`, or `{"description": null}` is accepted and then silently
omitted by serialization.

Evidence:
- `fhir4ds/viewdef/parser.py:392` through `fhir4ds/viewdef/parser.py:400`
  call `validate_root_metadata_fields()` with `data.get(...)` for each root
  metadata field.
- `fhir4ds/viewdef/types.py:1062` through `fhir4ds/viewdef/types.py:1090`
  validate those fields only when the value is not `None`.

The parser should reject present-null root metadata before calling the shared
validator, matching the newer explicit `Column.description` null check and FHIR
JSON's no-null-property rule.

### REV-045-002 - HIGH - `to_dict()` can emit invalid `where` JSON

Direct dataclass serialization validates root/select/column/constant shapes in
the recent SOF-VD-01 through SOF-VD-03 fixes, but `where` entries are still
copied verbatim. `ViewDefinition.to_dict()` and `Select.to_dict()` can emit
official JSON with missing `where.path`, non-string `where.path`, or present
`where.description: null`, even though parser and `SQLGenerator.generate()`
reject those shapes.

Evidence:
- `fhir4ds/viewdef/types.py:669` through `fhir4ds/viewdef/types.py:670` copy
  `Select.where` with `dict(condition)` and no call to
  `validate_where_conditions()`.
- `fhir4ds/viewdef/types.py:1001` through `fhir4ds/viewdef/types.py:1002` do
  the same for root `ViewDefinition.where`.
- The shared validator already exists at `fhir4ds/viewdef/types.py:146`
  through `fhir4ds/viewdef/types.py:189`.

The serializer should normalize/validate root and nested `where` with the same
helper used by parser and generator before emitting official JSON.

## CQL Clinical/Message Review

No new CQL clinical/message issues were found in this review pass. The CQL-21
changes register the missing age precision functions across Python, native, and
no-Python paths, and the CQL-22 changes keep `Message(...)` signature checks in
the translator while preserving the no-Python `CQLMessage` macro surface.

## Carried-Forward Open Findings

### REV-001 - HIGH - Native FHIRPath Section 5.1 arity validation remains incomplete

Carried from review-40. Native `evalFunction` still lacks exact arity guards
for collection helpers such as `exists`, `all`, `subsetOf`, `supersetOf`,
`count`, `empty`, `distinct`, `isDistinct`, `hasValue`, and Boolean aggregates.

### REV-002 - MEDIUM - Native `fhirpath_timestamp` still accepts invalid resource-backed DateTime strings

Carried from review-40. Native wrapper validation still checks shape before
returning resource-backed timestamp strings. Route through the strict DateTime
parser or enforce identical range rules.

### REV-003 - MEDIUM - `fhirpath_quantity` typed wrappers accept malformed Quantity objects

Carried from review-40. Native and fallback typed wrappers still accept
Quantity-like objects by shape rather than requiring finite JSON-numeric
`value` and string `unit` or `code`.

### REV-004 - MEDIUM - Native Unicode `upper()` / `lower()` still use incomplete local case tables

Carried from review-40. Replace hand-maintained native case mappings with
generated Unicode data or a Unicode-aware library path, then parity-test
one-to-one and one-to-many mappings.

### REV-005 - MEDIUM - FHIR model/type knowledge remains embedded in generic FHIRPath runtime code

Carried from review-40. Native FHIRPath still embeds field primitive metadata
and type hierarchy logic that should come from generated/shared model metadata.

### REV-006 - MEDIUM - FHIRPath string/STU helper arity validation remains incomplete

Carried from review-40. Add exact signatures for `trim`, `split`, `join`,
`matchesFull`, `escape`, `unescape`, `encode`, and `decode`.

### REV-007 - HIGH - Qualified ValueSet references from included CQL libraries lower to missing CTEs

Carried from review-40. Resolve `Lib.ValueSetName` through included terminology
symbols or raise a clear translation error instead of synthesizing
`SELECT * FROM "Lib.ValueSetName"`.

### REV-008 - HIGH - Generic CQL ValueSet membership embeds QICore-specific behavior

Carried from review-40. Move `qicore-notDoneValueSet` behavior out of generic
Python/native terminology membership and behind a profile/IG adapter or
registry-driven configuration.

### REV-030-002 - HIGH - Decimal `HighBoundary` / `LowBoundary` mishandle negative values and coarser precision

Carried from review-40. Decimal boundary helpers still need sign-aware
arithmetic/quantization for negative values and requested precision lower than
the authored scale, with parity coverage across translated SQL, Python
fallback, native-loaded, and no-Python extension surfaces.

## Closed Since Review-40

No carried-forward review-40 findings were verified closed by CQL-21, CQL-22,
SOF-VD-01, SOF-VD-02, or SOF-VD-03.

## Validation Context

This read-only review did not rerun full conformance. The current schedule
shows 45 completed chunks, all passed, with 199 bugs found and fixed and zero
open chunk bugs. The latest completed SOF-VD-03 pass reported full conformance
2822/2822.
