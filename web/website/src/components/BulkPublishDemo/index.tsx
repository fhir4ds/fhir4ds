import "./styles.css";
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
        onPresetDefaults={s.setPresetDefaults}
        onConnect={s.doConnect}
        ingest={s.ingest}
        ingestLog={s.ingestLog}
        connecting={s.connecting}
        connected={!!s.ingest}
        error={null}
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
      <RawDataSection ready={!!s.ingest} executeQuery={s.executeQuery} />
    </div>
  );
}

export function ResourceDiagram() {
  // The Slot → Schedule → PractitionerRole → Practitioner/Location diagram.
  // Kept as a component because mermaid source is awkward to inline in MDX.
  return (
    <div className="bulk-publish-demo-app">
      <MermaidDiagram
        chart={`flowchart TD
          Slot["Slot<br/><small>appointment window</small>"]
          Sched["Schedule<br/><small>service at a location</small>"]
          Role["PractitionerRole<br/><small>links provider + location</small>"]
          Prac["Practitioner<br/><small>the provider</small>"]
          Loc["Location<br/><small>physical site</small>"]
          HCS["HealthcareService<br/><small>service line</small>"]
          Book["→ EHR booking<br/><small>via deep link</small>"]

          Slot -->|"Slot.schedule"| Sched
          Sched -->|"Schedule.actor"| Role
          Role -->|"PractitionerRole.practitioner"| Prac
          Role -->|"PractitionerRole.location"| Loc
          Role -.->|"PractitionerRole.healthcareService"| HCS
          Slot -.->|"Slot.booking-deep-link"| Book

          style Slot fill:#131c30,stroke:#38bdf8,color:#e6ecf5
          style Sched fill:#131c30,stroke:#38bdf8,color:#e6ecf5
          style Role fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style Prac fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style Loc fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style HCS fill:#1c2741,stroke:#5fed83,color:#e6ecf5
          style Book fill:#131c30,stroke:#fbbf24,color:#e6ecf5
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
        defaults={s.presetDefaults}
      />
    </div>
  );
}

export function ProductionBlock() {
  const s = useDemoState();
  return (
    <div className="bulk-publish-demo-app">
      <ProductionSection
        materialized={s.materialized}
        executeQuery={s.executeQuery}
        lookupZip={s.lookupZip}
        lookupCityState={s.lookupCityState}
        reverseGeocode={s.reverseGeocode}
        defaults={s.presetDefaults}
      />
    </div>
  );
}
