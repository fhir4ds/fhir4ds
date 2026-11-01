# Engineer Handoff — FP-15 EXPLORER (2026-08-18)

## Triage
| Issue | Sev | Category | Action |
|---|---|---|---|
| QA-001 | HIGH | SPEC_VIOLATION (grammar) | FIXED |
| QA-002 | MEDIUM | SPEC_VIOLATION (R4 metadata) | FIXED |
| QA-003 | MEDIUM | SPEC_VIOLATION (R4 metadata + parity) | FIXED |
| QA-004 | LOW | SPEC_GAP_METADATA | DEFERRED (needs path-aware native metadata, ARCH-002) |

## Fixes
1. **QA-001** `extensions/fhirpath/src/fhirpath/parser.cpp` — parseTypeExpression
   changed from single-shot `if` to a left-associative `while` loop over
   `('is'|'as') typeSpecifier`. Official FHIRPath.g4 rule
   `expression ('is' | 'as') typeSpecifier #typeExpression` is left-recursive;
   chains like `A as Resource is FHIR.Patient` are valid and must associate
   LEFT. Extension rebuilt (`make fhirpath_loadable_extension`) and redeployed
   to `fhir4ds/fhirpath/duckdb/extensions/` AND user site-packages (md5
   70b25e317acc9118f1654751cfe53787 in all three locations); verified through
   a freshly loaded connection (stale-binary trap checked).
2. **QA-002/QA-003** `evaluator.cpp fhirFieldType`: `recorded` added and
   `lastUpdated` moved from dateTime to the instant branch (R4: AuditEvent/
   Provenance.recorded and Meta.lastUpdated are `instant`; instant/dateTime are
   sibling primitives). Fallback side: `".recorded": "instant"` and
   `".lastUpdated": "instant"` added to `fhir4ds/fhirpath/models/r4/
   fhir_path_to_type.json` and `fhir4ds/fhirpath/duckdb/fhir_model.py`
   (all metadata copies per ARCH-002 doctrine). Suffix keys keep name-only
   semantics identical to native — parity preserved.

## Regression tests
`fhir4ds/fhirpath/duckdb/tests/integration/test_type_parity.py`:
- `test_infix_is_as_chains_both_engines_fp15_explorer` (9 cases)
- `test_recorded_and_last_updated_typed_instant_both_engines_fp15_explorer` (7 cases)

## Validation
- New + prior FP-15 parity tests: 17 passed.
- fhirpath full pytest tree: 1918 passed.
- Full conformance: ViewDefinition 144/144, FHIRPath 935/935, CQL 1706/1706,
  DQM 47/47, OVERALL 2832/2832 — baseline held.
  Log: `.temp/qa/fp15_explorer2_2026_08_18/conformance_after_fix.log`
