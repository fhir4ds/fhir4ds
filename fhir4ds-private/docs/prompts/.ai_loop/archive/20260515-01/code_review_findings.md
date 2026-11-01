# Code Review Findings

Scope:
- `extensions/fhirpath/src/fhirpath_extension.cpp`
- `extensions/fhirpath/src/fhirpath/parser.cpp`
- new FHIRPath DuckDB integration tests
- rebuilt bundled FHIRPath DuckDB extension

Findings:
- No blocking security, correctness, or implementation findings.

Review notes:
- `FhirpathNumberFunction` now uses `ResolveJsonPath(...)` for simple numeric paths, which preserves flattened collection semantics before scalar emission. Numeric values are copied before `yyjson_doc_free(doc)`, and non-numeric or multi-item cases fall through to the full evaluator/scalar gate.
- Standalone `extension(...)` now parses as `NodeType::ExtensionCall`, matching source-qualified `.extension(...)` dispatch without evaluator special-casing.
- Regression coverage exists for both fixed surfaces: `test_number_fastpath_parity.py` and `test_extension_parity.py`.
- Build/validation commands modified generated files (`conformance/reports/dqm_report.json`, extension clangd cache files). These are not product-code findings, but they should be cleaned or intentionally kept before commit.

Validation reviewed:
- Focused FHIRPath parity: 13/13 passed.
- Native FHIRPath C++ SQL suite: 110 assertions passed.
- Final full conformance: ViewDefinition 134/134, FHIRPath 935/935, CQL 1706/1706, DQM 47/47, overall 2822/2822.
