# Rust Extension Implementation Plan

## Executive Summary

Create **two separate Rust-based packages** for high-performance FHIRPath evaluation:

| Package | Purpose | PyPI Name |
|---------|---------|-----------|
| `fhirpath-rs` | Pure FHIRPath evaluator (no DuckDB) | `fhirpath-rs` |
| `duckdb-fhirpath-rs` | DuckDB UDFs using fhirpath-rs | `duckdb-fhirpath-rs` |

This mirrors the Python structure (`fhirpath-py` + `duckdb-fhirpath-py`) and allows standalone FHIRPath evaluation without DuckDB.

**Key Benefits:**
- 100% FHIRPath spec compliance (1118 tests passing in octofhir-fhirpath)
- 10-20x performance improvement over Python
- Native wheel distribution (no external dependencies)
- Thread-safe, async-ready evaluation
- MIT OR Apache-2.0 license
- Reusable without DuckDB dependency

---

## Architecture

### Package Relationship

```
                        octofhir-fhirpath (Rust crate)
                                │
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                         fhirpath-rs                               │
│                    (PyO3 wrapper package)                         │
│                                                                   │
│  • evaluate(resource, expression) -> list                         │
│  • parse(expression) -> AST                                       │
│  • validate(expression) -> bool                                   │
│  • No DuckDB dependency                                           │
└───────────────────────────────────────────────────────────────────┘
                                │
                                │ import fhirpath_rs
                                ▼
┌───────────────────────────────────────────────────────────────────┐
│                     duckdb-fhirpath-rs                            │
│                   (DuckDB extension)                              │
│                                                                   │
│  • register_fhirpath(connection)                                  │
│  • Creates DuckDB UDFs that call fhirpath-rs                      │
│  • fhirpath(), fhirpath_text(), fhirpath_bool(), etc.            │
└───────────────────────────────────────────────────────────────────┘
```

### Comparison with Python Packages

| Layer | Python | Rust |
|-------|--------|------|
| **Core Evaluator** | `fhirpath-py` | `fhirpath-rs` |
| **DuckDB Extension** | `duckdb-fhirpath-py` | `duckdb-fhirpath-rs` |

### Shared API Contract

Both `fhirpath-py` and `fhirpath-rs` expose identical APIs:

```python
# Core evaluator API
def evaluate(resource: dict, expression: str, context: dict = None) -> list: ...
def parse(expression: str) -> AST: ...
def validate(expression: str) -> bool: ...
```

Both `duckdb-fhirpath-py` and `duckdb-fhirpath-rs` expose identical APIs:

```python
# DuckDB extension API
def register_fhirpath(con: duckdb.DuckDBPyConnection) -> None: ...

# UDF functions registered with DuckDB
def fhirpath(resource: str | None, expression: str | None) -> list[str] | None: ...
def fhirpath_text(resource: str | None, expression: str | None) -> str | None: ...
def fhirpath_bool(resource: str | None, expression: str | None) -> bool | None: ...
def fhirpath_number(resource: str | None, expression: str | None) -> float | None: ...
def fhirpath_json(resource: str | None, expression: str | None) -> str | None: ...
def fhirpath_is_valid(expression: str | None) -> bool: ...
```

---

## Project Structure

```
fhir4ds/
├── fhirpath-rs/                          # Pure FHIRPath evaluator
│   ├── src/
│   │   └── fhirpath_rs/
│   │       └── __init__.py               # Python wrapper
│   │
│   ├── rust/                             # Rust native extension
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs                    # PyO3 module entry
│   │       ├── evaluator.rs              # FHIRPathEvaluator wrapper
│   │       ├── types.rs                  # PyO3 type conversions
│   │       └── error.rs                  # Error handling
│   │
│   ├── tests/
│   │   ├── test_evaluator.py
│   │   └── test_compatibility.py         # Parity with fhirpath-py
│   │
│   ├── pyproject.toml                    # maturin config
│   └── README.md
│
├── duckdb-fhirpath-rs/                   # DuckDB extension
│   ├── src/
│   │   └── duckdb_fhirpath_rs/
│   │       ├── __init__.py               # Exports register_fhirpath
│   │       ├── extension.py              # DuckDB UDF registration
│   │       └── udf.py                    # UDF implementations
│   │
│   ├── tests/
│   │   ├── test_udf.py
│   │   └── test_integration.py
│   │
│   ├── pyproject.toml
│   └── README.md
│
└── (other packages...)
```

---

## Package 1: fhirpath-rs

### 1.1 Cargo.toml

```toml
[package]
name = "fhirpath-rs"
version = "0.1.0"
edition = "2021"

[lib]
name = "_native"
crate-type = ["cdylib"]

[dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
octofhir-fhirpath = "0.4"
octofhir-fhir-model = "0.1"
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
tokio = { version = "1.0", features = ["rt-multi-thread"] }
```

### 1.2 Core Types (rust/src/types.rs)

```rust
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde_json::Value;

/// FHIRPath evaluation result
#[pyclass]
pub struct FHIRPathResult {
    pub values: Vec<Value>,
}

#[pymethods]
impl FHIRPathResult {
    /// Convert to Python list
    fn to_list(&self, py: Python<'_>) -> PyResult<PyObject> {
        let list = PyList::empty(py);
        for val in &self.values {
            list.append(value_to_pyobject(py, val)?)?;
        }
        Ok(list.into())
    }

    /// Convert to Python list of strings
    fn to_string_list(&self, py: Python<'_>) -> PyResult<PyObject> {
        let list = PyList::empty(py);
        for val in &self.values {
            list.append(value_to_string(val))?;
        }
        Ok(list.into())
    }

    /// Get first value as string
    fn first_string(&self) -> Option<String> {
        self.values.first().map(value_to_string)
    }

    /// Get first value as bool
    fn first_bool(&self) -> Option<bool> {
        self.values.first().and_then(|v| match v {
            Value::Bool(b) => Some(*b),
            Value::String(s) => Some(s.eq_ignore_ascii_case("true")),
            _ => None,
        })
    }

    /// Get first value as number
    fn first_number(&self) -> Option<f64> {
        self.values.first().and_then(|v| match v {
            Value::Number(n) => n.as_f64(),
            _ => None,
        })
    }

    /// Check if empty
    fn is_empty(&self) -> bool {
        self.values.is_empty()
    }

    fn __len__(&self) -> usize {
        self.values.len()
    }

    fn __repr__(&self) -> String {
        format!("FHIRPathResult({:?})", self.values)
    }
}

fn value_to_string(val: &Value) -> String {
    match val {
        Value::String(s) => s.clone(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::Null => "null".to_string(),
        other => other.to_string(),
    }
}

fn value_to_pyobject(py: Python<'_>, val: &Value) -> PyResult<PyObject> {
    use pyo3::types::PyBool;
    match val {
        Value::Null => Ok(py.None()),
        Value::Bool(b) => Ok(PyBool::new(py, *b).into()),
        Value::Number(n) => {
            if let Some(f) = n.as_f64() {
                Ok(f.into_pyobject(py)?.into_any().unbind())
            } else {
                Ok(n.to_string().into_pyobject(py)?.into_any().unbind())
            }
        }
        Value::String(s) => Ok(s.into_pyobject(py)?.into_any().unbind()),
        Value::Array(arr) => {
            let list = PyList::empty(py);
            for item in arr {
                list.append(value_to_pyobject(py, item)?)?;
            }
            Ok(list.into())
        }
        Value::Object(obj) => {
            let dict = PyDict::new(py);
            for (k, v) in obj {
                dict.set_item(k, value_to_pyobject(py, v)?)?;
            }
            Ok(dict.into())
        }
    }
}
```

### 1.3 Evaluator Wrapper (rust/src/evaluator.rs)

```rust
use pyo3::prelude::*;
use octofhir_fhirpath::FhirPathEngine;
use octofhir_fhirpath::context::EvaluationContext;
use serde_json::Value;
use std::sync::Arc;
use tokio::runtime::Runtime;
use crate::types::FHIRPathResult;

/// Thread-safe FHIRPath evaluator
#[pyclass]
pub struct FHIRPathEvaluator {
    engine: Arc<FhirPathEngine>,
    runtime: Runtime,
}

#[pymethods]
impl FHIRPathEvaluator {
    #[new]
    fn new() -> PyResult<Self> {
        let runtime = Runtime::new()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                format!("Failed to create tokio runtime: {}", e)
            ))?;

        // Create engine with empty provider (SYNC call)
        let engine = octofhir_fhirpath::create_engine_with_empty_provider()
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
                format!("Failed to create FHIRPath engine: {}", e)
            ))?;

        Ok(Self {
            engine: Arc::new(engine),
            runtime,
        })
    }

    /// Evaluate a FHIRPath expression against a JSON resource string
    fn evaluate_str(
        &self,
        resource_json: &str,
        expression: &str,
    ) -> PyResult<FHIRPathResult> {
        let resource: Value = serde_json::from_str(resource_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Invalid JSON: {}", e)
            ))?;

        self.evaluate_value(&resource, expression)
    }

    /// Evaluate a FHIRPath expression against a Python dict
    fn evaluate_dict(
        &self,
        resource: &PyDict,
        expression: &str,
    ) -> PyResult<FHIRPathResult> {
        let resource = pydict_to_value(resource)?;
        self.evaluate_value(&resource, expression)
    }

    /// Validate a FHIRPath expression
    fn validate(&self, expression: &str) -> bool {
        self.engine.validate(expression).is_ok()
    }
}

impl FHIRPathEvaluator {
    fn evaluate_value(&self, resource: &Value, expression: &str) -> PyResult<FHIRPathResult> {
        let engine = Arc::clone(&self.engine);
        let resource = resource.clone();
        let expression = expression.to_string();

        let result = self.runtime.block_on(async {
            let ctx = EvaluationContext::from_value(resource);
            engine.evaluate(&expression, &ctx).await
        }).map_err(|e| PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(
            format!("Evaluation error: {}", e)
        ))?;

        Ok(FHIRPathResult {
            values: result,
        })
    }
}

fn pydict_to_value(dict: &PyDict) -> PyResult<Value> {
    let json_str = pyo3::Python::with_gil(|py| {
        use pyo3::types::PyString;
        let json_module = py.import("json")?;
        let dumps = json_module.getattr("dumps")?;
        let result: Py<PyString> = dumps.call1((dict,))?.extract()?;
        Ok::<_, PyErr>(result.to_string())
    })?;

    serde_json::from_str(&json_str)
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Failed to convert dict to JSON: {}", e)
        ))
}
```

### 1.4 Module Entry (rust/src/lib.rs)

```rust
use pyo3::prelude::*;
use std::sync::OnceLock;

mod evaluator;
mod types;
mod error;

use evaluator::FHIRPathEvaluator;
use types::FHIRPathResult;

/// Global evaluator instance (thread-safe)
static EVALUATOR: OnceLock<FHIRPathEvaluator> = OnceLock::new();

fn get_evaluator() -> &'static FHIRPathEvaluator {
    EVALUATOR.get_or_init(|| FHIRPathEvaluator::new().expect("Failed to create evaluator"))
}

/// Evaluate a FHIRPath expression against a resource (JSON string)
#[pyfunction]
fn evaluate(resource_json: &str, expression: &str) -> PyResult<PyObject> {
    let evaluator = get_evaluator();
    let result = evaluator.evaluate_str(resource_json, expression)?;
    Python::with_gil(|py| result.to_list(py))
}

/// Parse a FHIRPath expression (returns AST representation)
#[pyfunction]
fn parse(expression: &str) -> PyResult<String> {
    // For now, just validate - AST representation can be added later
    let evaluator = get_evaluator();
    if evaluator.validate(expression) {
        Ok(expression.to_string()) // Placeholder
    } else {
        Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
            format!("Invalid FHIRPath expression: {}", expression)
        ))
    }
}

/// Validate a FHIRPath expression
#[pyfunction]
fn validate(expression: &str) -> bool {
    get_evaluator().validate(expression)
}

/// fhirpath_rs._native module
#[pymodule]
fn _native(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_class::<FHIRPathEvaluator>()?;
    m.add_class::<FHIRPathResult>()?;
    m.add_function(wrap_pyfunction!(evaluate, m)?)?;
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add_function(wrap_pyfunction!(validate, m)?)?;
    Ok(())
}
```

### 1.5 Python Package (__init__.py)

```python
"""
fhirpath-rs - High-performance FHIRPath evaluator (Rust backend)

Usage:
    from fhirpath_rs import evaluate

    patient = {"resourceType": "Patient", "id": "123"}
    result = evaluate(patient, "Patient.id")
    # result: ["123"]
"""

import json
from fhirpath_rs._native import evaluate as _evaluate, validate, parse

__version__ = "0.1.0"
__all__ = ["evaluate", "validate", "parse", "FHIRPathEvaluator"]


def evaluate(resource, expression, context=None):
    """
    Evaluate a FHIRPath expression against a FHIR resource.

    Args:
        resource: A FHIR resource (dict) or JSON string
        expression: A FHIRPath expression string
        context: Optional evaluation context (ignored for now)

    Returns:
        List of matching values
    """
    if isinstance(resource, dict):
        resource_json = json.dumps(resource)
    elif isinstance(resource, str):
        resource_json = resource
    else:
        raise TypeError(f"resource must be dict or str, got {type(resource)}")

    return _evaluate(resource_json, expression)


# Re-export the evaluator class for advanced usage
from fhirpath_rs._native import FHIRPathEvaluator
```

### 1.6 pyproject.toml

```toml
[build-system]
requires = ["maturin>=1.0,<2.0"]
build-backend = "maturin"

[project]
name = "fhirpath-rs"
version = "0.1.0"
description = "High-performance FHIRPath evaluator (Rust backend)"
readme = "README.md"
license = {text = "MIT OR Apache-2.0"}
requires-python = ">=3.9"
dependencies = []

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "fhirpath-py",  # For compatibility testing
]

[project.urls]
Homepage = "https://github.com/fhir4ds/fhir4ds"
Repository = "https://github.com/fhir4ds/fhir4ds"

[tool.maturin]
python-source = "src"
module-name = "fhirpath_rs._native"
features = ["pyo3/extension-module"]
```

---

## Package 2: duckdb-fhirpath-rs

### 2.1 Python UDF Implementation (src/duckdb_fhirpath_rs/udf.py)

```python
"""
DuckDB UDF implementations using fhirpath-rs.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

import json
from functools import lru_cache

# Import from fhirpath-rs
from fhirpath_rs import evaluate as fhirpath_evaluate
from fhirpath_rs import validate as fhirpath_validate


def _evaluate_to_strings(resource: str | None, expression: str | None) -> list[str]:
    """Evaluate FHIRPath and return list of strings."""
    if resource is None or expression is None:
        return []

    try:
        result = fhirpath_evaluate(resource, expression)
        return [str(item) if not isinstance(item, str) else item for item in result]
    except Exception:
        return []


def fhirpath_udf(resource: str | None, expression: str | None) -> list[str] | None:
    """Main fhirpath UDF - returns list of strings."""
    if resource is None or expression is None:
        return None
    return _evaluate_to_strings(resource, expression)


def fhirpath_text_udf(resource: str | None, expression: str | None) -> str | None:
    """fhirpath_text UDF - returns first value as string."""
    if resource is None or expression is None:
        return None

    result = _evaluate_to_strings(resource, expression)
    return result[0] if result else None


def fhirpath_bool_udf(resource: str | None, expression: str | None) -> bool | None:
    """fhirpath_bool UDF - returns first value as bool."""
    if resource is None or expression is None:
        return None

    try:
        result = fhirpath_evaluate(resource, expression)
        if not result:
            return None
        first = result[0]
        if isinstance(first, bool):
            return first
        if isinstance(first, str):
            return first.lower() == "true"
        return bool(first)
    except Exception:
        return None


def fhirpath_number_udf(resource: str | None, expression: str | None) -> float | None:
    """fhirpath_number UDF - returns first value as float."""
    if resource is None or expression is None:
        return None

    try:
        result = fhirpath_evaluate(resource, expression)
        if not result:
            return None
        first = result[0]
        if isinstance(first, (int, float)):
            return float(first)
        if isinstance(first, str):
            return float(first)
        return None
    except Exception:
        return None


def fhirpath_json_udf(resource: str | None, expression: str | None) -> str | None:
    """fhirpath_json UDF - returns result as JSON string."""
    if resource is None or expression is None:
        return None

    try:
        result = fhirpath_evaluate(resource, expression)
        if not result:
            return None
        if len(result) == 1:
            return json.dumps(result[0])
        return json.dumps(result)
    except Exception:
        return None


def fhirpath_is_valid_udf(expression: str | None) -> bool:
    """fhirpath_is_valid UDF - validates expression syntax."""
    if not expression or not isinstance(expression, str):
        return False
    return fhirpath_validate(expression)
```

### 2.2 Extension Registration (src/duckdb_fhirpath_rs/extension.py)

```python
"""
DuckDB Extension Registration for Rust Backend
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

from duckdb_fhirpath_rs.udf import (
    fhirpath_udf,
    fhirpath_text_udf,
    fhirpath_bool_udf,
    fhirpath_number_udf,
    fhirpath_json_udf,
    fhirpath_is_valid_udf,
)


def register_fhirpath(con: duckdb.DuckDBPyConnection) -> None:
    """
    Register the fhirpath UDF family with a DuckDB connection.

    Uses the Rust backend (fhirpath-rs) for 10-20x faster evaluation.

    Args:
        con: A DuckDB connection object.

    Example:
        >>> import duckdb
        >>> from duckdb_fhirpath_rs import register_fhirpath
        >>> con = duckdb.connect()
        >>> register_fhirpath(con)
    """
    from duckdb.functional import FunctionNullHandling

    # Register main fhirpath function
    con.create_function("fhirpath", fhirpath_udf)

    # Register validation function
    con.create_function("fhirpath_is_valid", fhirpath_is_valid_udf)

    # Register convenience UDFs with SPECIAL null handling
    con.create_function(
        "fhirpath_text",
        fhirpath_text_udf,
        null_handling=FunctionNullHandling.SPECIAL,
    )

    con.create_function(
        "fhirpath_bool",
        fhirpath_bool_udf,
        null_handling=FunctionNullHandling.SPECIAL,
    )

    con.create_function(
        "fhirpath_number",
        fhirpath_number_udf,
        null_handling=FunctionNullHandling.SPECIAL,
    )

    con.create_function(
        "fhirpath_json",
        fhirpath_json_udf,
        null_handling=FunctionNullHandling.SPECIAL,
    )
```

### 2.3 Package Init (__init__.py)

```python
"""
duckdb-fhirpath-rs - DuckDB FHIRPath extension (Rust backend)

A high-performance DuckDB extension for evaluating FHIRPath expressions,
powered by the fhirpath-rs Rust library.

Usage:
    import duckdb
    from duckdb_fhirpath_rs import register_fhirpath

    con = duckdb.connect()
    register_fhirpath(con)

    result = con.execute('''
        SELECT fhirpath(resource, 'Patient.name.given')
        FROM fhir_resources
    ''').fetchall()
"""

from duckdb_fhirpath_rs.extension import register_fhirpath

__version__ = "0.1.0"
__all__ = ["register_fhirpath"]
```

### 2.4 pyproject.toml

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "duckdb-fhirpath-rs"
version = "0.1.0"
description = "DuckDB extension for FHIRPath queries (Rust backend)"
readme = "README.md"
license = {text = "MIT OR Apache-2.0"}
requires-python = ">=3.9"
dependencies = [
    "fhirpath-rs>=0.1.0",
    "duckdb>=0.9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "duckdb-fhirpath-py",  # For compatibility testing
]

[project.urls]
Homepage = "https://github.com/fhir4ds/fhir4ds"
Repository = "https://github.com/fhir4ds/fhir4ds"

[tool.hatch.build.targets.wheel]
packages = ["src/duckdb_fhirpath_rs"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
target-version = "py39"
line-length = 100
select = ["E", "W", "F", "I", "B", "C4", "UP"]
ignore = ["E501", "B008"]

[tool.ruff.isort]
known-first-party = ["duckdb_fhirpath_rs", "fhirpath_rs"]
```

---

## Build System

### Build Commands

```bash
# Build fhirpath-rs
cd fhirpath-rs
maturin develop --release      # Development build
maturin build --release        # Build wheel

# Install duckdb-fhirpath-rs (depends on fhirpath-rs)
cd ../duckdb-fhirpath-rs
pip install -e .
```

### CI/CD Pipeline (GitHub Actions)

```yaml
name: Build Rust Wheels

on:
  push:
    tags:
      - 'fhirpath-rs-v*'

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: ubuntu-latest
            target: x86_64-unknown-linux-gnu
          - os: windows-latest
            target: x86_64-pc-windows-msvc
          - os: macos-latest
            target: x86_64-apple-darwin
          - os: macos-latest
            target: aarch64-apple-darwin

    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.target }}

      - name: Build wheel
        uses: PyO3/maturin-action@v1
        with:
          target: ${{ matrix.target }}
          args: --release --out dist
          working-directory: fhirpath-rs

      - name: Upload wheel
        uses: actions/upload-artifact@v4
        with:
          name: wheel-${{ matrix.target }}
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - name: Download wheels
        uses: actions/download-artifact@v4
        with:
          path: dist/

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

---

## Implementation Plan

### Phase 1: fhirpath-rs Core (Week 1)

| Task | Description |
|------|-------------|
| Set up Rust project | Cargo.toml, maturin config |
| FHIRPathEvaluator wrapper | PyO3 bindings for octofhir-fhirpath |
| Type conversions | PyObject ↔ serde_json::Value |
| Core API functions | evaluate(), validate(), parse() |
| Unit tests | Basic evaluation tests |

**Deliverable:** Working `fhirpath-rs` package with `evaluate()` function.

### Phase 2: duckdb-fhirpath-rs Integration (Week 2)

| Task | Description |
|------|-------------|
| Python UDF layer | udf.py with all 6 UDF functions |
| Extension registration | extension.py with register_fhirpath() |
| Integration tests | Test with DuckDB queries |
| Compatibility tests | Verify parity with duckdb-fhirpath-py |

**Deliverable:** Working `duckdb-fhirpath-rs` package.

### Phase 3: Optimization (Week 3)

| Task | Description |
|------|-------------|
| GIL release | Release GIL during Rust evaluation |
| Expression caching | Cache parsed AST in Rust |
| Batch evaluation | Evaluate multiple resources efficiently |
| Benchmark suite | Performance comparison tests |

**Deliverable:** Optimized implementation.

### Phase 4: Distribution (Week 4)

| Task | Description |
|------|-------------|
| CI/CD pipeline | GitHub Actions for multi-platform builds |
| Wheel building | Build for Linux, macOS, Windows |
| PyPI publishing | Upload both packages |
| Documentation | API docs, usage guide |

**Deliverable:** Published packages on PyPI.

---

## Performance Targets

| Metric | fhirpath-py | fhirpath-rs | Improvement |
|--------|-------------|-------------|-------------|
| Single resource eval | ~200 µs | ~10-20 µs | 10-20x |
| Batch 1000 resources | ~200 ms | ~10-20 ms | 10-20x |
| Expression compilation | ~50 µs | ~5 µs | 10x |
| Memory per evaluation | ~1 KB | ~100 B | 10x |

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rust API changes | Medium | Pin octofhir-fhirpath version |
| Build complexity | Low | Use maturin, well-documented |
| Result divergence | High | Comprehensive parity test suite |
| Platform support | Medium | CI builds for all platforms |
| GIL contention | Low | Release GIL during evaluation |

---

## Success Criteria

1. **API Compatibility:** `fhirpath-rs` has same API as `fhirpath-py`
2. **API Compatibility:** `duckdb-fhirpath-rs` has same API as `duckdb-fhirpath-py`
3. **Performance:** 10x+ improvement over Python backend
4. **Parity:** 100% agreement on test cases between implementations
5. **Distribution:** Wheels available for Linux, macOS (Intel + ARM), Windows
6. **Independence:** `fhirpath-rs` works without DuckDB

---

## Usage Examples

### Standalone FHIRPath (no DuckDB)

```python
# Python backend
from fhirpath_py import evaluate

# Rust backend (10-20x faster)
from fhirpath_rs import evaluate

patient = {
    "resourceType": "Patient",
    "id": "123",
    "name": [{"given": ["John"], "family": "Doe"}]
}

result = evaluate(patient, "Patient.name.given")
# result: ["John"]
```

### DuckDB Extension

```python
import duckdb

# Python backend
# from duckdb_fhirpath_py import register_fhirpath

# Rust backend (10-20x faster)
from duckdb_fhirpath_rs import register_fhirpath

con = duckdb.connect()
register_fhirpath(con)

result = con.execute('''
    SELECT
        id,
        fhirpath_text(resource, 'Patient.name.given') as first_name,
        fhirpath_bool(resource, 'Patient.active') as is_active
    FROM patients
    WHERE fhirpath_bool(resource, 'Patient.active') = true
''').fetchdf()
```

### Benchmarking

```python
import duckdb
import time

test_resource = '{"resourceType":"Patient","id":"123","active":true}'
test_expression = 'Patient.id'

def benchmark(backend, iterations=10000):
    if backend == 'py':
        from duckdb_fhirpath_py import register_fhirpath
    else:
        from duckdb_fhirpath_rs import register_fhirpath

    con = duckdb.connect()
    register_fhirpath(con)

    start = time.perf_counter()
    for _ in range(iterations):
        con.execute(
            "SELECT fhirpath(?, ?)",
            [test_resource, test_expression]
        ).fetchone()
    elapsed = time.perf_counter() - start

    print(f"{backend}: {elapsed:.3f}s ({iterations/elapsed:.0f} eval/s)")
    con.close()

benchmark('py')   # Python backend
benchmark('rs')   # Rust backend
```

---

## References

- [octofhir-fhirpath-rs](https://github.com/octofhir/fhirpath-rs)
- [octofhir-fhirpath docs.rs](https://docs.rs/octofhir-fhirpath)
- [PyO3 Documentation](https://pyo3.rs/)
- [Maturin Guide](https://www.maturin.rs/)
- [FHIRPath Specification](https://hl7.org/fhirpath/)
