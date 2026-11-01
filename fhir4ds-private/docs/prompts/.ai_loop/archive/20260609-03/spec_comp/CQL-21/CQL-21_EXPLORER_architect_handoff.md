# Architect Handoff — CQL-21 EXPLORER

Golden standard: structured terminology values must cross all clinical boundaries with the same canonical identity. For ValueSets, that means preserving `id|version` anywhere a runtime lookup is performed.

Audit result: `CQL21-EXPLORER-001` is structurally resolved. The fix is in the correct layer: both `ExpandValueSet` macro registrations now derive the lookup key from the ValueSet value shape, while translator membership logic continues to emit canonical versioned URLs. No clinical code lists or measure-specific assumptions were added.

QA quality: adequate. The EXPLORER probe specifically prevented accidental base-URL success by loading only the versioned `valueset_codes` row and checking Python fallback, native-loaded, and no-Python runtimes.

Validation:
- `.temp/qa/cql21_explorer_probe.py`: PASS.
- Clinical operator parity pytest: 12/12.
- Official CQL conformance: 1706/1706.
- Full conformance: 2822/2822.

No retry requested. No open findings remain for this pass.
