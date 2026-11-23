---
id: installation
title: Installation
description: "Install FHIR4DS with pip — core engine, optional extras for measures, terminology, and MCP — plus native DuckDB extension setup."
---

# Installation

FHIR4DS is a suite of high-performance tools for FHIR data science. You can install the unified package or individual sub-packages depending on your needs.

## Prerequisites
- Python 3.10 or newer.
- DuckDB (installed automatically with `fhir4ds-v2`).

## Installing with pip

The PyPI package is named **`fhir4ds-v2`** and imports as `fhir4ds`:

```bash
pip install fhir4ds-v2
```

### Optional Dependencies

| Extra | Purpose |
|-------|---------|
| `[measures]` | pandas — `evaluate_measure` result DataFrames |
| `[hapi]` | HAPI PostgreSQL materialization worker (psycopg) |
| `[mongo]` | Mongo change-stream materialization worker (pymongo) |
| `[serve]` | `fhir4ds serve` HTTP surface (fastapi + uvicorn) |
| `[hf]` | Hub-backed publish store for the serve layer (huggingface-hub) |
| `[terminology]` | Terminology service integration (httpx + medterm4ds) |
| `[ner]` | Clinical notes NER cascade (medterm4ds[extraction]) |
| `[mcp]` | `fhir4ds-mcp` stdio server for agentic interfaces (MCP SDK 1.x) |

```bash
pip install "fhir4ds-v2[measures]"       # measure evaluation
pip install "fhir4ds-v2[serve]"          # FHIR R4 / SQL-on-FHIR HTTP API
pip install "fhir4ds-v2[hapi]"           # HAPI PostgreSQL worker
pip install "fhir4ds-v2[mongo]"          # Mongo change-stream worker
pip install "fhir4ds-v2[terminology]"    # terminology service integration
pip install "fhir4ds-v2[ner]"            # clinical notes NER pipeline
pip install "fhir4ds-v2[mcp]"            # MCP stdio server
```

### DuckDB 2.0 (default on Python 3.11+)

New installs pick the DuckDB line automatically: **Python 3.11+ gets
DuckDB 2.0.x** (measurably faster at population scale — up to ~10× on
large measures — with the validated planner tuning that
`fhir4ds.register()` applies automatically); **Python 3.10 gets the 1.5.x
line** (DuckDB 2.x wheels are cp311+ only). The correct native extension
for whichever DuckDB is installed loads at runtime.

To stay on (or return to) the 1.5.x line on Python 3.11+:

```bash
pip install "fhir4ds-v2[duckdb1]"
```

`[duckdb2]` also remains available as the explicit 2.0.x pin. On Python
3.10 it resolves to the 1.5.x line.

After installation, import from the `fhir4ds` namespace:

```python
import fhir4ds

con = fhir4ds.create_connection()
```

## Using in the Browser (WASM)
If you are building a web application, you can use the pre-compiled WASM extensions and Python wheels. See the [WASM Engine](/docs/integrations/wasm-engine/) for details.
