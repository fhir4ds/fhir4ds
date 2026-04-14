---
id: engine
title: The Unified Engine
sidebar_label: The Unified Engine
slug: /user-guide/index
---

# The Unified Engine

The **fhir4ds** package is the single recommended entry point for the entire toolkit. It simplifies healthcare data science by bundling FHIRPath evaluation, CQL translation, and SQL-on-FHIR ViewDefinitions into a single, high-level API.

## 1. Design Philosophy

The primary goal of the unified engine is **transparency** and **performance** across all environments:

-   **SQL-First**: Clinical logic is translated directly into standard, inspectable DuckDB SQL. You own the query.
-   **Hybrid Execution**: Automatic fallback between high-performance C++ extensions and vectorized Python implementations.
-   **No Infrastructure**: Zero-server deployment, from local Jupyter notebooks to in-browser WebAssembly.

---

## 2. Basic Workflow

The common pattern for using FHIR4DS involves four simple steps:

1.  **Connect**: Create or attach a DuckDB connection.
2.  **Register**: Load UDFs and extensions via `fhir4ds.register()`.
3.  **Ingest**: Load patient data into the `resources` table.
4.  **Execute**: Run FHIRPath queries, evaluate CQL measures, or generate SQL views.

```python
import fhir4ds
from fhir4ds.cql import FHIRDataLoader

# 1. Connect (UDFs are registered automatically)
con = fhir4ds.create_connection()

# 2. Ingest
loader = FHIRDataLoader(con)
loader.load_directory("./data/")

# 3. Execute (High-level API)
result = fhir4ds.evaluate_measure("CMS124.cql", conn=con)
```

---

## 3. Core Mechanisms

The engine handles the technical complexity of FHIR analytics under the hood so you can focus on the clinical logic.

### Unified Registration
Instead of managing multiple extensions and UDFs manually, a single call to `register(con)` prepares your DuckDB connection with every tool in the suite. It automatically detects the environment (Native vs. WASM) and loads the optimal implementation.

### C++/Python Fallback
The C++ DuckDB extensions provide maximum performance for large-scale population analytics. However, in environments where binary extensions are restricted, the engine transparently falls back to pure-Python vectorized implementations to ensure your code remains functional and accurate.

### Automated Terminology
The engine manages the orchestration between CQL logic and ValueSet expansion. It handles terminology resolution automatically during the translation phase, allowing you to use standard codes and systems without manual mapping.

---

## 4. Functional Modules

FHIR4DS is organized into several functional pillars. Use the guides below to dive deeper into each area.

<details>
<summary><b>Data Extraction (FHIRPath)</b>: Native filtering and selection</summary>

The `fhirpath` module provides a high-performance C++ DuckDB extension for executing expressions directly against FHIR JSON columns.

- **Learn more**: [FHIRPath Guide](./extraction/fhirpath)
- **Database integration**: [Native DuckDB Integration](./extraction/duckdb)
</details>

<details>
<summary><b>Modeling (ViewDefinition)</b>: Flattening FHIR for standard SQL</summary>

The `viewdef` module implements the HL7 SQL-on-FHIR v2 specification, allowing you to define flat projections of complex FHIR resources in portable JSON.

- **Guide**: [ViewDefinition Modeling](./modeling/viewdef)
</details>

<details>
<summary><b>Clinical Logic (CQL)</b>: Translating logic to vectorized SQL</summary>

The `cql` module translates Clinical Quality Language into optimized DuckDB SQL queries that process entire populations in a single pass.

- **Basics**: [Clinical Quality Language (CQL)](./analytics/cql)
- **Internals**: [Translation Logic](/docs/api-reference/cql/)
</details>

<details>
<summary><b>Measurement (DQM)</b>: End-to-end measure orchestration</summary>

The `dqm` (Digital Quality Measures) module manages the full lifecycle of evaluation, from loading CMS bundles to generating auditable evidence.

- **Workflow & Audit**: [DQM Orchestration](./quality/dqm)
</details>

---

:::tip 

Full API Reference
For a complete list of functions, parameters, and return types, see the [API Reference](/docs/api-reference/fhir4ds).

:::
