# Design Handoff

## Plan

Final plan path:

`docs/architecture/plans/FEATURE_CQL_TESTS_RUNNER_REMEDIATION.md`

## Summary

The remediation should proceed in slices and fix behavior in the owning layer:

- parser/translator for Ratio literals and type routing;
- DuckDB UDF/macros for CQL runtime semantics;
- facade only for serialization of already-correct values;
- harness/docs for runner-owned limitations.

## Auto-Advance Note

`USER_DIRECTIVES.md` asks for design before implementation, but the latest
human chat message explicitly requested initialization and auto-advance until
all work is complete. Treat this handoff as approved for implementation in this
run.

## Validation Gate

Each slice needs local tests plus targeted `cql-tests-runner` probes. A final
full runner pass is required before completion.

