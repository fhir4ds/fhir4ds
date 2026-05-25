---
id: duckdb
title: Native DuckDB Integration
---

# Native DuckDB Integration

FHIR4DS achieves industry-leading performance by executing clinical logic directly within the database engine. By leveraging custom C++ extensions, complex FHIRPath and CQL operations run at native speeds, eliminating the "data tax" of moving information between SQL and application layers.

## 1. Why In-Database Logic?

Traditional healthcare data pipelines suffer from significant overhead when serializing large FHIR JSON objects for processing in external virtual machines (JVM, Python). FHIR4DS eliminates this by:

-   **Zero-ETL**: Query raw, nested FHIR JSON directly in its original format.
-   **Vectorized Execution**: Process entire columns of patient data using modern CPU instructions (SIMD) via DuckDB.
-   **Pushdown Optimization**: Database filters are applied directly to the JSON columns, reducing the amount of data processed.

---

## 2. The fhirpath() UDF Family

FHIR4DS provides a suite of type-safe User-Defined Functions (UDFs) for high-speed extraction.

| Function | Return Type | Best For |
|----------|-------------|----------|
| `fhirpath(json, path)` | `VARCHAR[]` | Returning all matching values as a list. |
| `fhirpath_text(json, path)` | `VARCHAR` | Single string fields (e.g., `Patient.id`). |
| `fhirpath_bool(json, path)` | `BOOLEAN` | Filters and flags (e.g., `Patient.active`). |
| `fhirpath_number(json, path)` | `DOUBLE` | Numeric extraction (e.g., `Observation.value.value`). |
| `fhirpath_json(json, path)` | `VARCHAR` | Extracting a nested JSON sub-object. |

```sql
-- Efficiently filter and extract in a single pass
SELECT 
    fhirpath_text(resource, 'Patient.id') as patient_id,
    fhirpath_text(resource, 'Patient.gender') as gender,
    fhirpath_number(resource, 'Patient.extension.where(url="...").value') as risk_score
FROM resources
WHERE fhirpath_bool(resource, 'Patient.active') = true;
```

---

## 3. The cql() UDF Family

Beyond standard FHIRPath, the engine registers specialized primitives required for Clinical Quality Language (CQL). These handle healthcare-specific logic that is difficult to express in standard SQL:

-   **Clinical Primitives**: `AgeInYears(resource)`, `AgeInMonths(resource)`, `AgeInDays(resource)` — extract birthDate from the resource and compute age relative to today.
-   **At-Time Variants**: `AgeInYearsAt(resource, date)`, `AgeInMonthsAt(resource, date)` — compute age as of a specific date.
-   **Interval Logic**: `intervalContains()`, `intervalOverlaps()`, `intervalStart()`, `intervalEnd()`.
-   **Terminology**: `in_valueset(resource, path, valueset_url)` for high-speed membership checks.

```sql
-- Using clinical primitives in standard SQL
SELECT 
    fhirpath_text(resource, 'Patient.id') as id,
    AgeInYears(resource) as age
FROM resources
WHERE resourceType = 'Patient';

-- Terminology membership checks use (resource, path, valueset_url)
SELECT fhirpath_text(resource, 'Observation.id') as obs_id
FROM resources
WHERE in_valueset(resource, 'code', 'http://example.org/ValueSet/diabetes-codes');
```

---

## 4. The "Best-Available" Strategy

FHIR4DS uses a "hybrid" implementation strategy to ensure portability:

1.  **C++ Primary**: In environments that support DuckDB extensions (Native Python, WASM), high-performance C++ binaries are loaded automatically.
2.  **Python Fallback**: In restricted environments, the library transparently falls back to vectorized Python UDFs. This ensures your analytical code is portable from a local workstation to a locked-down production environment.

---

## 5. Performance Optimization Tips

-   **Use Type-Specific UDFs**: Always prefer `fhirpath_bool` or `fhirpath_text` over the generic `fhirpath` function when you expect a single value. This avoids array serialization overhead.
-   **Filter Early**: Use FHIRPath UDFs in the `WHERE` clause. DuckDB can often optimize these filters to skip unnecessary data processing.
-   **Register Once**: A single call to `fhir4ds.register(con)` prepares the entire environment.

---

:::tip 

Full UDF Reference
For a complete list of all registered SQL functions and their parameters, see the [API Reference](/docs/api-reference/fhir4ds).

:::
