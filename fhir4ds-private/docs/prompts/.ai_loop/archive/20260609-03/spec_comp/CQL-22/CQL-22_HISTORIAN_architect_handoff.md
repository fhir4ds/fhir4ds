# Architect Handoff: CQL-22 HISTORIAN

Structural result: PASS. The HISTORIAN finding was a translator-boundary bug, not a runtime-only helper bug. The corrected shape is now explicit: static CQL type evidence is validated before SQL generation, while runtime-unknown values still route through the public `CQLMessage` surface. This preserves the separation between CQL semantic validation and DuckDB execution/coercion.

Golden standard update: `.temp/architect/golden_standard.md` now includes a falsifiable invariant that `Message` signature validation belongs at the translator boundary for statically known operands.

State of issues:
- Found: 1 HIGH `SPEC_VIOLATION`
- Fixed: 1
- Verified: 1
- Open: 0

QA quality review: sufficient. The probe and parity tests covered signature rejection, condition true/false/null handling, severity behavior, null code/message, list/source preservation, translated CQL, direct helper behavior, runtime parameter severity in population SQL, and Python fallback/native-loaded/no-Python execution.

Validation accepted:
- Fresh HISTORIAN probe PASS
- `test_message_parity.py`: 8 passed
- Official CQL errors/messaging subset: 4/4
- CQL conformance: 1706/1706
- Full conformance: 2822/2822

No `RETRY_QA` is set. Per outer-orchestrator control, EXPLORER and the next chunk were not initialized, no archive step was run, and `spec_schedule.json` was not modified for this closeout.
