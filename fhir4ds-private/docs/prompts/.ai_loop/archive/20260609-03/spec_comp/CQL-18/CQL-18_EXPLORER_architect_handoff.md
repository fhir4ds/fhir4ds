# Architect Handoff - CQL-18 EXPLORER

Structural health: clean after remediation.

The fix preserves the intended CQL list boundary. `CQLIndexOf` now follows the
same tri-state element equality contract as the other list helpers: true
matches produce an index, unknown equality remains SQL NULL, and `-1` is
reserved for known absence. The translator change is also at the right layer:
row-producing query expressions are folded into list values before entering a
scalar list helper, matching the existing CQL query-as-list pattern without
embedding fixture, measure, profile, or terminology-specific logic.

Issues by category: 1 `SPEC_VIOLATION`, resolved and verified. No additional
architectural findings were logged.

QA quality: sufficient. The EXPLORER probe covered direct helper calls,
translated CQL, query-produced lists, Quantity and clinical unknown equality,
compatible controls, forced Python fallback, native-loaded registration, and
no-Python/browser-style macro execution. `RETRY_QA` is not set.

Validation accepted:

- `.temp/qa/cql18_explorer_probe.py`: PASS
- CQL list Part 1 parity: 8/8
- CQL list Part 1 + Part 2 parity: 14/14
- Official `CqlListOperatorsTest`: 212/212
- Full conformance: 2822/2822

Recommended fix order: none remaining for this pass.
