---
id: installation
title: Installation
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

After installation, import from the `fhir4ds` namespace:

```python
import fhir4ds

con = fhir4ds.create_connection()
```

## Using in the Browser (WASM)
If you are building a web application, you can use the pre-compiled WASM extensions and Python wheels. See the [WASM Engine](/docs/integrations/wasm-engine) for details.
