# Architect Handoff: SOF-VD-05 / SKEPTIC

## Golden Standard

Nested `ViewDefinition.select.select` must be treated as the same recursive
selection structure at every depth. Parser, serializer, direct dataclass, and
SQL generation boundaries must share container validation. Child selects must
inherit parent iterator focus, no-iterator children must keep the current
`$this` focus, parent/child rows must repeat parent bindings, sibling rowsets
must compose by Cartesian product, and duplicate output names must be rejected
recursively while valid `unionAll` branch schemas remain compatible.

## Audit Result

No architectural findings were logged. QA was sufficiently adversarial for the
SOF-VD-05 SKEPTIC scope: it attacked malformed nested containers, direct
dataclass bypasses, native/fallback execution, recursive context inheritance,
default `$this`, row multiplication, duplicate names, deep recursion, and empty
nested select behavior. No QA retry is needed.

## State Hygiene

- Issues in `evolution.json`: 0
- Open CRITICAL/HIGH/MEDIUM issues: 0
- `ARCHIVE_LOG.md`: not modified, per hard stop boundary and because there are
  no issue details to archive.

## Validation

- Fresh probe: `.temp/qa/sof_vd05_skeptic_probe.py` PASS
- Focused parser/generator/foreach/union/integration pytest: 353/353 passed
- Official ViewDefinition spec compliance pytest: 435/435 passed
- Full conformance: 2822/2822 passed

## Changed Files

- `fhir4ds/viewdef/AGENTS.md`
- `.temp/qa/sof_vd05_skeptic_probe.py`
- `.temp/qa/sof_vd05_skeptic_conformance_summary.log`
- `.temp/architect/golden_standard.md`
- `.ai_loop/evolution.json`
- `.ai_loop/qa_handoff.md`
- `.ai_loop/engineer_handoff.md`
- `.ai_loop/architect_handoff.md`
- `.ai_loop/GLOBAL_KNOWLEDGE.md`

## Recommended Fix Order

No fixes are required for this pass. Continue with the outer orchestrator
archive/finalization, then run SOF-VD-05 HISTORIAN.
