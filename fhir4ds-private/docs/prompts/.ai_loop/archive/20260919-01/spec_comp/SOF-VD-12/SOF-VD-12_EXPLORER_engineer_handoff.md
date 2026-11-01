# Engineer Handoff — SOF-VD-12 EXPLORER (3rd launch, iteration 1, 2026-08-24)

## Triage table
| Issue | Category | Triage |
|---|---|---|
| QA-001 (MEDIUM) | SPEC_VIOLATION (JSON representation round-trip) | CONFIRMED -> RESOLVED |

## QA-001 fix summary
- **Reproducer:** `parse_view_definition('...{"valueDecimal":1.2}...')` ->
  `to_dict()['constant'][0]['valueDecimal'] == Decimal('1.2')` ->
  `json.dumps(vd.to_dict())` raises TypeError; dict-input path yields float
  (path-dependent serialization type).
- **Root cause:** parser parses JSON strings with `parse_float=Decimal`
  (pinned lossless FHIRPath literal doctrine, parser.py:498);
  `Constant.to_dict` (types.py) emitted the internal Decimal verbatim at the
  public serialization boundary.
- **Spec reference:** SQL-on-FHIR v2 ViewDefinition.constant valueDecimal
  (StructureDefinition-ViewDefinition.json, ig/2.0.0) — the FHIR JSON
  representation of a decimal constant is a JSON number; chunk mandate
  "JSON representation uses official field names and round-trips through
  parser/generator inputs".
- **Fix (files changed):**
  - `fhir4ds/viewdef/types.py`: new `_json_number_value()` — to_dict emits
    int for integral Decimals, float when the float repr round-trips exactly
    (Decimal('1.2') -> 1.2), and fails fast with a typed ValueError for
    >17-significant-digit decimals (cannot be a JSON number without
    corruption — honest per the no-silent-corruption doctrine). Dataclass
    `.value` stays Decimal; generator literal substitution untouched.
  - `fhir4ds/viewdef/tests/unit/test_constants.py`: new
    `TestDecimalToDictJsonSerialization` (6 tests: JSON serializability,
    string-vs-dict path equality, integral->int, float passthrough,
    unrepresentable fails fast, dataclass value stays Decimal).

## Validation (final tree, PYTHONPATH=/mnt/d/fhir4ds)
- Reproducer probe2.py E2: PASS (11/11 probes now pass).
- Constants unit tests: 101/101.
- Viewdef pytest: 1238/1238 passed.
- ViewDef conformance: 144/144 (100.0%).
- Master gate (run_all.py): 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706,
  DQM 47) — SUCCESS, no regressions.
- Binary md5s (Python-only fix, unchanged, repo == site-packages):
  fhirpath 57d0634b6ee6eddee9fc06a1355bef5a,
  cql c5b22d58310c1eb7bafa17ce7877f989.

## New issues discovered
None.
