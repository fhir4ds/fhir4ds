# SMART on FHIR

Experience the full FHIR4DS workbench connected to live EHR data. This demo follows a step-by-step flow: authenticate with a patient portal, load clinical data into DuckDB, and run complex queries.

import WasmDemoWC from '@site/src/components/WasmDemoWC';

<WasmDemoWC scenario="smart-flow" height="90vh" />

## The Workflow
1.  **Connect:** Select a sandbox (Epic or Cerner) and log in using the provided test credentials.

:::tip 

Sandbox Credentials
Use the following test accounts to log in to the sandboxes:
- **Epic**: `fhircamila` / `epicepic1`
- **Cerner**: `wilmasmart` / `Cerner01`

:::

2.  **Ingest:** FHIR4DS fetches your clinical history and loads it into a local, high-performance DuckDB instance.
3.  **Analyze:** Switch between the **CQL Playground** and **SDC Forms** to query your own real-world medical data.
4.  **Verify:** Use the **Patient Data** pane to see exactly which raw resources are being processed by the engine.
