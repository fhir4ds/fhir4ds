/**
 * Sample registry: the six engine-verified gallery samples (public/samples/).
 * Each sample = { name, slug, description, vdUrl, resourcesUrl }.
 */

export interface Sample {
  slug: string;
  name: string;
  description: string;
  vdUrl: string;
  resourcesUrl: string;
  /** Optional pre-computed composition DDL (legacy; live derivation is now the default). */
  setupUrl?: string;
  /** Gallery suite grouping (dropdown optgroups / ?suite= filter). */
  suite: SampleSuite;
}

export type SampleSuite = "general" | "uscore" | "omop";

export const SUITE_LABELS: Record<SampleSuite, string> = {
  general: "General",
  uscore: "US Core",
  omop: "OMOP",
};

export const SAMPLES: Sample[] = [
  {
    slug: "patient-demographics",
    suite: "general",
    name: "Patient Demographics",
    description: "One row per Patient: id, name, gender, birthDate (the default).",
    vdUrl: "samples/patient-demographics/viewdefinition.json",
    resourcesUrl: "samples/patient-demographics/resources.ndjson",
  },
  {
    slug: "patient-addresses",
    suite: "general",
    name: "Patient Addresses",
    description: "forEach over Patient.address — one row per address.",
    vdUrl: "samples/patient-addresses/viewdefinition.json",
    resourcesUrl: "samples/patient-addresses/resources.ndjson",
  },
  {
    slug: "patient-contact-address-union",
    suite: "general",
    name: "Patient + Contact Address Union",
    description: "unionAll of patient and contact addresses (IG 2.0.0 example).",
    vdUrl: "samples/patient-contact-address-union/viewdefinition.json",
    resourcesUrl: "samples/patient-contact-address-union/resources.ndjson",
  },
  {
    slug: "us-core-blood-pressures",
    suite: "uscore",
    name: "US Core Blood Pressures",
    description: "Deep forEach + where on component coding (LOINC 85354-9 / 8480-6 / 8462-4).",
    vdUrl: "samples/us-core-blood-pressures/viewdefinition.json",
    resourcesUrl: "samples/us-core-blood-pressures/resources.ndjson",
  },
  {
    slug: "questionnaire-response-items",
    suite: "general",
    name: "Questionnaire Response Items",
    description: "select.repeat over a nested QuestionnaireResponse item tree.",
    vdUrl: "samples/questionnaire-response-items/viewdefinition.json",
    resourcesUrl: "samples/questionnaire-response-items/resources.ndjson",
  },
  {
    slug: "observation-values",
    suite: "general",
    name: "Observation Values",
    description: "collection:true + typed columns (component codes & values as arrays).",
    vdUrl: "samples/observation-values/viewdefinition.json",
    resourcesUrl: "samples/observation-values/resources.ndjson",
  },
  {
    slug: "omop-patient",
    suite: "omop",
    name: "OMOP person",
    description: "OMOP CDM v5.5 person table as a ViewDefinition (concept-map join for gender).",
    vdUrl: "samples/omop-patient/viewdefinition.json",
    resourcesUrl: "samples/omop-patient/resources.ndjson",
  },
  {
    slug: "omop-drug-exposure",
    suite: "omop",
    name: "OMOP drug_exposure (request arm)",
    description: "OMOP CDM v5.5 drug_exposure child view — RxNorm concept join + provenance type.",
    vdUrl: "samples/omop-drug-exposure/viewdefinition.json",
    resourcesUrl: "samples/omop-drug-exposure/resources.ndjson",
  },
  {
    slug: "omop-drug-exposure-sqlquery",
    suite: "omop",
    name: "OMOP drug_exposure (SQLQuery)",
    description: "Cross-resource drug_exposure via a SQLQuery Library — MedicationRequest, Dispense, Statement, Administration and Immunization unioned over the OMOP views (composed live on every run).",
    vdUrl: "samples/omop-drug-exposure-sqlquery/viewdefinition.json",
    resourcesUrl: "samples/omop-drug-exposure-sqlquery/resources.ndjson",
  },
  {
    slug: "omop-conditions-analysis",
    suite: "omop",
    name: "OMOP conditions (SQLQuery)",
    description: "condition_occurrence joined to person demographics — an analytical SQLQuery Library over the OMOP views (composed live on every run).",
    vdUrl: "samples/omop-conditions-analysis/viewdefinition.json",
    resourcesUrl: "samples/omop-conditions-analysis/resources.ndjson",
  },
];

export const DEFAULT_SAMPLE = SAMPLES[0];

export function sampleBySlug(slug: string): Sample | undefined {
  return SAMPLES.find((s) => s.slug === slug);
}

/**
 * Resolve the active sample list from the URL's ?suite= parameter.
 * Unknown/absent values return the full list (suites = null).
 */
export function activeSamples(): { samples: Sample[]; suite: SampleSuite | null } {
  const raw = new URLSearchParams(window.location.search).get("suite");
  if (raw && (raw === "general" || raw === "uscore" || raw === "omop")) {
    return { samples: SAMPLES.filter((s) => s.suite === raw), suite: raw };
  }
  return { samples: SAMPLES, suite: null };
}

/**
 * Sample-asset base: null = document-relative (standalone entry default);
 * set by the web-component entry to the bundle's own base URL so samples
 * resolve correctly regardless of the host page's URL.
 */
let sampleBase: string | null = null;

export function setSampleBase(base: string): void {
  sampleBase = base;
}

export function sampleUrl(path: string): string {
  if (sampleBase !== null) return `${sampleBase.replace(/\/$/, "")}/${path}`;
  return new URL(path, document.baseURI).href;
}

/** Parse NDJSON or a JSON array of resources; a single object is wrapped. */
export function parseResourcesInput(text: string): {
  resources: Array<Record<string, unknown>>;
  error: string | null;
} {
  const trimmed = text.trim();
  if (!trimmed) return { resources: [], error: null };
  // JSON array (single object wrapped into one by the caller contract)
  if (trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      if (!Array.isArray(parsed)) return { resources: [], error: "expected a JSON array" };
      const bad = parsed.findIndex((r) => r === null || typeof r !== "object" || Array.isArray(r));
      if (bad >= 0) return { resources: [], error: `element ${bad + 1} is not a JSON object` };
      return { resources: parsed, error: null };
    } catch (e) {
      return { resources: [], error: `invalid JSON array: ${(e as Error).message}` };
    }
  }
  // NDJSON: one resource per line
  const lines = trimmed.split(/\r?\n/);
  const resources: Array<Record<string, unknown>> = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line) continue;
    try {
      const r = JSON.parse(line);
      if (r === null || typeof r !== "object" || Array.isArray(r)) {
        return { resources: [], error: `line ${i + 1}: not a JSON object` };
      }
      resources.push(r);
    } catch (e) {
      return { resources: [], error: `line ${i + 1}: ${(e as Error).message}` };
    }
  }
  return { resources, error: null };
}

/** Count resources by resourceType for the resources-pane stats. */
export function resourceStats(resources: Array<Record<string, unknown>>): {
  total: number;
  byType: Array<{ type: string; count: number }>;
} {
  const counts = new Map<string, number>();
  for (const r of resources) {
    const rt = typeof r.resourceType === "string" ? r.resourceType : "Unknown";
    counts.set(rt, (counts.get(rt) ?? 0) + 1);
  }
  return {
    total: resources.length,
    byType: [...counts.entries()]
      .map(([type, count]) => ({ type, count }))
      .sort((a, b) => b.count - a.count || a.type.localeCompare(b.type)),
  };
}
