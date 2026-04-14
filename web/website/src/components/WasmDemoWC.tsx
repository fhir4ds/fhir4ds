/**
 * WasmDemoWC — Docusaurus wrapper for the <fhir4ds-demo> Web Component.
 *
 * Handles:
 *   - SSR: BrowserOnly guard (Docusaurus pre-renders; the WC requires browser APIs)
 *   - Script deduplication: fhir4ds-demo.js is only injected once per page
 *   - Lazy launch: optional "click to launch" gate for heavy pages
 *
 * Usage in .mdx:
 *   import WasmDemoWC from '@site/src/components/WasmDemoWC';
 *   <WasmDemoWC scenario="cql-sandbox" />
 *   <WasmDemoWC scenario="smart-flow" height="90vh" lazyLaunch />
 */

import { useState, useCallback } from "react";
import type { ReactNode } from "react";
import BrowserOnly from "@docusaurus/BrowserOnly";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import styles from "./WasmDemo.module.css";

const SCRIPT_ID = "fhir4ds-wc-bundle";

function injectWcScript(scriptSrc: string): void {
  if (document.getElementById(SCRIPT_ID)) return;
  const script = document.createElement("script");
  script.id = SCRIPT_ID;
  script.type = "module";
  script.src = scriptSrc;
  document.head.appendChild(script);
}

type Scenario =
  | "workbench"
  | "cql-sandbox"
  | "sdc-forms"
  | "cms-measures"
  | "smart-flow";

interface WasmDemoWCProps {
  /** Scenario to display. Default: 'workbench' */
  scenario?: Scenario;
  /** CSS height. Default: '80vh' */
  height?: string;
  /** Show a "Launch Demo" splash screen before loading the heavy WASM bundle. */
  lazyLaunch?: boolean;
  /** Override display title in the lazy launch card */
  title?: string;
  /** Override description in the lazy launch card */
  description?: string;
  /** Override the SMART OAuth redirect URI */
  redirectUri?: string;
}

const SCENARIO_META: Record<string, { title: string; desc: string }> = {
  workbench: {
    title: "FHIR4DS Workbench",
    desc: "Full CQL, SDC, CMS, and SMART on FHIR workbench.",
  },
  "cql-sandbox": {
    title: "CQL Sandbox",
    desc: "Translate Clinical Quality Language to DuckDB SQL and execute queries in your browser.",
  },
  "sdc-forms": {
    title: "SDC Forms Demo",
    desc: "Render FHIR Questionnaires with live FHIRPath calculations and patient pre-population.",
  },
  "cms-measures": {
    title: "CMS Measures",
    desc: "Run CMS quality measures in your browser with full audit evidence trails.",
  },
  "smart-flow": {
    title: "SMART on FHIR",
    desc: "Connect to a live EHR sandbox (Epic, Cerner) and query real patient data.",
  },
};

function LaunchCard({
  scenario,
  title,
  description,
  onLaunch,
}: {
  scenario: string;
  title?: string;
  description?: string;
  onLaunch: () => void;
}) {
  const meta = SCENARIO_META[scenario] ?? SCENARIO_META.workbench;
  return (
    <div className={styles.launcher}>
      <div className={styles.launcherContent}>
        <div className={styles.launcherIcon}>🌐</div>
        <h3 className={styles.launcherTitle}>{title ?? meta.title}</h3>
        <p className={styles.launcherDesc}>{description ?? meta.desc}</p>
        <div className={styles.launcherBadges}>
          <span className={styles.badge}>🔒 Zero server</span>
          <span className={styles.badge}>🌐 WebAssembly</span>
          <span className={styles.badge}>⚡ C++ extensions</span>
          {scenario === "smart-flow" && (
            <span className={styles.badge}>🏥 Live EHR data</span>
          )}
        </div>
        <button className={styles.launchBtn} onClick={onLaunch}>
          Launch Demo
        </button>
        <p className={styles.launcherNote}>
          Requires Chrome, Firefox, or Edge. First load downloads ~50 MB of WASM
          assets.
        </p>
      </div>
    </div>
  );
}

function WcEmbed({
  scenario,
  height,
  scriptSrc,
  redirectUri,
}: {
  scenario: string;
  height: string;
  scriptSrc: string;
  redirectUri?: string;
}) {
  injectWcScript(scriptSrc);

  // Default redirect URI: current page URL (so OAuth popup redirects back here)
  const effectiveRedirectUri =
    redirectUri ?? `${window.location.origin}${window.location.pathname}`;

  return (
    <div className={styles.demoWrapper} style={{ height }}>
      {/* @ts-expect-error fhir4ds-demo is a custom element defined in fhir4ds-demo.d.ts */}
      <fhir4ds-demo
        scenario={scenario}
        height={height}
        redirect-uri={effectiveRedirectUri}
        style={{ display: "block", width: "100%", height: "100%" }}
      />
    </div>
  );
}

export default function WasmDemoWC({
  scenario = "workbench",
  height = "80vh",
  lazyLaunch = false,
  title,
  description,
  redirectUri,
}: WasmDemoWCProps): ReactNode {
  const { siteConfig } = useDocusaurusContext();
  const baseUrl = siteConfig.baseUrl.replace(/\/$/, "");
  const scriptSrc = `${baseUrl}/wasm-app/fhir4ds-demo.js`;

  // Detect OAuth callback params in URL (?code= + ?state=)
  const hasOAuthParams =
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).has("code") &&
    new URLSearchParams(window.location.search).has("state");

  // Popup context: window.opener set → the WC IIFE handles token exchange
  const isPopupOAuthCallback =
    hasOAuthParams &&
    typeof window !== "undefined" &&
    window.opener !== null;

  // Skip lazyLaunch if there are OAuth params (popup OR direct-nav fallback)
  // so the WC renders immediately and SMARTLaunch can process the callback.
  const [launched, setLaunched] = useState(!lazyLaunch || hasOAuthParams);
  const launch = useCallback(() => setLaunched(true), []);

  // Popup callback: just inject the script so the IIFE handles token exchange,
  // then closes the popup. No UI needed.
  if (isPopupOAuthCallback) {
    return (
      <BrowserOnly fallback={<div />}>
        {() => {
          injectWcScript(scriptSrc);
          return <div style={{ display: "none" }} />;
        }}
      </BrowserOnly>
    );
  }

  return (
    <BrowserOnly
      fallback={
        <div style={{ height, background: "#0f172a", borderRadius: 8 }} />
      }
    >
      {() => {
        if (!launched) {
          return (
            <LaunchCard
              scenario={scenario}
              title={title}
              description={description}
              onLaunch={launch}
            />
          );
        }
        return (
          <WcEmbed
            scenario={scenario}
            height={height}
            scriptSrc={scriptSrc}
            redirectUri={redirectUri}
          />
        );
      }}
    </BrowserOnly>
  );
}
