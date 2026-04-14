---
id: fhirpath
title: fhirpath
sidebar_label: fhirpath
---

# `fhir4ds.fhirpath`

Core FHIRPath R4 evaluation engine. Provides a pure-Python evaluator and high-performance DuckDB SQL integration.

## 1. At a Glance

The most common entry points for direct evaluation:

```python
from fhir4ds.fhirpath import evaluate       # Evaluate against a Python object
from fhir4ds.fhirpath.duckdb import register_fhirpath  # Register UDFs on DuckDB
```

---

## 2. Function Reference

### `evaluate`
`evaluate(resource, path, context=None, model=None, options=None) -> list`

Evaluates a FHIRPath expression against a Python dictionary or list of resources.

| Parameter | Type | Description |
|-----------|------|-------------|
| `resource` | `dict | list` | The FHIR resource(s) to evaluate. |
| `path` | `str` | The FHIRPath expression. |
| `context` | `dict` | (Optional) Map of variable names to values (e.g. `%patient`). |
| `model` | `dict` | (Optional) The model data object specific to a domain, e.g. R4. |
| `options` | `dict` | (Optional) Config like `{"strict_mode": True}`. |

---

## 3. SQL UDF Reference

Registered via `fhir4ds.register()`.

| Function | Returns | Description |
|----------|---------|-------------|
| `fhirpath(json, expr)` | `VARCHAR[]` | All matching elements as a list. |
| `fhirpath_text(json, expr)` | `VARCHAR` | The first matching element as text. |
| `fhirpath_bool(json, expr)` | `BOOLEAN` | Evaluates expression to a boolean. |
| `fhirpath_number(json, expr)` | `DOUBLE` | The first matching numeric value. |

---

## 4. Supported Features

The FHIR4DS engine provides **100% coverage** for the following FHIRPath R4 features:

| Feature Category | Examples | Status |
|------------------|----------|--------|
| **Navigation** | `Patient.name.given` | ✅ Full |
| **Filtering** | `Observation.where(status='final')` | ✅ Full |
| **Collections** | `first()`, `last()`, `exists()`, `all()`, `count()` | ✅ Full |
| **Logic** | `and`, `or`, `xor`, `implies`, `not` | ✅ Full |
| **Math** | `+`, `-`, `*`, `/`, `mod`, `div` | ✅ Full |
| **String** | `substring()`, `startsWith()`, `contains()`, `matches()` | ✅ Full |
| **Types** | `is()`, `as()`, `ofType()` | ✅ Full |
| **Utility** | `now()`, `today()`, `trace()` | ✅ Full |

---

## 5. Advanced Configuration

### Strict Mode
Enable strict validation to catch common authoring mistakes:
- Choice-type suffix validation (e.g. `valueQuantity`).
- Property name validation.
- Polymorphic type narrowing enforcement.

```python
evaluate(res, "Patient.typo", options={"strict_mode": True}) # Raises error
```

### Custom Resource Types
The evaluator supports non-standard FHIR profiles:
```python
evaluate(resource, "MyCustom.field", resource_type="MyCustomResource")
```
