---
id: engine
title: The Unified Engine
description: "User guide to the FHIR4DS engine — connections, FHIRPath evaluation, and the operations API surface."
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

1.  **Connect**: Create a DuckDB connection.
2.  **Attach**: Mount your data using a `SourceAdapter` (e.g., `FileSystemSource`).
3.  **Execute**: Run FHIRPath queries, evaluate CQL measures, or generate SQL views.
4.  **Analyze**: Process results as standard DataFrames or DuckDB relations.

```python
import fhir4ds
from fhir4ds.sources import FileSystemSource

# 1. Connect & 2. Attach (Recommended Zero-ETL pattern)
con = fhir4ds.create_connection(
    source=FileSystemSource("./data/**/*.parquet")
)

# 3. Execute (High-level API)
result = fhir4ds.evaluate_measure("CMS124.cql", conn=con)

# 4. Analyze
df = result.df()
```

---

## 3. Core Mechanisms

The engine handles the technical complexity of FHIR analytics under the hood so you can focus on the clinical logic.

### Unified Registration
Instead of managing multiple extensions and UDFs manually, a single call to `register(con)` prepares your DuckDB connection with every tool in the suite. It automatically detects the environment (Native vs. WASM) and loads the optimal implementation.

### C++/Python Fallback
The C++ DuckDB extensions provide maximum performance for large-scale population analytics. However, in environments where binary extensions are restricted, the engine transparently falls back to pure-Python vectorized implementations to ensure your code remains functional and accurate.

Fallback never changes results — only speed. The native and Python engines are parity-tested, so the conformance suites pass on both.

### Environment switches
Three environment variables tune the engine. They are read at connection time.

| Variable | Effect |
|---|---|
| `FHIR4DS_REQUIRE_CPP=1` | Make a missing native extension **fatal** instead of a silent fallback. Use this in CI or production where you expect the C++ engine: it raises `RuntimeError` both when DuckDB's version line has no bundled binary (`1.5.x` and `2.0.x` are shipped) and when the bundled file is missing. Without it, both cases log and fall back. The literal value `1` is what enables it — `true`/`yes` are ignored. |
| `FHIR4DS_USE_CPP_VALUESET_CACHE=0` | Force the Python ValueSet membership cache even when the native extension exposes its own. Useful when mixing native UDFs with a `valueset_codes` table that is refreshed outside the loader. |
| `FHIR4DS_CQL_LATERAL_DEDUP=0` | Disable the CQL translator's lateral-dedup optimization (which hoists repeated correlated extractions into `CROSS JOIN LATERAL`). An escape hatch if a hand-written query misbehaves; translated SQL grows substantially. |

```python
import os
os.environ["FHIR4DS_REQUIRE_CPP"] = "1"   # fail loudly if the native engine is unavailable

import fhir4ds
con = fhir4ds.create_connection(allow_unsigned_extensions=True)
assert fhir4ds.register(con)["fhirpath_cpp"], "native engine expected"
```

### Automated Terminology
The engine manages the orchestration between CQL logic and ValueSet expansion. It handles terminology resolution automatically during the translation phase, allowing you to use standard codes and systems without manual mapping.

---

## 4. Functional Modules

FHIR4DS is organized into several functional pillars. Use the guides below to dive deeper into each area.

<details>
<summary><b>Data Extraction (FHIRPath)</b>: Native filtering and selection</summary>

The `fhirpath` module provides a high-performance C++ DuckDB extension for executing expressions directly against FHIR JSON columns.

- **Learn more**: [FHIRPath Guide](/docs/user-guide/extraction/fhirpath/)
- **Database integration**: [Native DuckDB Integration](/docs/user-guide/duckdb/)
</details>

<details>
<summary><b>Modeling (ViewDefinition)</b>: Flattening FHIR for standard SQL</summary>

The `viewdef` module implements the HL7 SQL-on-FHIR v2 specification, allowing you to define flat projections of complex FHIR resources in portable JSON.

- **Guide**: [ViewDefinition Modeling](/docs/user-guide/modeling/viewdef/)
</details>

<details>
<summary><b>Clinical Logic (CQL)</b>: Translating logic to vectorized SQL</summary>

The `cql` module translates Clinical Quality Language into optimized DuckDB SQL queries that process entire populations in a single pass.

- **Basics**: [Clinical Quality Language (CQL)](/docs/user-guide/analytics/cql/)
- **Internals**: [Translation Logic](/docs/api-reference/cql/)
</details>

<details>
<summary><b>Measurement (DQM)</b>: End-to-end measure orchestration</summary>

The `dqm` (Digital Quality Measures) module manages the full lifecycle of evaluation, from loading CMS bundles to generating auditable evidence.

- **Workflow & Audit**: [DQM Orchestration](/docs/user-guide/quality/dqm/)
- **Production Recipes**: [Source-to-DQM Production Recipes](/docs/examples/dqm-recipes/)
</details>

## 5. Operations

For repeatable batch runs and project automation, use the operations guides:

- **CLI**: [Command Line Interface](/docs/user-guide/interfaces/cli/)

---

:::tip 

Full API Reference
For a complete list of functions, parameters, and return types, see the [API Reference](/docs/api-reference/fhir4ds/).

:::
