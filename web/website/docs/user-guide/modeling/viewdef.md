---
id: viewdef
title: ViewDefinition Modeling
sidebar_label: ViewDefinition
---

# ViewDefinition Modeling

FHIR4DS implements the HL7 SQL-on-FHIR v2 specification, providing a standardized, portable way to flatten complex FHIR resources into analytical tables. This allows data scientists to query FHIR using standard SQL joins and aggregations without manual ETL.

## 1. Overview

The `viewdef` module translates declarative JSON **ViewDefinitions** into optimized DuckDB SQL. It allows you to define projections of FHIR resources that are independent of the underlying storage engine.

-   **Spec Compliant**: 100% compliance with the SQL-on-FHIR v2 specification (134 tests).
-   **Portable**: Views defined in FHIR4DS can be used across any spec-compliant implementation.
-   **SQL-Native**: Generates inspectable DuckDB SQL that leverages columnar performance.

---

## 2. Core Concepts

A ViewDefinition consists of three primary components:

### The Resource Focus
Specifies the base FHIR resource type (e.g., `Patient`, `Observation`, `Encounter`).

### Select and Column
Defines the mapping from FHIRPath expressions to SQL columns.
-   **Path**: The FHIRPath used to extract data.
-   **Name**: The resulting SQL column name.

### Flattening (forEach)
Handles one-to-many relationships (e.g., a Patient with multiple names or an Observation with multiple components).
-   **`forEach`**: Creates one row for every matching element (Inner Join semantics).
-   **`forEachOrNull`**: Preserves the parent row even if the collection is empty (Left Join semantics).

---

## 3. Quick Start

Flattening a resource involves defining the mapping and calling the generator.

```python
import json
import fhir4ds

# 1. Define the View (Portable JSON)
view_definition = {
    "resource": "Patient",
    "select": [{
        "column": [
            {"path": "id", "name": "patient_id"},
            {"path": "gender", "name": "gender"},
            {"path": "name.first().family", "name": "last_name"}
        ]
    }]
}

# 2. Generate optimized DuckDB SQL
sql = fhir4ds.generate_view_sql(json.dumps(view_definition))

# 3. Execute
con = fhir4ds.create_connection()
df = con.execute(sql).df()
```

---

## 4. Complex Modeling

ViewDefinitions support deep nesting and filtering, enabling the creation of production-grade analytical datasets.

```python
view_definition = {
    "resource": "Observation",
    "where": [{"path": "status = 'final'"}],
    "select": [
        {"column": [{"path": "id", "name": "obs_id"}]},
        {
            "forEach": "component",
            "column": [
                {"path": "code.coding.first().code", "name": "comp_code"},
                {"path": "value.ofType(Quantity).value", "name": "comp_value"}
            ]
        }
    ]
}
```

This example produces one row per observation component, filtering out any resources that are not in a 'final' status.

---

:::tip 

Spec & Compliance
For technical details on the generator class and the full compliance report, see the [ViewDefinition API Reference](/docs/api-reference/viewdef/).

:::
