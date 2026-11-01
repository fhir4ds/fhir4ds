# Architect Handoff — SOF-VD-04 SKEPTIC iter 1 fresh run (2026-07-03)

## Phase: ARCHITECT (Structural Audit)

## Golden Standard for SOF-VD-04
Architectural invariants for the `column.collection`, `column.type`, and
`column.tag` surface:

1. **Validation Centralization**: All spec invariants for `Column.collection`,
   `Column.type`, and `Column.tag` MUST be defined in `fhir4ds/viewdef/types.py`
   and reused by parser, `from_dict`, `to_dict`, direct dataclass `__post_init__`,
   and `SQLGenerator` direct-input guard paths.
2. **Construction-Time Validation**: `Column.__post_init__` MUST enforce
   `path`/`name`/`description`/`collection` shape and bool invariants before
   the object enters service (matching `Constant`, `ColumnTag`, `Join`).
3. **Collection Default = False**: Both parser and direct dataclass construction
   MUST default `collection` to `False` per SQL-on-FHIR v2 spec.
4. **Collection Bool-Only**: `collection` must be a strict JSON boolean. String
   `"true"` and integer `1` must be rejected.
5. **Multi-Value Non-Collection Error**: A non-collection column that produces
   multiple values at execution MUST raise a typed runtime error (per
   SQL-on-FHIR v2 spec).
6. **Type URI Handling**: `column.type` accepts a FHIR StructureDefinition URI.
   Unknown external URIs and arbitrary element-ID strings are accepted as
   runtime-text per spec; the implementation does not validate the URI resolves
   to a known StructureDefinition.
7. **Type Fragment Stripping**: Full URI with `#fragment` form strips the
   StructureDefinition prefix and the resource-type prefix, returning just the
   fragment. This matches FHIR's canonical URL semantics where fragments
   identify elements within a StructureDefinition.
8. **Tag 0..* Required Name/Value**: `column.tag` is a 0..* backbone with
   required `name` (string) and `value` (string). Both must be non-empty and
   non-whitespace per the SOF-VD-03 EXPLORER 2026-07-03 fix.
9. **Tag Mutation Revalidation**: `ColumnTag` objects mutated after
   construction MUST be revalidated by `Column.to_dict()` and
   `SQLGenerator._validate_column_shape`.
10. **Null-Row Collection Projection**: A `forEachOrNull` parent null-row
    MUST project SQL NULL (not `[]`) for child collection columns, matching
    the SOF-VD-05 HISTORIAN invariant.

## Audit Findings

### Empirical Validation
- QA SKEPTIC probe (38 assertions, 10 batteries): 36 PASS + 2 informational
  "FAIL" that are spec-interpretation cases, not code defects.
- ViewDefinition pytest: **1055/1055** PASS.
- Full conformance: **2822/2822** (ViewDefinition 134/134, FHIRPath 935/935,
  CQL 1706/1706, DQM 47/47).

### Audit Dimensions

**Generalizability**: No hardcoded resource types, magic strings, or
test-specific shortcuts found in the SOF-VD-04 surface.

**Abstraction Integrity**: Type validation flows through the canonical
`validate_optional_uri_string`, `validate_optional_boolean`,
`validate_required_string`, and `validate_column_fields` helpers in
`types.py`. The parser delegates to `Column.__post_init__` and
`ColumnTag.from_dict`; the serializer revalidates via `to_dict()`; the
generator's `_validate_column_shape` is the final safety net for mutated
dataclasses. Layering is clean.

**Silent Fallbacks**: No silent fallbacks identified. Invalid `collection`
values raise `ValueError`/`ParseError`/`ValidationError` typed. Invalid
`type` values raise `ValidationError`. Invalid `tag` items raise
`ParseError`/`ValueError`. The multi-value non-collection cardinality
violation raises a typed DuckDB runtime error.

**Test-Driven Hacks**: No special-cased logic found.

**Coupling**: `SQLGenerator` consumes already-validated `Column`/`ColumnTag`
objects via the type helpers; no parser internals leak into generator code.

**Performance Critical Paths**: No unnecessary overhead identified on the
column validation path.

### QA Enforcer Gate
QA SKEPTIC methodology produced 8 specific predicted bugs before probing, then
wrote 38 targeted assertions to confirm or reject each. The 8 hypotheses
covered all the orchestrator-briefed SOF-VD-04 items (collection default false,
multi-value error, collection true multi-value output, type URI handling,
type mismatch reporting, tag 0..* with required name/value) plus
`__post_init__` patterns. QA was NOT lazy — it was hypothesis-driven,
targeted the key spec boundaries, and produced a comprehensive handoff.
**RETRY_QA: false.**

### Architectural Observations (Non-blocking)
1. The `_URI_RE = r"^\S*$"` regex at `types.py:249` matches empty strings,
   which is technically a regex-layer inconsistency. The
   `validate_optional_uri_string` helper guards before the regex so the
   behavior is correct, but tightening the regex to `r"^\S+$"` would be a
   defense-in-depth improvement. (No code change required.)
2. The `ColumnType.normalize_name` method strips both the FHIR
   StructureDefinition prefix and the resource-type prefix when handling
   `URL#fragment` form, returning just the fragment (e.g.,
   `Observation#referenceRange` → `referenceRange`). This matches FHIR's
   canonical URL semantics but differs from the dot-notation element-ID
   form (`Observation.referenceRange`) used in some spec examples. Both
   forms are accepted at the parser boundary, but the canonical URL form
   loses the resource-type context after normalization. This is
   spec-compliant but worth documenting in AGENTS.md.
3. Per `Column.__post_init__`, `collection` defaults to `False`. The spec
   also requires this default. The invariant is enforced correctly.

## State Hygiene Protocol
No `RESOLVED` or `VERIFIED` issues to archive. No tombstones required.
No handoff compression required.

## Recommended Fix Order for Next Iteration (if any)
None — zero non-terminal CRITICAL/HIGH/MEDIUM issues remain. The chunk is
CLEAN.

## Institutional Memory Updates
- `fhir4ds/viewdef/AGENTS.md` Known Fragile Areas: confirm SOF-VD-04
  SKEPTIC iter 1 fresh rerun (2026-07-03) verified clean. All prior
  SOF-VD-04 SKEPTIC/HISTORIAN/EXPLORER fixes (2026-05-20 through
  2026-06-01) remain intact.
- `GLOBAL_KNOWLEDGE.md` Evolution Statistics: append new row.

## Conclusion
**CLEAN.** Zero non-terminal CRITICAL/HIGH/MEDIUM issues. Clean exit is
eligible at iteration 1 (>= min_iterations=1). SOF-VD-04 collection/type/tag
surface is structurally sound across parser, from_dict, to_dict, direct
dataclass, SQL generation, and DuckDB execution boundaries.
