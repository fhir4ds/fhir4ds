---
id: cql-clinic
title: CQL Clinic
sidebar_label: CQL Clinic
description: Learn CQL for FHIR step by step — 12 interactive lessons with instant feedback, running entirely in your browser via FHIR4DS-WASM.
hide_table_of_contents: true
---

# CQL Clinic

Learn Clinical Quality Language (CQL) hands-on. Twelve interactive lessons take
you from basic data types through a real CMS-style screening measure and FHIR
reference resolution — write CQL, run it against synthetic FHIR patients in
your browser, and get instant feedback on every expression.

:::info
First lesson load takes ~30–60 seconds for Pyodide to bring up FHIR4DS +
DuckDB-WASM (subsequent lessons reuse the engine). Your progress is saved in
the browser.
:::

import CqlClinicWC from '@site/src/components/CqlClinicWC';

<CqlClinicWC height="90vh" />

## Curriculum

*   **Beginner** — data types, comparisons, FHIR queries, strings & conversions.
*   **Intermediate** — null safety & three-valued logic, quantities & units,
    temporal logic, terminology (codes & code systems).
*   **Advanced** — query syntax (`where`/`return`/`let`/`sort`), building an
    eCQM with Initial Population, Denominator, Exclusion, and Numerator, a
    CMS124-style cervical cancer screening measure with age-banded windows,
    and following FHIR references between resources with `resolve()`.

Each lesson checks your CQL define-by-define against expected results, lets you
inspect the underlying patient data, drill into failed checks to see which
resources a define reads, and compare your work with the reference solution.
