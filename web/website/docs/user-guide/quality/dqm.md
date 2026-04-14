---
id: dqm
title: Digital Quality Measures (DQM)
sidebar_label: DQM
---

# Digital Quality Measures (DQM)

The `dqm` module is the high-level orchestrator of the FHIR4DS toolkit. It manages the end-to-end lifecycle of clinical quality measure evaluation, from loading official CMS bundles to generating auditable, human-readable evidence.

## 1. The DQM Lifecycle

Evaluating quality measures with FHIR4DS typically follows a four-step process that transitions from raw FHIR data to finalized reports:

1.  **Data Loading**: FHIR resources (QI-Core or US-Core) are loaded into a `resources` table in DuckDB.
2.  **Measure Parsing**: The engine parses a FHIR `Measure` resource to identify populations (e.g., Initial Population, Numerator).
3.  **Vectorized Evaluation**: The associated CQL logic is translated into optimized SQL and executed across the entire population.
4.  **Audit & Reporting**: Results are aggregated into a FHIR `MeasureReport` or analyzed as a DataFrame, complete with evidence trails.

---

## 2. Evaluating CMS Bundles

FHIR4DS is designed to work out-of-the-box with official CMS eCQM bundles. It supports the **QI-Core 2025** profile with near-perfect accuracy.

```python
import fhir4ds
from fhir4ds.dqm import MeasureEvaluator

# Initialize the evaluator
con = fhir4ds.create_connection()
evaluator = MeasureEvaluator(con)

# Load and execute an official CMS measure bundle
result = evaluator.evaluate(
    measure_bundle="./CMS124-bundle.json",
    cql_library_path="./CMS124.cql",
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")}
)

# Analyze population counts
print(result.populations)
```

---

## 3. Explainable Clinical Reasoning

A core mission of FHIR4DS is to eliminate the "black box" nature of clinical reasoning. Every decision made by the engine is backed by verifiable evidence.

### Audit Modes
You can control the depth of evidence captured during evaluation:
-   **Population Audit**: Captures the specific FHIR resources that satisfied the population criteria.
-   **Full Audit**: Produces a "logical breadcrumb" trail through every node in the CQL expression tree, allowing you to see exactly where a patient met or failed a criterion.

### Evidence Narratives
The engine includes a narrative generator that translates logical evidence into plain English. This enables clinicians to verify results without reading code:
> *"Patient has a blood pressure reading of 120/80 during the measurement period."*

---

## 4. SMART on FHIR Integration

The DQM module is fully compatible with WebAssembly, allowing the same production-grade measure evaluation to run entirely in the browser. This enables SMART on FHIR applications to retrieve data from an EHR and evaluate quality measures locally, ensuring patient data never leaves the device.

---

:::tip 

Full API Reference
For technical details on the `MeasureEvaluator` class, `MeasureResult` data structures, and `AuditMode` enums, see the [DQM API Reference](/docs/api-reference/dqm/).

:::
