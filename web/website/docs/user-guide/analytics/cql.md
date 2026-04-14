---
id: cql
title: Clinical Quality Language (CQL)
sidebar_label: CQL
---

# Clinical Quality Language (CQL)

Clinical Quality Language (CQL) is an HL7 standard designed for expressing clinical knowledge, such as quality measures and decision support rules. FHIR4DS provides a high-performance, SQL-native translator that allows you to execute complex clinical logic at population scale.

## 1. Overview

The `cql` module is the "brain" of the FHIR4DS toolkit. It handles the complexity of healthcare logic—such as time-interval math and terminology resolution—by translating it directly into optimized DuckDB SQL.

-   **Accuracy**: 100% compliance with the CQL grammar and parsing specification (3,044 tests).
-   **Speed**: Leveraging columnar execution provides a **~73× speedup** over traditional sequential engines.
-   **Transparency**: The resulting SQL is fully inspectable, allowing for auditability and debugging.

---

## 2. Basic Usage

Evaluating a clinical measure is handled via the high-level `evaluate_measure` API.

```python
import fhir4ds

# 1. Initialize connection
con = fhir4ds.create_connection()

# 2. Evaluate a CQL library
# This translates the logic to SQL and executes it across all patients
result = fhir4ds.evaluate_measure(
    library_path="./CMS165.cql",
    conn=con,
    parameters={"Measurement Period": ("2025-01-01", "2025-12-31")}
)

# 3. Analyze results as a pandas DataFrame
df = result.df()
```

---

## 3. The Translation Pipeline

FHIR4DS achieves its performance by treating CQL as a compiled language. The translation pipeline operates in four distinct stages:

### Stage 1: Parsing and AST Generation
The CQL source is parsed into an Expression Logical Model (ELM) compatible Abstract Syntax Tree (AST). This stage ensures the logic is syntactically correct.

### Stage 2: Logical Optimization
The engine analyzes the AST to simplify expressions, deduplicate library dependencies, and resolve terminology (ValueSets) into set-based identifiers.

### Stage 3: SQL Generation
Every node in the logic tree is translated into a corresponding DuckDB SQL fragment. This moves the logic from a patient-by-patient loop into a **set-based population query**.

### Stage 4: Columnar Execution
DuckDB executes the final SQL statement. Because the logic is now part of the database query, it utilizes modern CPU optimizations (SIMD) to process thousands of patients in milliseconds.

---

## 4. SQL Integration

In addition to full measure evaluation, FHIR4DS registers specialized clinical primitives directly in your DuckDB connection. You can use these in standard SQL queries:

-   **Age Calculation**: `AgeInYears()`, `AgeInMonths()`.
-   **Interval Logic**: `intervalContains()`, `intervalOverlaps()`.
-   **Code Membership**: `in_valueset()`.

---

:::tip 

Advanced Configuration
For details on low-level translator classes, ELM exports, and **Audit Mode** configuration, see the [CQL API Reference](/docs/api-reference/cql/).

:::
