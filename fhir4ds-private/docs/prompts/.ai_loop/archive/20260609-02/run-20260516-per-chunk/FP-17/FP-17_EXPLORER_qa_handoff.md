# QA Handoff - FP-17 EXPLORER

## Scope

FHIRPath §6.5 Boolean Logic: `and`, `or`, `not()`, `xor`, `implies`, with §4.5 singleton Boolean evaluation.

Normative basis checked against the current FHIRPath normative release:
- §4.5: single non-Boolean nodes evaluate as `true` when Boolean input is expected; empty remains empty; multi-item collections signal an error.
- §6.5: Boolean operators use three-valued logic after singleton Boolean evaluation.
- §6.5.5: `false implies X` returns `true`; short-circuit is permitted when it does not change semantics.
- §6.8: `and` binds tighter than `or`/`xor`, and `implies` has the lowest precedence.

## EXPLORER Probes

Created temp harness: `fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp17_explorer_probe.py`.

Fresh pathological cases covered:
- Nested and chained Boolean expressions: `active and (gender or {})`, `active and gender xor deceasedBoolean`, `active implies deceasedBoolean implies active`.
- Singleton non-Boolean truthiness: string, numeric, and object path operands; `obj.not()`, `zero.not()`, `two and active`.
- Empty/null propagation: `nul and true`, `nul or false`, `(nul | active) and true`.
- Multi-item operand boundaries: `contact.telecom.value implies true`, `objects or true`, `objects and false`, `objects.not()`.
- Intentional implication short-circuit: `false implies contact.telecom.value`, `false implies objects`.

Important harness note: executing the temp script by path without `PYTHONPATH=/mnt/d/fhir4ds` imported a stale installed package and produced false failures. With `PYTHONPATH` pinned to the checkout, native, forced fallback, and direct Python UDF probes passed.

## Results

No confirmed product issues.

No changes needed to source, tests, AGENTS.md, GLOBAL_KNOWLEDGE.md, or ARCHIVE_LOG.md from QA.

## Validation Run By QA

- `PYTHONPATH=/mnt/d/fhir4ds python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp17_explorer_probe.py native` -> passed, 23 cases.
- `PYTHONPATH=/mnt/d/fhir4ds python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp17_explorer_probe.py fallback` -> passed, 23 cases.
- `PYTHONPATH=/mnt/d/fhir4ds python3 fhir4ds-private/docs/prompts/.ai_loop/.temp/qa/fp17_explorer_probe.py direct` -> passed, 23 cases.
- `python3 -m pytest fhir4ds/fhirpath/duckdb/tests/integration/test_boolean_logic_parity.py fhir4ds/fhirpath/duckdb/tests/integration/test_operator_parity.py -q` -> 52 passed in 11.67s.
