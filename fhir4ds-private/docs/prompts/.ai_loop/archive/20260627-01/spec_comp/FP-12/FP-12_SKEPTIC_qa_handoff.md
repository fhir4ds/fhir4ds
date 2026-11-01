# QA Handoff - FP-12 SKEPTIC

Chunk: FP-12, FHIRPath §5.8 Tree Navigation and §5.9 Utility Functions.
Personality: SKEPTIC.

Spec source: HL7 FHIRPath continuous-build source, §5.8 and §5.9. The relevant normative points are:
- `children()` returns immediate child nodes, with undefined order.
- `descendants()` returns all descendant nodes excluding the input nodes and is shorthand for `repeat(children())`.
- `trace(name, [projection])` returns the input collection unchanged; when projection is supplied, it is evaluated as a scoped function for each item, setting `$this` and `$index`.
- `now()`, `today()`, and `timeOfDay()` are deterministic within one expression and exact zero-argument functions.

Hypotheses tested:
- `trace()` projection scoping may be implemented as a whole-collection argument evaluation instead of a scoped per-item projection.
- `descendants()` may drift from `repeat(children())` on duplicate scalar descendants or null children.
- `children()` may skip JSON null children despite the project invariant that navigation skips null but `children()` preserves them.
- Clock functions may change between repeated calls inside a single expression.
- Native and forced Python fallback validation may disagree on exact arity.

Finding:
- `QA-001` MEDIUM SPEC_VIOLATION is open. Fresh repro:
  `name.trace('names', given.single()).given.count() = 2` over a Patient with two `name` objects, each with one `given`, should return true. Native DuckDB/C++ returned `( [], None, true )`; forced Python fallback returned `( [], None, true )` and logged an empty trace. Both paths evaluate the projection once over the whole input collection, so `given.single()` fails across two items. Per §5.9, projection must evaluate per item and trace must still return the original input.

Artifacts:
- Fresh probe: `.temp/qa/fp12_skeptic_fresh_probe.py`.
- Initial inline repro command was run before remediation and failed as described above.

Recommended fix:
- Update Python `trace_fn` to evaluate projection once per item while setting `$this` and `$index`, restoring prior scope afterward.
- Update native C++ `trace` dispatch to evaluate projection once per input item, with `index_context_` set and scope restored, while still returning the original input.
- Add focused parity coverage for multi-item `trace(..., given.single())` and `$index.single()` projection behavior.
