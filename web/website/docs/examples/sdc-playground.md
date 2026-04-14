# SDC Forms

Explore Structured Data Capture (SDC) forms with real-time FHIRPath evaluation and SQL-on-FHIR pre-population.

import WasmDemoWC from '@site/src/components/WasmDemoWC';

<WasmDemoWC scenario="sdc-forms" height="85vh" />

## Key Capabilities
*   **Calculated Expressions:** Complex logic like the PHQ-9 total score is evaluated instantly using the FHIR4DS engine.
*   **SQL-on-FHIR Pre-population:** Automatically fill form fields by querying the local DuckDB database (e.g., fetching the latest lab results).
*   **Live JSON Editing:** Modify the Questionnaire JSON on the left and see the rendered form update immediately on the right.
