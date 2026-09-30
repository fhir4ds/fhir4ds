/**
 * CleanroomWC — Docusaurus wrapper for the <cql-cleanroom> Web Component.
 *
 * Handles:
 *   - SSR: BrowserOnly guard (Docusaurus pre-renders; the WC requires browser APIs)
 *   - Script deduplication: cql-cleanroom.js is only injected once per page
 *
 * Usage in .mdx:
 *   import CleanroomWC from '@site/src/components/CleanroomWC';
 *   <CleanroomWC />
 *   <CleanroomWC height="90vh" popout />
 */

import { useState } from "react";
import BrowserOnly from "@docusaurus/BrowserOnly";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import PopoutPill from "./PopoutPill";
import styles from "./WasmDemo.module.css";

const SCRIPT_ID = "cql-cleanroom-wc-bundle";

function injectWcScript(scriptSrc: string): void {
  if (document.getElementById(SCRIPT_ID)) return;
  const script = document.createElement("script");
  script.id = SCRIPT_ID;
  script.type = "module";
  script.src = scriptSrc;
  document.head.appendChild(script);
}

/** Click-to-launch splash (same card style as the other examples). */
function LaunchCard({ onLaunch }: { onLaunch: () => void }) {
  return (
    <div className={styles.launcher}>
      <div className={styles.launcherContent}>
        <div className={styles.launcherIcon}>🧪</div>
        <h3 className={styles.launcherTitle}>CQL Cleanroom</h3>
        <p className={styles.launcherDesc}>
          A fully browser-native CQL workbench — author, validate, evaluate,
          test, and diff clinical quality logic. Boots with the CMS69 featured
          example (62 patients, 22 ValueSets) already loaded.
        </p>
        <div className={styles.launcherBadges}>
          <span className={styles.badge}>🔒 Zero server</span>
          <span className={styles.badge}>🌐 WebAssembly</span>
          <span className={styles.badge}>📊 Full audit evidence</span>
          <span className={styles.badge}>⚡ C++ extensions</span>
        </div>
        <button className={styles.launchBtn} onClick={onLaunch}>
          Launch Demo
        </button>
        <p className={styles.launcherNote}>
          Requires Chrome, Firefox, or Edge. First boot downloads ~50 MB
          (Pyodide wheel + DuckDB-WASM) and takes 40–60 seconds; warm boots
          are cached.
        </p>
      </div>
    </div>
  );
}

interface CleanroomWCProps {
  /** CSS height. Default: '85vh' */
  height?: string;
  /** Show a "Launch Demo" splash card before loading the heavy bundle. */
  lazyLaunch?: boolean;
  /** Show an "Open in new window ↗" pill above the workbench that opens the
   *  standalone app (the cleanroom's static build is a full page on its own). */
  popout?: boolean;
}

function CleanroomComponent({
  height = "85vh",
  lazyLaunch = false,
  popout = false,
}: CleanroomWCProps) {
  const {
    siteConfig: { baseUrl },
  } = useDocusaurusContext();
  const [launched, setLaunched] = useState(!lazyLaunch);

  if (!launched) {
    return <LaunchCard onLaunch={() => setLaunched(true)} />;
  }

  injectWcScript(`${baseUrl}cql-cleanroom/cql-cleanroom.js`);

  return (
    <>
      {popout && <PopoutPill url={`${baseUrl}cql-cleanroom/?example=cms69`} />}
      <div className={styles.demoWrapper} style={{ height }}>
        {/* @ts-expect-error cql-cleanroom is a custom element defined by the cleanroom bundle */}
        <cql-cleanroom height={height} default-example="cms69" style={{ display: "block", width: "100%", height: "100%" }} />
      </div>
    </>
  );
}

export default function CleanroomWC(props: CleanroomWCProps) {
  return <BrowserOnly>{() => <CleanroomComponent {...props} />}</BrowserOnly>;
}
