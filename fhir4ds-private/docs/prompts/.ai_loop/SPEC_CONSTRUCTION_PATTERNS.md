# 📋 SPEC: CONSTRUCTION PATTERNS & PLUMBING

This document defines the standard "Plumbing Patterns" for expanding the `fhir4ds-v2` library. Use these templates to ensure that new features feel native and integrate correctly with existing abstractions.

---

## 1. 🔌 NEW SOURCE ADAPTER PATTERN
*Location: `fhir4ds/sources/`*

Every source must implement the `SourceAdapter` protocol.

```python
from __future__ import annotations
from typing import Any
from fhir4ds.sources.base import validate_schema

class MyNewSource:
    """
    Brief description of the source.
    """
    def __init__(self, ...):
        # Store connection/path details
        pass

    def register(self, con: Any) -> None:
        # 1. Mount data as a view named 'resources'
        # 2. MUST call validate_schema(con, self.__class__.__name__)
        pass

    def unregister(self, con: Any) -> None:
        # Drop the view and detach if necessary
        con.execute("DROP VIEW IF EXISTS resources")
```

**Exports**: Always add your new source to `fhir4ds/sources/__init__.py`.

---

## 2. 🧩 NEW DUCKDB UDF PATTERN
*Location: `fhir4ds/fhirpath/duckdb/` or `fhir4ds/cql/duckdb/`*

If adding a new low-level function (e.g., a new FHIRPath function):

1.  **Python Logic**: Implement the core function in a standalone utility.
2.  **Registration**: Add to the `register(con)` function in the appropriate module.
3.  **Error Handling**: Ensure the UDF catches exceptions and returns `NULL` (or raises a `DuckDBError` with a clear message) per spec.

---

## 3. 🧪 UNIT TEST PATTERN
*Location: `fhir4ds/*/tests/`*

1.  **Isolation**: Use `pytest.fixture` to provide a clean `duckdb.connect()` instance.
2.  **Mock Data**: Use the `tests/data/` JSON/NDJSON snippets where possible.
3.  **Naming**: `test_[function_name]_[scenario].py`.

---

## 4. 📝 API ERGONOMICS
*Location: `fhir4ds/core.py` and `fhir4ds/__init__.py`*

*   New core capabilities should be accessible via `fhir4ds.create_connection(source=...)` or high-level evaluators.
*   Avoid requiring the user to import 5 different sub-modules to use one feature. Use the top-level `__init__.py` to provide a clean surface.
