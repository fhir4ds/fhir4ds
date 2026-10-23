/**
 * ViewingRoomWC — Docusaurus wrapper for the <sqlonfhir-viewing-room> Web
 * Component. Follows the CleanroomWC/CqlClinicWC pattern:
 *   - SSR: BrowserOnly guard (the WC requires browser APIs)
 *   - Script deduplication: the bundle is injected once per page
 *   - lazyLaunch splash (click-to-launch keeps the heavy bundle off the
 *     initial page load, matching the cleanroom convention)
 *   - popout pill to the standalone app
 */

import { useState } from "react";
import BrowserOnly from "@docusaurus/BrowserOnly";
import useDocusaurusContext from "@docusaurus/useDocusaurusContext";
import PopoutPill from "./PopoutPill";
import styles from "./WasmDemo.module.css";

const SCRIPT_ID = "viewing-room-wc-bundle";

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
        <div className={styles.launcherIcon}>🩻</div>
        <h3 className={styles.launcherTitle}>SQL-on-FHIR Viewing Room</h3>
        <p className={styles.launcherDesc}>
          A ViewDefinition playground — load FHIR resources, author or edit a
          ViewDefinition, and watch the flattened SQL view update live as you
          type. Boots with the sql-on-fhir.org reference patient set already
          loaded.
        </p>
        <div className={styles.launcherBadges}>
          <span className={styles.badge}>🔒 Zero server</span>
          <span className={styles.badge}>🌐 WebAssembly</span>
          <span className={styles.badge}>⚡ Auto-recalc</span>
          <span className={styles.badge}>🔎 Exact-SQL view</span>
        </div>
        <button className={styles.launchBtn} onClick={onLaunch}>
          Launch Demo
        </button>
        <p className={styles.launcherNote}>
          Requires Chrome, Firefox, or Edge. First boot downloads ~30 MB
          (Pyodide wheel + DuckDB-WASM) and takes 30–60 seconds; warm boots
          are cached.
        </p>
      </div>
    </div>
  );
}

interface ViewingRoomWCProps {
  /** CSS height. Default: '85vh' */
  height?: string;
  /** Show a "Launch Demo" splash card before loading the heavy bundle. */
  lazyLaunch?: boolean;
  /** Show an "Open in new window ↗" pill above the app that opens the
   *  standalone build. */
  popout?: boolean;
}

function ViewingRoomComponent({
  height = "85vh",
  lazyLaunch = false,
  popout = false,
}: ViewingRoomWCProps) {
  const {
    siteConfig: { baseUrl },
  } = useDocusaurusContext();
  const [launched, setLaunched] = useState(!lazyLaunch);

  if (!launched) {
    return <LaunchCard onLaunch={() => setLaunched(true)} />;
  }

  injectWcScript(`${baseUrl}viewing-room-app/sqlonfhir-viewing-room.js`);

  return (
    <>
      {popout && <PopoutPill url={`${baseUrl}viewing-room-app/`} />}
      <div className={styles.demoWrapper} style={{ height }}>
        {/* @ts-expect-error sqlonfhir-viewing-room is a custom element defined by the viewing-room bundle */}
        <sqlonfhir-viewing-room height={height} style={{ display: "block", width: "100%", height: "100%" }} />
      </div>
    </>
  );
}

export default function ViewingRoomWC(props: ViewingRoomWCProps) {
  return <BrowserOnly>{() => <ViewingRoomComponent {...props} />}</BrowserOnly>;
}
