# Architect Handoff — SOF-VD-12 / EXPLORER (fresh rerun, 2026-07-03)

**Spec**: SOF-VD-12 — Profiling/metadata pathological-input probe.
**Iteration**: 1.
**Open issues**: 0.

## Audit Summary

- **Golden Standard**: profile activation and metadata handling must
  correctly enforce Shareable/Tabular rules, preserve canonical URLs,
  reject malformed profile arrays, ignore unsupported mapping, reject
  XML input, and leave execution unchanged when metadata is added.
- **Implementation review**: 11/12 pathological probes pass. E7 failure
  was a hypothesis error — Tabular correctly enforces its 18-primitive
  allowlist (`TABULAR_PRIMITIVE_TYPE_NAMES`), and `date` is not in it.
  No data corruption, no crashes, no metadata leaks into execution.
- **EXPLORER QA quality**: 12 distinct pathological inputs including
  unicode URLs, large profile arrays, type-allowlist boundaries, and
  metadata-execution independence. Failure investigated before dismissal.
  **RETRY_QA: false.**
- **Regression check**: ViewDefinition pytest 1055/1055 PASS.

## Recommended Fix Order for Engineer

None — no open issues.

## Global Knowledge Update

- Add to NOT-A-BUG Registry: TabularViewDefinition enforces a specific
  18-primitive allowlist (`TABULAR_PRIMITIVE_TYPE_NAMES` in
  `fhir4ds/viewdef/types.py`). `date` alone is NOT in the list (Tabular
  uses `dateTime`); `integer64`, `oid`, `uuid`, `markdown`, `url`,
  `canonical`, `code`, `id`, `base64Binary`, `boolean`, `decimal`,
  `instant`, `integer`, `positiveInt`, `string`, `time`, `unsignedInt`
  are. Future probes must use Tabular-allowed primitives only.
