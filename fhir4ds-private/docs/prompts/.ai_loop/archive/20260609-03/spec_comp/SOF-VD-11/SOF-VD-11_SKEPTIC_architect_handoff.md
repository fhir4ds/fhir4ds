# Architect Handoff - SOF-VD-11/SKEPTIC

Structural audit result: PASS. No retry QA required.

Golden standard:
- Written at `.temp/architect/golden_standard.md`.
- Core invariants: ViewDefinition runner SQL must preserve root resource filtering and typed columns; native C++ and forced Python fallback must agree for supported official runner examples; JSON primitive numeric text/value and FHIR primitive metadata must survive member access; root-level and chained collection operators must share evaluator semantics.

QA quality audit:
- QA was sufficient. It did not stop at happy paths: it used a fresh shared-table DuckDB probe, concrete Patient/Observation rows, Patient.address unrolling, filtered Observation execution, decimal type coercion, native/fallback comparison, and a full local official spec_tests sweep. That sweep found the native failures later remediated.

Issue status:
- `SOF-VD-11-SKEPTIC-001` is VERIFIED. The original decimal boundary mismatch expanded into the same runner-parity root class: JSON decimal scale loss, JSON-backed numeric boundary value loss, FHIR `date`/`dateTime`/`time` boundary coercion gaps, and missing root-level native `where(criteria)` dispatch.

Architecture assessment:
- The fix is localized to native FHIRPath evaluator semantics and paired with ViewDefinition runner tests. The ViewDefinition generator/parser surface was not broadened or special-cased for fixtures.
- The added behavior is general: it preserves primitive metadata at the evaluator boundary and routes top-level `where` to the existing filtering implementation.
- Durable knowledge was updated in ViewDefinition, FHIRPath, native extension AGENTS notes, and compact global knowledge.

Validation:
- Fresh SOF-VD-11 probe: native/fallback custom runner cases passed; native/fallback official spec_tests `134/134`.
- Focused regressions: `4 passed`.
- ViewDefinition pytest: `976 passed`.
- FHIRPath environment/type parity: `11 passed`.
- ViewDefinition conformance: `134/134`.
- Full conformance: ViewDefinition `134/134`, FHIRPath `935/935`, CQL `1706/1706`, DQM `47/47`, overall `2822/2822`.

Recommended next action:
- Clean exit for this bounded SOF-VD-11/SKEPTIC pass. Do not initialize another personality/chunk here; the outer orchestrator owns archive and schedule updates.
