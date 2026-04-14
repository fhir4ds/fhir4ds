# CQL Playground

This live CQL sandbox allows you to write and execute Clinical Quality Language (CQL) queries directly in your browser using the FHIR4DS engine.

:::info
This playground uses **synthetic sample data** for 28 patients. To test against real EHR data, visit the [SMART on FHIR Demo](./smart-demo).
:::

import WasmDemoWC from '@site/src/components/WasmDemoWC';

<WasmDemoWC scenario="cql-sandbox" height="85vh" />

## Features
*   **Live Translation:** See the optimized DuckDB SQL generated from your CQL in real-time.
*   **In-Browser Execution:** Queries run directly against a local DuckDB-WASM instance.
*   **Verification:** Use the **Patient Data** pane to inspect raw FHIR resources and verify query results.
