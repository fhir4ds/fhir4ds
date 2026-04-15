# WASM Engine

For developers building custom clinical applications, FHIR4DS provides a suite of **DuckDB C++ extensions** and **Python-based translation logic** that can be integrated directly into your own WebAssembly-powered browser application.

This is a "low-level" integration: you provide the UI and data management, and FHIR4DS provides the clinical logic intelligence.

## Prerequisites

To integrate the engine, you will need to host the following assets on your web server:

1.  **DuckDB Extensions**: `fhirpath.duckdb_extension.wasm` and `cql.duckdb_extension.wasm`.
2.  **Translator Wheel**: `fhir4ds_v2-0.0.1-py3-none-any.whl` (the CQL-to-SQL translation module for Pyodide).

You can find these files in the [FHIR4DS GitHub Repository](https://github.com/fhir4ds/fhir4ds/tree/main/web/wasm-demo/public).

## Loading C++ Extensions

To use `fhirpath` and `cql` UDFs in the browser, you must load the compiled `.wasm` extensions into your DuckDB instance.

```typescript
import * as duckdb from "@duckdb/duckdb-wasm";

const db = new duckdb.AsyncDuckDB(logger, worker);
await db.instantiate(wasmUrl);
const conn = await db.connect();

// Register and load the FHIR4DS extensions
const extBase = "/extensions/";

// 1. Register the extension files
await db.registerFileURL(
  "fhirpath.duckdb_extension.wasm",
  extBase + "fhirpath.duckdb_extension.wasm",
  duckdb.DuckDBDataProtocol.HTTP,
  false
);
await db.registerFileURL(
  "cql.duckdb_extension.wasm",
  extBase + "cql.duckdb_extension.wasm",
  duckdb.DuckDBDataProtocol.HTTP,
  false
);

// 2. Load the extensions
await conn.query("LOAD 'fhirpath.duckdb_extension.wasm'");
await conn.query("LOAD 'cql.duckdb_extension.wasm'");
```

## Loading Data from JavaScript

FHIR4DS executes logic against a DuckDB `resources` table. **The table name `resources` is mandatory** as the CQL translator generates SQL that hardcodes this identifier.

```typescript
// Define the mandatory FHIR4DS schema
await conn.query(`
  CREATE TABLE resources (
    id VARCHAR,
    resourceType VARCHAR,
    resource JSON,
    patient_ref VARCHAR
  )
`);

const patient = {
  resourceType: "Patient",
  id: "p1",
  name: [{ family: "Smith", given: ["Alice"] }]
};

const stmt = await conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
await stmt.query(
  patient.id, 
  patient.resourceType, 
  JSON.stringify(patient), 
  `Patient/${patient.id}`
);
await stmt.close();
```

## Executing CQL from JavaScript

To evaluate Clinical Quality Language (CQL) in the browser, you first translate the CQL string into optimized SQL using the FHIR4DS CQL translator, and then execute that SQL against DuckDB.

### 1. Translator Setup (Pyodide)

The `translator` is a wrapper around a **Pyodide Web Worker** that has the FHIR4DS CQL translation module installed. Because Python translation is a blocking operation, it must run in a background worker to keep the UI responsive.

A minimal implementation looks like this:

```typescript
// In your main thread
const translator = {
  async translate(cql: string): Promise<{ sql: string }> {
    // Send message to your Pyodide worker
    const response = await worker.postMessage({ type: 'translate', cql });
    return response.data;
  }
};
```

Inside the **Web Worker**, you initialize Pyodide and install the FHIR4DS translator wheel:

```python
# Inside the Pyodide worker
import micropip
await micropip.install("path/to/fhir4ds_v2-0.0.1-py3-none-any.whl")

from fhir4ds.cql.parser import parse_cql
from fhir4ds.cql import CQLToSQLTranslator
# ... logic to call translator.translate_library_to_population_sql()
```

### 2. Translate and Execute

Once your worker is ready, you can convert high-level clinical logic into high-performance DuckDB SQL.

```typescript
const cql = `
  library Example version '1.0.0'
  using FHIR version '4.0.1'
  context Patient
  define "Is Adult": AgeInYears() >= 18
`;

// 1. Translate
const { sql } = await translator.translate(cql);

// 2. Execute against DuckDB
const result = await conn.query(sql);

// 3. Process results
const rows = result.toArray().map(row => row.toJSON());
console.log("Results:", rows);
```

## Troubleshooting

### SharedArrayBuffer
DuckDB-WASM and Pyodide require `SharedArrayBuffer` to operate at peak performance. This requires your server to send specific HTTP headers:
*   `Cross-Origin-Opener-Policy: same-origin`
*   `Cross-Origin-Embedder-Policy: require-corp`

### CORS
Ensure your `.wasm` and `.whl` files are served with `Access-Control-Allow-Origin: *` if they are hosted on a different domain than your application.
