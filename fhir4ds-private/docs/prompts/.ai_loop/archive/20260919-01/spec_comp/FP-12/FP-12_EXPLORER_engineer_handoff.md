# Engineer Handoff — FP-12 EXPLORER iteration 1 FIX (2026-08-17)

Scope: QA-001 (HIGH) and QA-002 (MEDIUM), §5.8/§5.9 typing parity on
children()/descendants()/nested navigation.

## QA-001 (HIGH) — RESOLVED (Python fallback only; no extension rebuild needed for this half)

Root cause: `ResourceNode.get_type_info` (fhir4ds/fhirpath/engine/nodes.py)
had no field-name complex-type inference. For Mapping nodes whose path is
absent from path metadata — recursive backbone paths
(`Questionnaire.item.item`) and choice-suffixed nested paths
(`Observation.component.valueCodeableConcept.coding`) — typing fell to
value-shape inference → FHIR.object, breaking the §5.8 ofType() composition
in both direct navigation and children()/descendants(). Additionally the
curated suffix table (`models/r4/fhir_path_to_type.json`) lacked
`.type` → code, so `Questionnaire.item.type` typed string (R4: code).

Fix:
- `nodes.py`: `ResourceNode._FIELD_NAME_COMPLEX_TYPES` (name/address/
  identifier/telecom/coding/code/extension/modifierExtension → HumanName/
  Address/Identifier/ContactPoint/Coding/CodeableConcept/Extension) and
  `_BACKBONE_ELEMENT_FIELDS` {communication, component, compose, contact,
  expansion, item, link}, applied in `get_type_info` as the final Mapping
  fallback — mirroring the native `structuralFHIRComplexType` + field-name
  chains. LOCKSTEP RULE documented in-code.
- `models/r4/fhir_path_to_type.json`: added `".type": "code"` (aligned with
  native `fhirFieldType`, which already maps type→code).

## QA-002 (MEDIUM) — RESOLVED (native; extension rebuilt + redeployed)

Root cause: native `evaluator.cpp` field-name inference chains (fn_type,
is/ofType, structuralFHIRComplexType) had no entry for
`extension`/`modifierExtension`, so extension-array elements inferred
'object' for type()/ofType() while the fallback special-cases childPath
"Extension".

Fix: added extension/modifierExtension → Extension at all three inference
sites. Extension rebuilt (`make fhirpath_loadable_extension`) and deployed
identically (md5 0b8cf9e5…) to repo bundle, user site-packages, and
~/.duckdb extension caches.

## Files changed

- `fhir4ds/fhirpath/engine/nodes.py` — field-name/backbone typing fallback.
- `fhir4ds/fhirpath/models/r4/fhir_path_to_type.json` — `.type` suffix.
- `extensions/fhirpath/src/fhirpath/evaluator.cpp` — 3 extension-typing sites.
- `fhir4ds/fhirpath/duckdb/extensions/fhirpath.duckdb_extension` (+
  site-packages and ~/.duckdb caches) — rebuilt binary.
- `fhir4ds/fhirpath/duckdb/tests/integration/test_tree_utility_parity.py` —
  2 regression tests (24/24 in file).

## Validation

- Probes probe/probe2/probe3: 0 parity diffs remaining (the sole residual
  `.sum()` chain divergence is the pre-existing documented FP-02 EXPLORER
  QA-004 LOW DEFERRED unknown-function doctrine, out of chunk scope).
- test_tree_utility_parity.py: 24/24.
- Full fhirpath pytest tree: **1824 passed**.
- Full conformance: **2832/2832** (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47). No regressions.

## New issues discovered

None beyond the documented `.sum()` doctrine (not re-filed).
