# Engineer Handoff — SOF-VD-03, iteration 1

## Triage
| Issue | Category | Severity | Action |
|---|---|---|---|
| QA-001 | DOC_ACCURACY (misleading warning) | LOW | FIXED |
| QA-002 | ERROR_MESSAGE_QUALITY | LOW | DEFERRED (spec-silent; guard restructuring out of minimal footprint; error IS raised) |

## QA-001 fix
- File: `/mnt/d/fhir4ds/fhir4ds/viewdef/generator.py` (preflight warning in permissive mode).
- Warning text changed from "only the first will be used" (claims silent truncation that does not exist) to "the runtime guard will raise an error if multiple values are actually produced" — matches SQL-on-FHIR v2 Select.column.collection SHALL.
- Focused test: `TestCollectionPreflightWarning::test_multivalue_warning_states_runtime_error_not_truncation` in `/mnt/d/fhir4ds/fhir4ds/viewdef/tests/unit/test_generator.py`.

## QA-002 deferral rationale
Runtime guard emits one SQL boolean combining cardinality + type conditions; a single message cannot say which fired. Behavior is spec-compliant (error raised). Distinguishing requires splitting guard conditions — net-new restructuring for a wording nit; suite pins fragments at test_duckdb.py:386/755/757/866.

## Validation (FINAL tree)
- viewdef pytest package: 1171 passed.
- ViewDefinition conformance: 144/144.
- Master gate: 2832/2832 (ViewDef 144, FHIRPath 935, CQL 1706, DQM 47) — baseline held.
- Extension binary md5 57d0634b6ee6eddee9fc06a1355bef5a, matched repo bundle vs ~/.local site-packages (no native changes this launch; Python-only fix).
