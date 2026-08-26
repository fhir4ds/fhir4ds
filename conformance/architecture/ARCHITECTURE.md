# FHIR4DS Architecture

**Version**: 2.1.0
**Date**: 2026-04-10
**Status**: Unified Namespace Reorganization Complete

---

## Overview

FHIR4DS (FHIR for Data Science) is a unified suite of high-performance libraries for querying and analyzing FHIR data using DuckDB. The architecture centers on native FHIRPath evaluation within DuckDB via a high-performance C++ extension and vectorized Python UDFs.

---

## Core Design Principle

**UDF-Driven Evaluation** - Instead of complex transpilation to pure SQL, we evaluate FHIRPath and CQL logic directly within the DuckDB engine. This approach:

- **Accuracy**: Provides 100% FHIRPath R4 coverage and full CQL specification compliance.
- **Performance**: Leverages DuckDB's vectorized engine and Arrow UDFs for high-speed batch processing.
- **Simplicity**: Keeps the generated SQL readable and easier to debug.

---

## Unified Library Structure

The project is organized under a single `fhir4ds` namespace using a **Feature-First** hierarchy.

```
── fhir4ds/                      # Unified package root
   ├── fhirpath/                 # Core FHIRPath (from fhirpath-py)
   │   └── duckdb/               # DuckDB FHIRPath adapter (from duckdb-fhirpath-py)
   ├── cql/                      # Core CQL (from cql-py)
   │   └── duckdb/               # DuckDB CQL adapter (from duckdb-cql-py)
   ├── viewdef/                  # SQL-on-FHIR v2 (from sql-on-fhir-py)
   └── dqm/                      # Digital Quality Measures (from dqm-py)
```

### Library Components

| Subpackage | Purpose | Import Example |
|------------|---------|----------------|
| `fhir4ds.fhirpath` | Core FHIRPath R4 engine | `from fhir4ds.fhirpath import evaluate` |
| `fhir4ds.fhirpath.duckdb` | FHIRPath DuckDB integration | `from fhir4ds.fhirpath.duckdb import register_fhirpath` |
| `fhir4ds.cql` | CQL translator and high-level evaluator | `from fhir4ds.cql import evaluate_measure` |
| `fhir4ds.cql.duckdb` | CQL-specific DuckDB UDFs | `from fhir4ds.cql.duckdb import register` |
| `fhir4ds.viewdef` | SQL-on-FHIR v2 generator | `from fhir4ds.viewdef import generate_view_sql` |
| `fhir4ds.dqm` | Measure audit and orchestration | `from fhir4ds.dqm import DQMOrchestrator` |

---

## Execution Layers

1. **Top-Level API**: Unified entry points in `fhir4ds/__init__.py` (e.g., `create_connection()`, `evaluate_measure()`).
2. **Feature Adapters**: Subpackages like `cql` and `viewdef` generate optimized SQL targeting the UDF layer.
3. **UDF Layer (DuckDB)**:
   - **C++ Extension**: Pre-compiled binaries (`.duckdb_extension`) for native FHIRPath performance.
   - **Vectorized UDFs**: Arrow-based Python functions for complex logic (e.g., `AgeInYears`).
   - **SQL Macros**: Inlined SQL expressions for zero-overhead simple operations.
4. **Core Engines**: Pure Python implementations of FHIRPath and CQL parsing used for validation and standalone evaluation.

---

## Data Flow: CQL Measure Evaluation

```
┌────────────┐     ┌────────────┐     ┌───────────┐     ┌───────────┐     ┌──────────────────┐
│ CQL Source │ ──▶ │ CQL Parser │ ──▶ │  CQL AST  │ ──▶ │  SQL AST  │ ──▶ │ DuckDB SQL       │
│ (.cql)     │     │            │     │           │     │           │     │ + Extensions     │
└────────────┘     └────────────┘     └───────────┘     └───────────┘     └──────────────────┘
```

---

## Error Handling Philosophy

**Mode**: Permissive and Specification-Compliant.

- **Non-Breaking**: Invalid FHIRPath expressions return empty results per the spec rather than raising exceptions.
- **Reporting**: Detailed warnings are logged during translation and registration.
- **Fallback**: The DuckDB integration automatically falls back to the Python UDF if the C++ extension binary is missing or incompatible.

---

## Development & Maintenance

- **Subpackage Independence**: While unified under `fhir4ds`, subpackages like `fhirpath` and `cql` maintain their own internal test suites in `tests/` directories.
- **Build System**: Managed via `hatchling` with custom build hooks in `hatch_build.py` to bundle multi-platform C++ binaries.
- **Compliance Baseline**: Continuously verified against official HL7 FHIRPath and CQL compliance suites.
