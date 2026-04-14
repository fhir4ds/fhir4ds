---
id: dqm
title: dqm
sidebar_label: dqm
---

# `fhir4ds.dqm`

Digital Quality Measure orchestrator and audit engine for FHIR-based CQL measures.

## 1. At a Glance

The high-level orchestration interface:

```python
from fhir4ds.dqm import (
    MeasureEvaluator,  # Main orchestrator
    AuditEngine,       # Evidence trail generator
    AuditMode,         # Enum: NONE, POPULATION, FULL
    AuditOrStrategy,   # Enum: ALL, TRUE_BRANCH
)
```

---

## 2. Class Reference

### `MeasureEvaluator`
`MeasureEvaluator(conn, audit_or_strategy=AuditOrStrategy.TRUE_BRANCH)`

The primary class for executing end-to-end quality measures.

| Parameter | Type | Description |
|-----------|------|-------------|
| `conn` | `duckdb.DuckDBPyConnection` | DuckDB connection with FHIR data loaded. |
| `audit_or_strategy` | `AuditOrStrategy` | (Optional) Strategy for `OR` evidence collection. |

#### Methods

- **`evaluate(measure_bundle, cql_library_path, parameters=None, audit=False) -> MeasureResult`**: Evaluate a measure bundle against loaded FHIR data.
- **`summary_report() -> str`**: Generate a summary report of the last evaluation.

---

## 3. Data Structures

### `MeasureResult`
The object returned by evaluation methods.

| Property | Type | Description |
|----------|------|-------------|
| `populations` | `dict` | Aggregated counts for each population (IP, NUMER, etc). |
| `patient_results` | `list` | Detailed results for every patient in the set. |
| `evidence` | `dict` | Logical evidence trails (if audit mode enabled). |
| `sql` | `str` | The optimized DuckDB SQL used for execution. |

---

## 4. Configuration Enums

### `AuditMode`
Controls the depth of evidence captured.
- **`NONE`**: No evidence capture (Fastest).
- **`POPULATION`**: Captures resources that satisfied population criteria.
- **`FULL`**: Captures every logical sub-expression evaluation.

### `AuditOrStrategy`
Defines how evidence is collected for `OR` operations.
- **`ALL`**: Collect evidence from all branches of the OR.
- **`TRUE_BRANCH`**: Only collect evidence from the specific branch that evaluated to `true`.

---

## 5. Compliance

| Metric | Status |
|--------|--------|
| **CMS eCQM (QI-Core 2025)** | 42/46 Measures (100% accuracy) |
| **Audit Coverage** | 100% expression-level traceability |
