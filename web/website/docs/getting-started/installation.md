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
For advanced measure evaluation and clinical reasoning, install the `measures` extra:

```bash
pip install "fhir4ds-v2[measures]"
```

For DQM materialization workers:

```bash
pip install "fhir4ds-v2[hapi]"   # HAPI PostgreSQL worker
pip install "fhir4ds-v2[mongo]"  # Mongo change-stream worker
```

### DuckDB 2.0 (experimental, opt-in)

The default install pins the DuckDB 1.5.x line. Experimental DuckDB 2.0.0
support (the wheel bundles the `.duckdb2_extension` binaries and selects
them at runtime) is opt-in:

```bash
pip install "fhir4ds-v2[duckdb2]"
```

DuckDB 2.x wheels require **Python 3.11+**. Request the `[duckdb2]` extra
**on its own** — pip intersects it with the base DuckDB pin, so combining
extras in one command (e.g. `[duckdb2,serve]`) cannot resolve; install any
other extras in a second command:

```bash
pip install "fhir4ds-v2[duckdb2]"
pip install "fhir4ds-v2[serve]"
```

2.0 stays opt-in (not the default pin) because of an upstream DuckDB 2.0
optimizer/planner pathology on large generated SQL
([duckdb/duckdb#28181](https://github.com/duckdb/duckdb/issues/28181)).

After installation, import from the `fhir4ds` namespace:

```python
import fhir4ds

con = fhir4ds.create_connection()
```

## Using in the Browser (WASM)
If you are building a web application, you can use the pre-compiled WASM extensions and Python wheels. See the [WASM Engine](/docs/integrations/wasm-engine/) for details.
