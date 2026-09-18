import Head from "@docusaurus/Head";
import BrowserOnly from "@docusaurus/BrowserOnly";
import { useState, type ReactElement } from "react";
import {
  BulkPublishDemoProvider,
  readPatientAppSeed,
  useDemoState,
} from "@site/src/components/BulkPublishDemo";
import { ProductionSection } from "@site/src/components/BulkPublishDemo/components/sections/ProductionSection";

/**
 * Chrome-less standalone rendering of the §5 production widget: the
 * patient-facing scheduling app with none of the docs site around it. The
 * provider auto-connects to the default publisher on mount, so this window
 * boots, ingests, materializes, and searches on its own.
 *
 * Opened from the bulk-publish example's "Open patient app ↗" button.
 */
function PatientApp() {
  const s = useDemoState();

  const status = !s.duckdbReady
    ? "Starting the in-browser search engine…"
    : !s.ingest
      ? "Downloading published schedules…"
      : !s.materialized
        ? "Preparing appointment search…"
        : null;

  return (
    <div className="bulk-publish-demo-app patient-app">
      <Head>
        <title>Find care — patient app · FHIR4DS</title>
        <meta name="description" content="Search published FHIR scheduling data — entirely in your browser." />
      </Head>

      <header className="patient-app__header">
        <span className="patient-app__brand">Find care</span>
        <span className="patient-app__tag">FHIR4DS · queries run 100% in your browser</span>
      </header>

      <main className="patient-app__main">
        {s.error && (
          <div className="patient-app__error">
            <div className="widget__error">{s.error}</div>
            <button className="patient-app__retry" onClick={() => s.doConnect()}>
              Retry
            </button>
          </div>
        )}

        {status && !s.error && (
          <div className="patient-app__loading">
            <span className="patient-app__spinner" />
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
      </main>
    </div>
  );
}

export default function PatientAppPage(): ReactElement {
  return (
    <BrowserOnly fallback={<div className="patient-app patient-app--boot" />}>
      {() => <PatientAppWindow />}
    </BrowserOnly>
  );
}

function PatientAppWindow() {
  // One-shot read at mount: if the demo page just popped this window open,
  // inherit its live connections. Search defaults derive from the data.
  const [seed] = useState(() => readPatientAppSeed());
  return (
    <BulkPublishDemoProvider seedConnections={seed?.urls}>
      <PatientApp />
    </BulkPublishDemoProvider>
  );
}
