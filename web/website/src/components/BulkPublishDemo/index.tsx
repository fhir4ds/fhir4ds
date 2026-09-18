import "./styles.css";
import useBaseUrl from "@docusaurus/useBaseUrl";
import { BulkPublishDemoProvider, useDemoState } from "./provider";
import { MermaidDiagram } from "./components/MermaidDiagram";
import { ConnectSection } from "./components/sections/ConnectSection";
import { RawDataSection } from "./components/sections/RawDataSection";
import { TranslationSection } from "./components/sections/TranslationSection";
import { QuerySection } from "./components/sections/QuerySection";
import { ProductionSection } from "./components/sections/ProductionSection";

// The default export is the Provider. It sets up all shared state (DuckDB,
// Pyodide, ingest, materialization) and exposes it via Context so the
// per-section widgets rendered between markdown H2s in the MDX can consume
// it. The Provider renders no DOM of its own — it just wraps children.
export default BulkPublishDemoProvider;

export { BulkPublishDemoProvider, useDemoState };

// Each "Block" component renders ONLY the interactive widget for its section.
// Section titles, narrative prose, and the eyebrow (§N / label) all live in
// the MDX as plain markdown — this lets Docusaurus build the right-side ToC
// from the markdown H2s and lets the narrative flow naturally as paragraph
// text instead of being trapped inside a padded Section container.

export function IntroDiagram() {
  // Three-step overview of the demo flow: Publish → Consume → Book. Each
  // step is a single node with a one-sentence description; no substeps or
  // bullets. Kept as a component because mermaid source is awkward to
  // inline in MDX.
  return (
    <div className="bulk-publish-demo-app">
      <MermaidDiagram
        chart={`flowchart LR
          P["① Publish — providers expose NDJSON via $bulk-publish"]
          C["② Consume — FHIR4DS-WASM ingests and DuckDB-WASM queries client-side"]
          B["③ Book — booking-deep-link sends the patient back to the EHR"]

          P --> C --> B

          style P fill:#131c30,stroke:#38bdf8,color:#e6ecf5
          style C fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style B fill:#131c30,stroke:#fbbf24,color:#e6ecf5
        `}
      />
    </div>
  );
}

export function ConnectBlock() {
  const s = useDemoState();
  return (
    <div className="bulk-publish-demo-app">
      <ConnectSection
        publisherUrl={s.publisherUrl}
        onPublisherUrl={s.setPublisherUrl}
        onConnect={s.doConnect}
        onDisconnect={s.disconnect}
        connections={s.connections}
        ingest={s.ingest}
        ingestLog={s.ingestLog}
        connecting={s.connecting}
        connected={!!s.ingest}
        error={s.error}
        lookupZip={s.lookupZip}
        lookupCityState={s.lookupCityState}
        reverseGeocode={s.reverseGeocode}
        onRegenerateNearLocation={s.regenerateNearLocation}
        regenerating={s.regenerating}
      />
    </div>
  );
}

export function ExploreBlock() {
  const s = useDemoState();
  return (
    <div className="bulk-publish-demo-app">
      <RawDataSection ready={!!s.ingest} executeQuery={s.executeQuery} providerRefresh={s.ingest?.totalTimeMs ?? 0} />
    </div>
  );
}

export function ResourceDiagram() {
  // Slot at the top; Schedule + EHR booking at the next level; the
  // practitioner-related resources Schedule points at on the third level.
  // Arrows follow reference direction (who points at whom).
  return (
    <div className="bulk-publish-demo-app">
      <MermaidDiagram
        chart={`flowchart TD
          Slot["Slot<br/><small>appointment window</small>"]
          Sched["Schedule<br/><small>service at a location</small>"]
          Book["EHR booking<br/><small>via deep link</small>"]
          Role["PractitionerRole<br/><small>links provider + location</small>"]
          Prac["Practitioner<br/><small>the provider</small>"]
          HCS["HealthcareService<br/><small>service line</small>"]
          Loc["Location<br/><small>physical site</small>"]

          Slot -->|"Slot.schedule"| Sched
          Slot -.->|"Slot.booking-deep-link"| Book
          Sched -->|"Schedule.actor"| Role
          Sched -->|"Schedule.actor"| Prac
          Sched -->|"Schedule.actor"| HCS
          Sched -->|"Schedule.actor"| Loc

          style Slot fill:#131c30,stroke:#38bdf8,color:#e6ecf5
          style Sched fill:#131c30,stroke:#38bdf8,color:#e6ecf5
          style Book fill:#131c30,stroke:#fbbf24,color:#e6ecf5
          style Role fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style Prac fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style HCS fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style Loc fill:#1c2741,stroke:#5fed83,color:#e6ecf5
        `}
      />
    </div>
  );
}

export function TranslateBlock() {
  const s = useDemoState();
  return (
    <div className="bulk-publish-demo-app">
      <TranslationSection
        generatedSql={s.generatedSql}
        materialized={s.materialized}
        executeQuery={s.executeQuery}
        translateMs={s.translateMs}
      />
    </div>
  );
}

export function QueryBlock() {
  const s = useDemoState();
  return (
    <div className="bulk-publish-demo-app">
      <QuerySection
        materialized={s.materialized}
        executeQuery={s.executeQuery}
        lookupZip={s.lookupZip}
        lookupCityState={s.lookupCityState}
        reverseGeocode={s.reverseGeocode}
        onRegenerateNearLocation={
          s.isSynthetic ? s.regenerateNearLocation : undefined
        }
        regenerating={s.regenerating}
        defaults={s.defaults}
      />
    </div>
  );
}

/** localStorage hand-off from the demo to the pop-out patient app: the
 *  popup window can't share React state, so the button writes the live
 *  connection list right before opening it. Search defaults are derived
 *  from the data on both sides, so only the endpoints need handing off. */
const PATIENT_APP_SEED_KEY = "fhir4ds.patient-app.seed";
const PATIENT_APP_SEED_TTL_MS = 10 * 60 * 1000;

export function readPatientAppSeed(): { urls: string[] } | null {
  try {
    const raw = localStorage.getItem(PATIENT_APP_SEED_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (Date.now() - parsed.ts > PATIENT_APP_SEED_TTL_MS) return null;
    if (!Array.isArray(parsed.urls) || parsed.urls.length === 0) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function ProductionBlock() {
  const s = useDemoState();
  const patientAppUrl = useBaseUrl("patient-app");

  function openPatientApp() {
    try {
      localStorage.setItem(
        PATIENT_APP_SEED_KEY,
        JSON.stringify({ ts: Date.now(), urls: s.connections.map((c) => c.url) }),
      );
    } catch {
      // Private mode / storage disabled — the popup falls back to default.
    }
    window.open(patientAppUrl, "_blank");
  }

  return (
    <div className="bulk-publish-demo-app">
      <div className="production-popout">
        <button className="production-popout__btn" onClick={openPatientApp}>
          Open patient app ↗
        </button>
      </div>
      <ProductionSection
        materialized={s.materialized}
        executeQuery={s.executeQuery}
        lookupZip={s.lookupZip}
        lookupCityState={s.lookupCityState}
        reverseGeocode={s.reverseGeocode}
        defaults={s.defaults}
      />
    </div>
  );
}
