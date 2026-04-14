---
id: fhirpath
title: FHIRPath Evaluation
sidebar_label: FHIRPath
---

# FHIRPath Evaluation

FHIRPath is the standard expression language used throughout the FHIR ecosystem for navigation, extraction, and constraint validation. FHIR4DS provides a high-performance evaluation engine designed for large-scale analytical tasks.

## 1. Overview

The FHIRPath engine in FHIR4DS is built for accuracy and speed. It serves as the primary mechanism for extracting data from nested FHIR JSON during both CQL translation and direct SQL queries.

- **Full R4 Support**: 99.9% compliance with the FHIRPath R4 specification (935 tests).
- **Dual-Engine Architecture**: Seamless fallback between a native C++ DuckDB extension and a vectorized Python evaluator.
- **Set-Based Evaluation**: Designed to process entire populations simultaneously when used within the database.

---

## 2. Core Concepts

FHIRPath expressions are evaluated against a "focus" (the starting resource) and return a collection of elements.

### Navigation and Selection
Expressions use dot-notation to traverse the resource tree:
- `Patient.name.given`: Extracts all given names.
- `MedicationRequest.medication.code.coding.display`: Retrieves display text for medications.

### Filtering and Logic
Powerful built-in functions allow for complex data selection:
- **Filtering**: `Observation.where(status = 'final')`
- **Existence**: `Condition.evidence.exists()`
- **Boolean Logic**: `Patient.active and Patient.gender = 'female'`

---

## 3. Python Usage

For data exploration, validation, or small-scale processing, the `fhir4ds.fhirpath` module provides a direct evaluation interface.

```python
from fhir4ds.fhirpath import evaluate

patient = {
    "resourceType": "Patient",
    "name": [{"given": ["John"], "family": "Doe"}]
}

# Evaluate a path against a Python dictionary
names = evaluate(patient, "Patient.name.given")
# Result: ["John"]

# Using variables in expressions
count = evaluate(patient, "%names.count()", context={"names": names})
# Result: [1]
```

---

## 4. SQL Usage (Native Integration)

The most efficient way to evaluate FHIRPath is directly within DuckDB SQL queries. This utilizes the C++ extension to process FHIR resources without serializing them back to Python.

```sql
-- Registration happens automatically with fhir4ds.register(con)
SELECT 
    fhirpath_text(resource, 'Patient.id') as patient_id,
    fhirpath_text(resource, 'Patient.birthDate') as dob,
    fhirpath_bool(resource, 'Patient.active') as is_active
FROM resources
WHERE resourceType = 'Patient';
```

### Type-Safe UDFs
To optimize database performance, FHIR4DS provides several specialized User-Defined Functions (UDFs):

| Function | Return Type | Best For |
|----------|-------------|----------|
| `fhirpath()` | `VARCHAR[]` | Returning lists of values |
| `fhirpath_text()` | `VARCHAR` | Single string fields (names, codes) |
| `fhirpath_bool()` | `BOOLEAN` | Filters and flags |
| `fhirpath_number()` | `DOUBLE` | Quantities and counts |

---

:::tip 

Advanced Configuration
The engine supports advanced features like **Strict Mode** (for catching typos) and **Custom Resource Types**. For detailed parameter descriptions, see the [FHIRPath API Reference](/docs/api-reference/fhirpath/).

:::
