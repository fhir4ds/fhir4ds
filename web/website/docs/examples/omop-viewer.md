---
id: omop-viewer
title: OMOP Demo
sidebar_label: OMOP Demo
description: FHIR R4 → OMOP CDM v5.5 on a real 25-patient Synthea cohort — browse the composed OMOP tables live in your browser.
hide_table_of_contents: true
---

# OMOP Demo

FHIR R4 mapped to **OMOP CDM v5.5**, live in your browser. This is the
Viewing Room filtered to its OMOP sample suite: a real 25-patient
[Synthea](https://synthetichealth.github.io/synthea/) cohort with a
71k-concept RxNorm vocabulary, composed through a ViewDefinition library
and resolved at query time through ConceptMap view joins.

:::info
First boot takes ~30–60 seconds (Pyodide + DuckDB-WASM download). The
full OMOP datasets are fetched from
[Hugging Face](https://huggingface.co/datasets/fhir4ds/omop-demo) —
no server, no token.
:::

import ViewingRoomWC from '@site/src/components/ViewingRoomWC';

<ViewingRoomWC height="85vh" suite="omop" popout />

## What to try

- **OMOP person** — 25 patients; gender resolves through the ConceptMap
  view join (male → 8507, female → 8532), birth dates split into
  year/month/day.
- **OMOP encounters** — 1,284 Synthea encounters mapped to
  `visit_occurrence`; visit classes resolve (IMP → 9201, AMB → 9202,
  EMER → 9203) while unmapped classes (VR, HH) fall to concept 0 — the
  real OMOP no-map convention.
- **OMOP medications (ViewDefinition)** — `drug_exposure` from
  MedicationRequest alone: one resource root, RxNorm concepts resolved
  through the ConceptMap view.
- **OMOP medications (SQLQuery)** — the same table via a **SQLQuery
  Library**: a 5-arm `UNION` across MedicationRequest, Dispense,
  Statement, Administration and Immunization — the cross-resource
  composition a single ViewDefinition cannot express. The composition
  DDL is derived live on every run.

## How it works

`Athena CONCEPT` → FHIR **ConceptMap resources** (chunked, standard
RxNorm classes) → a **conceptmap ViewDefinition** that flattens them into
a virtual mapping table → every OMOP table ViewDefinition **joins** that
view on `(source system, code)`. Swap the ConceptMap to swap
vocabularies; no ViewDefinition is regenerated.

Full details, the concept-map contract, coverage and ETL assumptions:
[OMOP CDM v5.5 Mapping](/docs/user-guide/modeling/omop-mapping).
