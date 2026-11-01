# QA Handoff - FP-12 EXPLORER

## Scope

Fresh run for SPEC COMPLIANCE CHUNK FP-12, `qa_personality=EXPLORER`.
Focused on FHIRPath §5.8 Tree Navigation and §5.9 Utility Functions:
`children()`, `descendants()`, `trace(name, [projection])`, `now()`,
`timeOfDay()`, and `today()`.

Spec source: HL7 FHIRPath continuous build
`https://raw.githubusercontent.com/HL7/FHIRPath/refs/heads/master/input/pages/index.md`.

## Normative Basis

- §5.8 says `children()` returns all immediate child nodes of the input items.
- §5.8 says `descendants()` excludes the input items and is shorthand for
  `repeat(children())`.
- The §5.8 `children()` example explicitly notes that a FHIR primitive datatype
  such as `Patient.gender` may have value, id, and extension children.
- §5.9 says `trace(name, projection)` evaluates projection per input item with
  `$this` and `$index`, returns the original input, and evaluates `name` before
  the projection loop.
- §5.9 says `now()`, `timeOfDay()`, and `today()` are deterministic within one
  expression.

## Exploration Performed

- Compared bundled native DuckDB/C++ registration against forced Python
  fallback registration.
- Re-probed post-FP-12 SKEPTIC trace projection scoping with multi-item
  `name.trace('names', given.single())`, dynamic trace labels, and `$index`.
- Re-probed utility arity and deterministic current-time helpers.
- Abused tree navigation with FHIR primitive extension metadata represented by
  sibling `_birthDate` and `_given` JSON fields.

## Finding

### QA-001 - MEDIUM - SPEC_VIOLATION - OPEN

FHIR primitive element extension metadata is not exposed through
`children()`/`descendants()`, and native C++ also misses nested primitive
`extension(url)` lookup.

Current source evidence from `.temp/qa/fp12_explorer_fresh_probe.py`:

- `birthDate.children().where(url = '.../birth-note').valueString`
  returned empty in both native and fallback; expected `["midday"]`.
- `birthDate.descendants().where($this = 'midday').count()` returned `0` in
  both native and fallback; expected `1`.
- `name.given.children().where(url = '.../given-note').valueString`
  returned empty in both native and fallback; expected `["alias"]`.
- `name.given.descendants().where($this = 'alias').count()` returned `0` in
  both native and fallback; expected `1`.
- `name.given.extension('.../given-note').valueString` returned empty in native
  but `["alias"]` in fallback; expected native/fallback parity.

## Validation Run

```bash
python3 .temp/qa/fp12_explorer_fresh_probe.py
```

Result: failed as expected for `QA-001`. Trace projection, invalid arity, and
current-time determinism checks are included in the same probe and are not the
logged failure.

## Handoff To Engineer

Fix tree navigation for primitive FHIR metadata in both Python fallback and
native C++:

- For primitive nodes carrying sibling `_field` metadata, `children()` should
  expose metadata child nodes such as `extension` and `id`.
- `descendants()` should pick those up via the same `children()` projection.
- Native nested primitive `extension(url)` should use the primitive's owning
  shadow metadata, not only root-level `_field` lookup.
- Preserve the existing post-SKEPTIC `trace(name, projection)` behavior.
