/**
 * Demo ValueSet resources for the CQL playground (FHIR4-49).
 *
 * The browser engine answers ValueSet membership from the C++ in-process
 * valueset cache, not from a table, so a `[Condition: "Some VS"]` retrieve is
 * only answerable when the app SEEDS that cache. `useDuckDB` seeds it from
 * whatever `ValueSet` resources the loaded dataset carries — these are the
 * demo's own, keyed to codes the synthetic cohort actually has
 * (`src/lib/sample-data.ts`), so a valueset retrieve demonstrably works.
 *
 * Two shapes are exercised on purpose:
 *   - `compose.include[].concept[]` (the authoring form)
 *   - `expansion.contains[]`     (the VSAC pre-expanded form)
 */
export const SAMPLE_VALUESETS: Record<string, unknown>[] = [
  {
    resourceType: "ValueSet",
    id: "vs-diabetes",
    url: "http://fhir4ds.org/ValueSet/diabetes",
    name: "Diabetes mellitus",
    title: "Diabetes mellitus (demo)",
    status: "active",
    compose: {
      include: [
        {
          system: "http://snomed.info/sct",
          concept: [{ code: "73211009", display: "Diabetes mellitus" }],
        },
      ],
    },
  },
  {
    resourceType: "ValueSet",
    id: "vs-hypertension",
    url: "http://fhir4ds.org/ValueSet/hypertension",
    name: "Hypertension",
    title: "Hypertension (demo)",
    status: "active",
    // Pre-expanded form (what VSAC value sets look like in the wild).
    expansion: {
      contains: [
        {
          system: "http://snomed.info/sct",
          code: "38341003",
          display: "Hypertension",
        },
      ],
    },
  },
  {
    resourceType: "ValueSet",
    id: "vs-hba1c",
    url: "http://fhir4ds.org/ValueSet/hba1c",
    name: "Hemoglobin A1c",
    title: "Hemoglobin A1c panel (demo)",
    status: "active",
    expansion: {
      contains: [
        {
          system: "http://loinc.org",
          code: "4548-4",
          display: "Hemoglobin A1c/Hemoglobin.total in Blood",
        },
      ],
    },
  },
];
