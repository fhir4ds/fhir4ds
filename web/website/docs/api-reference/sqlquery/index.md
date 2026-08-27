---
id: sqlquery
title: sqlquery
sidebar_label: sqlquery
---

# `fhir4ds.sqlquery`

The SQL-on-FHIR v2 **Analytics Layer**: FHIR `Library` resources that
conform to the [SQLQuery](https://sql-on-fhir.org/ig/StructureDefinition/SQLQuery)
and [SQLView](https://sql-on-fhir.org/ig/StructureDefinition/SQLView)
profiles. A SQLQuery carries typed, FHIR-declared parameters plus SQL
content, so reusable analytics queries can travel as FHIR resources —
stored in repositories, referenced by canonical URL, and executed
anywhere the FHIR4DS engine runs.

## 1. At a Glance

```python
from fhir4ds.sqlquery import (
    parse_library,      # Library dict/JSON -> SQLQuery or SQLView
    parse_sqlquery,     # Strict parse against the SQLQuery profile
    parse_sqlview,      # Strict parse against the SQLView profile
    SQLQueryRunner,     # Execute against a DuckDB connection
)
```

A SQLQuery is a FHIR `Library` whose `content` entry holds SQL (base64
`data`, `contentType` `application/sql`). Queries may declare
`parameter`s — referenced in the SQL as `$name` — and reference other
queries or ViewDefinitions through `relatedArtifact` canonical URLs. Each
`depends-on` label becomes a virtual table in the SQL: the runner
resolves the dependency graph, materializes each dependency as a view,
and executes the query against them.

A **SQLView** is the parameter-free variant (`parameter 0..0`) — a
reusable named query that other queries can depend on.

## 2. Function Reference

### `parse_library`
`parse_library(input_) -> SQLQuery | SQLView`

Parse a Library dict or JSON string into its profiled form. The profile
is detected from `meta.profile`; unknown profiles fall back to SQLQuery.

| Parameter | Type | Description |
|-----------|------|-------------|
| `input_` | `dict \| str` | A Library object or its JSON text. |

### `parse_sqlquery`
`parse_sqlquery(input_) -> SQLQuery`

Strict parse against the SQLQuery profile — validates the canonical,
required fields (`status`, `type`, content dialect), and parameter
declarations (primitive FHIR types only).

### `parse_sqlview`
`parse_sqlview(input_) -> SQLView`

Strict parse against the SQLView profile; rejects any `parameter`
declaration.

---

## 3. Class Reference

### `SQLQueryRunner`
`SQLQueryRunner(connection, resolver, *, source_table="resources")`

Executes SQLQuery / SQLView resources against a DuckDB connection. Each
dependency is materialized with `CREATE OR REPLACE VIEW`, so re-running
the same query is idempotent.

| Parameter | Type | Description |
|-----------|------|-------------|
| `connection` | `duckdb.DuckDBPyConnection` | Caller-supplied connection. |
| `resolver` | `DependencyResolver` | Callable mapping a canonical URL to the referenced resource — a parsed ViewDefinition/SQLQuery/SQLView, a ViewDefinition dict, or a Library dict. May raise to signal "not found". |
| `source_table` | `str` | The physical table that ViewDefinition dependencies read from (default `"resources"`). |

#### Methods

- **`execute(library, parameters=None) -> list[tuple]`**: Execute a
  parsed SQLQuery/SQLView (or a Library dict). `parameters` is a name →
  value dict, coerced to the declared FHIR types; required parameters
  must be present. Raises typed errors for unresolvable
  `relatedArtifact` (`SQLQueryMaterializationError`), dependency cycles
  (`SQLQueryCycleError`), parameter type mismatches or missing
  parameters (`SQLQueryTypeError`), and unsupported content dialects
  (`UnsupportedDialectError`).

---

## 4. Example

```python
import base64
import fhir4ds
from fhir4ds.sqlquery import parse_sqlquery, SQLQueryRunner, SQLQUERY_PROFILE_CANONICAL

def b64(text):
    return base64.b64encode(text.encode()).decode()

vd_canonical = "https://example.org/ViewDefinition/PatientIds"
vd_dict = {
    # SQL-on-FHIR v2 typed resourceType (no "name" on the root select).
    "url": vd_canonical,
    "resource": "Patient",
    "select": [{"column": [{"path": "id", "name": "id", "type": "id"}]}],
}

query = {
    "resourceType": "Library",
    "url": "https://example.org/SQL/Seniors",
    "meta": {"profile": [SQLQUERY_PROFILE_CANONICAL]},
    "status": "active",
    "type": {"coding": [{"code": "sql-query"}]},
    # The label "pt" becomes a virtual table, resolved via the canonical.
    "relatedArtifact": [
        {"type": "depends-on", "label": "pt", "resource": vd_canonical},
    ],
    "parameter": [{"name": "min_year", "type": "integer", "use": "in"}],
    "content": [{
        "contentType": "application/sql",
        "data": b64("SELECT id FROM pt WHERE id LIKE $min_year || '%'"),
    }],
}

con = fhir4ds.create_connection()
runner = SQLQueryRunner(
    connection=con,
    resolver=lambda canonical: vd_dict if canonical == vd_canonical else None,
)
rows = runner.execute(parse_sqlquery(query), parameters={"min_year": 1970})
```
