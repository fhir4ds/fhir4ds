# Architect Handoff — FP-12 EXPLORER iteration 1 (2026-08-17)

## Iteration summary (compressed)

QA (EXPLORER, 123 fresh dual-path cases in
`.temp/qa/fp12_explorer3_2026_08_17/probe{,2,3}.py`) filed 2 issues: QA-001
(HIGH) fallback lost FHIR typing on metadata-miss nested paths (recursive
backbones `Questionnaire.item.item`, choice-nested
`component.valueCodeableConcept.coding`, plus missing `.type`→code suffix);
QA-002 (MEDIUM) native failed to type `extension`/`modifierExtension`
elements as FHIR.Extension for type()/ofType(). FIX resolved both at the
typing-resolution layer: fallback gained a field-name complex-type table +
curated backbone-field set in `ResourceNode.get_type_info` mirroring the
native chains (lockstep rule documented), `.type`→code added to
`fhir_path_to_type.json`; native gained extension/modifierExtension→
Extension at all three inference sites (fn_type, is/ofType,
structuralFHIRComplexType), extension rebuilt and redeployed (md5
0b8cf9e5…). 2 dual-path regression tests added (24/24 in the parity file).
Validation: probes 0 parity diffs (sole residual is the pre-documented FP-02
`.sum()` unknown-function doctrine, out of scope); full fhirpath tree 1824
passed; conformance 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47).

## Audit findings (Golden Standard: .temp/architect/golden_standard_fp12_explorer3_iter1.md)

- Invariant 1 (lockstep): PASS — both fixes mirrored across engines with
  dual-path parity tests.
- Invariant 2 (no hacks): PASS — tables are general field-name classes.
- Invariant 3 (binary currency): PASS — repo bundle / site-packages /
  ~/.duckdb caches identical md5.
- Invariant 4 (baseline): PASS — 2832/2832, no regressions.
- Invariant 5 (root cause): PASS — fixes at the typing-resolution layer.
- Invariant 6 (data-driven curation): PASS with note — the nodes.py tables
  widen the pre-existing REV-002 hand-maintained metadata-pair family; the
  inline LOCKSTEP rule mitigates; long-term generation from models/r4
  remains the structural fix.
- Invariant 7 (error-message contract): N/A — no new error messages.

## Structural issues by category

CRITICAL 0 / HIGH 0 / MEDIUM 0 / LOW 0 (new). No new architecture drift.

## QA Enforcer Gate

QA performance: GOOD — adversarial coverage matched the EXPLORER brief
(deep recursion, wide trees, choice-type matrices, trace scope chains,
now/today arithmetic), findings were isolated with control anchors, spec
citations verified against live N1 text. No RETRY_QA.

## Recommended fix order

None — no open issues. Clean exit at iteration 1 (min 1, max 3); chunk
FP-12 tally now SKEPTIC 2, HISTORIAN 4, EXPLORER 2 fixes.
