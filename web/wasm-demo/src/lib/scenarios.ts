/** Scenario-based routing for the WASM demo workbench. */

export type Scenario = "workbench" | "cql-sandbox" | "sdc-forms" | "cms-measures" | "smart-flow";

export type Tab = "playground" | "cms" | "smart" | "forms";

export interface ScenarioConfig {
  /** Which tabs are visible in this scenario */
  visibleTabs: Tab[];
  /** Whether the tab navigation bar is shown */
  showTabNav: boolean;
  /** Whether sample-data selectors are shown */
  showSampleSelectors: boolean;
  /** Default tab to activate */
  defaultTab: Tab;
  /** Human-readable label */
  label: string;
}

export const SCENARIO_CONFIGS: Record<Scenario, ScenarioConfig> = {
  workbench: {
    visibleTabs: ["playground", "cms", "smart", "forms"],
    showTabNav: true,
    showSampleSelectors: true,
    defaultTab: "playground",
    label: "FHIR4DS Workbench",
  },
  "cql-sandbox": {
    visibleTabs: ["playground"],
    showTabNav: false,
    showSampleSelectors: true,
    defaultTab: "playground",
    label: "CQL Sandbox",
  },
  "sdc-forms": {
    visibleTabs: ["forms"],
    showTabNav: false,
    showSampleSelectors: true,
    defaultTab: "forms",
    label: "SDC Forms",
  },
  "cms-measures": {
    visibleTabs: ["cms"],
    showTabNav: false,
    showSampleSelectors: true,
    defaultTab: "cms",
    label: "CMS Measures",
  },
  "smart-flow": {
    visibleTabs: ["smart"],
    showTabNav: false,
    showSampleSelectors: false,
    defaultTab: "smart",
    label: "SMART on FHIR",
  },
};

/** 
 * Parse the ?scenario= URL parameter. 
 * Supports both standard query params and hash-based params (for some iframe/proxy setups).
 */
export function getScenarioFromURL(): Scenario {
  const searchParams = new URLSearchParams(window.location.search);
  let raw = searchParams.get("scenario");
  
  // Fallback to hash parsing if search is empty (e.g. /#/?scenario=...)
  if (!raw && window.location.hash.includes("scenario=")) {
    const hashPart = window.location.hash.split("?")[1] || window.location.hash.substring(1);
    const hashParams = new URLSearchParams(hashPart);
    raw = hashParams.get("scenario");
  }

  if (raw && raw in SCENARIO_CONFIGS) {
    return raw as Scenario;
  }
  return "workbench";
}

export function getScenarioConfig(scenario: Scenario): ScenarioConfig {
  return SCENARIO_CONFIGS[scenario];
}

/**
 * In smart-flow, after authentication the CQL and SDC tabs are revealed.
 * The SMART tab itself is hidden once connected (the header shows the
 * patient banner + disconnect button instead).
 */
export function getEffectiveConfig(scenario: Scenario, isAuthenticated: boolean): ScenarioConfig {
  if (scenario === "smart-flow" && isAuthenticated) {
    return {
      ...SCENARIO_CONFIGS["smart-flow"],
      // Hide the SMART connect tab once signed in; CQL + SDC use EHR data
      visibleTabs: ["playground", "forms"],
      showTabNav: true,
      showSampleSelectors: false,
      defaultTab: "playground",
    };
  }
  return SCENARIO_CONFIGS[scenario];
}
