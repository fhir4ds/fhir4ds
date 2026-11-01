# QA Handoff: FP-02 EXPLORER

Scope: FHIRPath §4.2 operators, §4.3 function invocation, §4.4 null/empty propagation, and §4.5 singleton evaluation, with direct native C++ vs forced Python fallback comparison.

Spec grounding: FHIRPath Normative Release §4.4 says empty operands generally propagate for single-input operators/functions, with documented exceptions such as collection-aware functions. §4.5 defines singleton coercion and mandates an error for multi-item or incompatible singleton input. §6.8 gives the operator precedence table and explicitly states that `-7.combine(3)` is parsed as `-(7.combine(3))`, producing an error because unary negation cannot apply to a list.

Probe: `.temp/qa/fp02_explorer_probe.py` ran 45 pathological cases covering adjacent precedence, call-vs-member syntax, empty/null propagation, documented empty exceptions, and multi-item singleton row resilience. The probe isolated native and fallback backends in subprocesses.

Result: 1 native/fallback mismatch.

- `QA-001` HIGH SPEC_VIOLATION: native C++ returns `-7` for `-7.combine(3)`, while forced Python fallback returns empty/NULL and invalid. This contradicts the explicit FHIRPath §6.8 example that dot/function invocation binds before unary minus.

No source code was modified during QA. The issue is logged in `evolution.json`.
