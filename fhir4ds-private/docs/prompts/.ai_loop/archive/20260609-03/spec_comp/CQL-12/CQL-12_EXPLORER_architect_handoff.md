# Architect Handoff - CQL-12 EXPLORER

Structural audit result: passed with no additional open findings.

Golden standard written to `.temp/architect/golden_standard.md`. The relevant
invariants are that CQL query expressions used as list values must be adapted
before public list/string macros, and CQL strings embedded into generated
FHIRPath must be escaped with FHIRPath literal rules before `SQLLiteral`
performs SQL serialization.

The two QA findings were real and are now verified. `QA-001` fixed a layer
mismatch where a row-producing query entered `Combine`/`CombineSep` instead of
a DuckDB list. `QA-002` fixed generated FHIRPath predicate construction so
`ext(element, url)` and related extension/code predicate builders do not let
escaped CQL quotes become executable FHIRPath. The fix is general: a shared
FHIRPath literal escaper now covers extension lowering, profile-registry paths,
the FHIRPath builder, extension URL existence checks, and direct code-filter
predicate builders.

QA quality: sufficient for EXPLORER. It tested unusual string compositions,
dynamic FHIR string paths, no-Python/native/fallback helper surfaces, regex
guards, and string-derived FHIRPath injection. `RETRY_QA` is not set.

Validation confirmed after the final patch:

- `.temp/qa/cql12_explorer_probe.py` passed.
- Focused string parity pytest passed 7/7.
- Official CQL string operator subset passed 81/81.
- Full conformance passed ViewDefinition 134/134, FHIRPath 935/935, CQL
  1706/1706, DQM 47/47, overall 2822/2822.

