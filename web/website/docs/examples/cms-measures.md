---
hide_table_of_contents: true
description: "Run standard CMS eCQM quality measures against patient data in your browser, with no install and no server, and inspect population results."
---

# Quality Measures

Execute and audit standard CMS Quality Measures (eCQMs) directly against patient data in your browser.

import WasmDemoWC from '@site/src/components/WasmDemoWC';

<WasmDemoWC scenario="cms-measures" height="85vh" popout />

## Audit & Verification
*   **Population Logic:** Switch between measures to see aggregate statistics for the Initial Population, Denominator, and Numerator.
*   **Traceability:** Click the 🔍 icon in the results table to see the specific FHIR resources that contributed to a patient's inclusion in a population.
*   **Accuracy:** Compare the engine's results against validated benchmark data in real-time.
