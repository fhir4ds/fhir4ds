import BrowserOnly from "@docusaurus/BrowserOnly";
import { useState, type ReactElement } from "react";
import DemoAppWindow from "@site/src/components/DemoAppWindow";
import windowStyles from "@site/src/components/DemoAppWindow.module.css";
import {
  BulkPublishDemoProvider,
  readSchedulingAppSeed,
  useDemoState,
} from "@site/src/components/BulkPublishDemo";
import { ProductionSection } from "@site/src/components/BulkPublishDemo/components/sections/ProductionSection";

/**
 * Chrome-less standalone rendering of the §5 production widget: the
 * scheduling demo app with none of the docs site around it. The provider
 * auto-connects on mount — inheriting the demo page's live connections
 * when opened via "Open in new window ↗" — then ingests, materializes,
 * and searches on its own.
 */
function SchedulingApp() {
  const s = useDemoState();

  const status = !s.duckdbReady
    ? "Starting the in-browser search engine…"
    : !s.ingest
      ? "Downloading published schedules…"
      : !s.materialized
        ? "Preparing appointment search…"
        : null;

  return (
    <DemoAppWindow
      title="Find Care"
      documentTitle="Find Care · FHIR4DS scheduling demo"
    >
      <div className={`bulk-publish-demo-app ${windowStyles.fill}`}>
        {s.error && (
          <div className={windowStyles.error}>
            <div className={windowStyles.widgetError}>{s.error}</div>
            <button className={windowStyles.retry} onClick={() => s.doConnect()}>
              Retry
            </button>
          </div>
        )}

        {status && !s.error && (
          <div className={windowStyles.loading}>
            <span className={windowStyles.spinner} />
            <div>
              <strong>Finding available appointments…</strong>
              <p>{status}</p>
            </div>
          </div>
        )}

        {!status && (
          <ProductionSection
            materialized={s.materialized}
            executeQuery={s.executeQuery}
            lookupZip={s.lookupZip}
            lookupCityState={s.lookupCityState}
            reverseGeocode={s.reverseGeocode}
            defaults={s.defaults}
          />
        )}
      </div>
    </DemoAppWindow>
  );
}

export default function SchedulingAppPage(): ReactElement {
  return (
    <BrowserOnly fallback={<div className={windowStyles.boot} />}>
      {() => (
        <SchedulingAppWindow />
      )}
    </BrowserOnly>
  );
}

function SchedulingAppWindow() {
  // One-shot read at mount: if the demo page just popped this window open,
  // inherit its live connections. Search defaults derive from the data.
  const [seed] = useState(() => readSchedulingAppSeed());
  return (
    <BulkPublishDemoProvider seedConnections={seed?.urls}>
      <SchedulingApp />
    </BulkPublishDemoProvider>
  );
}
