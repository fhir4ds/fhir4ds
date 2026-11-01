# Architect Handoff — SOF-VD-12 EXPLORER (3rd launch, iteration 1, 2026-08-24)

## Structural health: SOUND
This launch's delta is one boundary fix plus tests; the prior launches'
profile-enforcement architecture (metadata.py canonical alias sets ->
types.py validate_supported_view_profiles via _iter_select_columns recursion;
extra_fields verbatim round-trip bag) held up under the EXPLORER's full
CanonicalResource-breadth and combined-profile pressure. No architectural
drift found.

## Audit of this launch's fix (QA-001)
- Placement correct: normalization lives at the serialization boundary
  (`Constant.to_dict`), not in the parser or generator; the lossless Decimal
  doctrine on the dataclass (generator FHIRPath literal substitution) is
  untouched — exactly the right layer split.
- General, not test-specific: handles the class (any Decimal constant), not
  just the reproducer; integral/fractional/overprecision branches are each
  principled and documented.
- No silent fallback: overprecision (>17 significant digits) fails fast with
  a typed ValueError instead of silently corrupting through float —
  consistent with the no-silent-fallbacks invariant.
- Minimal footprint: one helper + one call-site change; 6 focused regression
  tests. No public API breakage (to_dict previously crashed under json.dumps
  for the affected class; direct Decimal consumers of `.value` unaffected).

## Issue counts
CRITICAL 0 | HIGH 0 | MEDIUM 1 (RESOLVED) | LOW 0. Open issues: 0.

## QA Enforcer Gate: PASSED (no retry)
EXPLORER coverage matched the chunk mandate breadth: full canonical metadata
round-trip (useContext all value shapes, identifier+assigner, contact+photo,
contained, nested extensions, mapping comment/commenti), combined
Shareable+Tabular with nested unionAll (rule firing + error clarity),
status/version/date shapes, XML rejection quality in all forms, official
example byte fidelity, meta.profile canonical variants, end-to-end execution
with native==fallback parity. Probes: .temp/qa/sof_vd12_explorer/.

## Compressed handoff
QA found 1 MEDIUM (Constant valueDecimal broke json.dumps(to_dict()) and
made output type input-path-dependent); Engineer fixed it via
types.py::_json_number_value with 6 regression tests; all gates green
(viewdef pytest 1238/1238, ViewDef 144/144, master 2832/2832; extension
md5s unchanged, repo == site-packages). New NOT A BUG pins: empty-string
meta.profile canonical rejected; top-level ViewDefinition.profile never
triggers profile enforcement. State pruned; QA-001 details archived.

## Exit
Clean exit at iteration 1 (= min_iterations); zero non-terminal issues.
exit_reason=CLEAN, workflow=null. Control returns to the outer spec
compliance orchestrator.
