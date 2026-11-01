# Design Handoff

Final plan: `docs/architecture/plans/FEATURE_WASM_CQL_COMPLETE_PARITY.md`

The loop has been initialized and routed through feature design for the stricter
goal: every CQL expression/library supported by the Python translator must run
in DuckDB-WASM using only C++ DuckDB extensions, SQL macros, and DuckDB builtins.

Key refinement from self-audit:

- The previous browser-demo surface is not enough.
- The next implementation must start with a generated emitted-function
  inventory and a strict no-Python translate-and-execute harness.
- Exact Python/C++ UDF name comparison is only a discovery signal; final gates
  must reason from translator-emitted names and runtime catalog availability.
- `_PYTHON_PREFERRED_CPP_CONFLICTS` is treated as unresolved semantic parity
  work for any translator-required function.
- Final acceptance requires full pytest, C++ SQL suites, Playwright browser
  tests, release artifact refresh where relevant, and 100% conformance across
  ViewDefinition, FHIRPath, CQL, and DQM.

The feature design workflow is complete. Implementation must wait for human
approval.
