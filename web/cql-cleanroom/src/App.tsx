import { useEffect, useRef, useState } from "react";
import {
  BootOverlay,
  VersionBadge,
  useBootProgress,
  workerRequest,
} from "./components/BootOverlay";
import { EditorPane } from "./components/EditorPane";
import {
  buildShareUrl,
  decodeShareFragment,
  type SharePayload,
} from "./lib/share";
import { ResultsPane } from "./components/ResultsPane";
import { TestsPane } from "./components/TestsPane";
import { DatasetPane } from "./components/DatasetPane";
import { ResourceBuilderPane } from "./components/ResourceBuilderPane";
import { EvidencePane } from "./components/EvidencePane";
import { FhirpathPane } from "./components/FhirpathPane";
import { AstPane } from "./components/AstPane";
import { GraphPane } from "./components/GraphPane";
import type { DatasetSpec, LibraryText } from "./lib/protocol";
import {
  clearWorkspace,
  exportWorkspaceZip,
  importWorkspaceZip,
  loadWorkspace,
  saveWorkspace,
  type WorkspaceLibrary,
} from "./state/workspace";

// e2e bridge: the app's singleton worker, request/response correlated by id
declare global {
  interface Window {
    __cleanroom?: (msg: Record<string, unknown>) => Promise<any>;
  }
}
(window as any).__cleanroom = workerRequest;

const DEFAULT_CQL = `library CleanroomDemo version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers

define "Initial Population":
  exists([Patient] P where P.gender = 'female')

define "Has Name":
  exists([Patient] P where P.name.first().given.first() is not null)
`;

const OUTPUT_COLUMNS: Record<string, string> = {
  IPP: "Initial Population",
  NAME: "Has Name",
};

export default function App() {
  const boot = useBootProgress();
  const [libraries, setLibraries] = useState<WorkspaceLibrary[]>([
    { name: "CleanroomDemo", text: DEFAULT_CQL },
  ]);
  const [activeTab, setActiveTab] = useState(0);
  const [dataset, setDataset] = useState<DatasetSpec | null>(null);
  // C3-U3: builder prefill for dataset-row editing (nonce re-triggers).
  const [builderPrefill, setBuilderPrefill] = useState<{
    resource: Record<string, unknown>;
    nonce: number;
  } | null>(null);
  const [restored, setRestored] = useState(false);
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Restore workspace on first mount; autosave (debounced) on changes.
  // A share fragment (#s=...) takes precedence over IndexedDB state.
  useEffect(() => {
    const shared = decodeShareFragment(location.hash);
    if (shared) {
      setLibraries(
        shared.libraries.map((l) => ({ name: l.name, text: l.text })),
      );
      setActiveTab(Math.min(shared.activeIndex ?? 0, shared.libraries.length - 1));
      setRestored(true);
      return;
    }
    loadWorkspace()
      .then((ws) => {
        if (ws?.libraries?.length) {
          setLibraries(ws.libraries);
          setActiveTab(0);
          if (ws.dataset) {
            setDataset({
              resources: ws.dataset.resources as Record<string, unknown>[],
            });
          }
        }
      })
      .catch(() => undefined)
      .finally(() => setRestored(true));
  }, []);

  useEffect(() => {
    if (!restored) return;
    const t = setTimeout(() => {
      saveWorkspace({
        libraries,
        dataset: dataset?.resources?.length
          ? { resources: dataset.resources as unknown[] }
          : null,
        cases: null,
        prefs: {},
      }).catch(() => undefined);
    }, 800);
    return () => clearTimeout(t);
  }, [libraries, dataset, restored]);

  const active = libraries[activeTab] ?? libraries[0];
  const main: LibraryText = { name: active.name, text: active.text };

  const updateActiveText = (text: string) => {
    setLibraries((libs) =>
      libs.map((l, i) => (i === activeTab ? { ...l, text } : l)),
    );
  };

  const addTab = () => {
    const name = `Library${libraries.length + 1}`;
    const text = `library ${name} version '1.0.0'\nusing FHIR version '4.0.1'\n`;
    setLibraries((libs) => [...libs, { name, text }]);
    setActiveTab(libraries.length);
  };

  const closeTab = (i: number) => {
    if (libraries.length === 1) return;
    setLibraries((libs) => libs.filter((_, idx) => idx !== i));
    setActiveTab((t) => (i < t ? t - 1 : Math.min(t, libraries.length - 2)));
  };


  const shareLink = () => {
    const payload: SharePayload = {
      format: "cql-cleanroom-share",
      version: 1,
      libraries: libraries.map((l) => ({ name: l.name, text: l.text })),
      activeIndex: activeTab,
      outputColumns: OUTPUT_COLUMNS,
      parameters: null,
      cases: null,
    };
    try {
      const url = buildShareUrl(payload);
      location.hash = url.slice(url.indexOf("#"));
      void navigator.clipboard?.writeText(url).catch(() => undefined);
    } catch (e) {
      // REV-C2-002: surface encode failures (e.g. >100KB) via statusNote.
      setStatusNote(
        `share link failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
  };

  const exportZip = () => {
    const bytes = exportWorkspaceZip({
      libraries,
      dataset: dataset?.resources?.length
        ? { resources: dataset.resources as unknown[] }
        : null,
      cases: null,
      prefs: {},
    });
    const blob = new Blob([bytes as unknown as BlobPart], {
      type: "application/zip",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "cql-cleanroom-workspace.zip";
    a.click();
    URL.revokeObjectURL(url);
  };

  const importZip = async (file: File) => {
    try {
      const state = importWorkspaceZip(new Uint8Array(await file.arrayBuffer()));
      if (state.libraries.length) {
        setLibraries(state.libraries);
        setActiveTab(0);
      }
      if (state.dataset) {
        setDataset({
          resources: state.dataset.resources as Record<string, unknown>[],
        });
      }
    } catch (e) {
      console.error("workspace import failed", e);
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>CQL Cleanroom</h1>
        <VersionBadge
          wheelVersion={boot.phase === "ready" ? boot.wheelVersion : null}
        />
        {statusNote && (
          <span
            className="status-note"
            data-testid="status-note"
            ref={(el) => {
              if (el) {
                setTimeout(() => setStatusNote(null), 6000);
              }
            }}
          >
            {statusNote}
          </span>
        )}
        <div className="workspace-actions" data-testid="workspace-actions">
          <button data-testid="share-btn" onClick={shareLink}>
            Share
          </button>
          <button data-testid="workspace-export" onClick={exportZip}>
            Export zip
          </button>
          <button
            data-testid="workspace-import"
            onClick={() => fileRef.current?.click()}
          >
            Import zip
          </button>
          <button
            data-testid="workspace-reset"
            onClick={() => {
              clearWorkspace().catch(() => undefined);
              setLibraries([{ name: "CleanroomDemo", text: DEFAULT_CQL }]);
              setActiveTab(0);
              setDataset(null);
            }}
          >
            Reset
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".zip"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importZip(f);
              e.target.value = "";
            }}
          />
        </div>
      </header>
      <main className="app-main" data-testid="app-main">
        <div className="pane-col editor-col">
          <div className="tab-strip" data-testid="library-tabs">
            {libraries.map((lib, i) => (
              <span
                key={lib.name + i}
                className={`tab ${i === activeTab ? "active" : ""}`}
                data-testid={`library-tab-${i}`}
              >
                <button onClick={() => setActiveTab(i)}>{lib.name}</button>
                {libraries.length > 1 && (
                  <button
                    className="tab-close"
                    data-testid={`library-tab-${i}-close`}
                    onClick={() => closeTab(i)}
                    aria-label={`close ${lib.name}`}
                  >
                    ×
                  </button>
                )}
              </span>
            ))}
            <button
              className="tab-add"
              data-testid="library-tab-add"
              onClick={addTab}
            >
              +
            </button>
          </div>
          <EditorPane text={active.text} onTextChange={updateActiveText} />
        </div>
        <div className="pane-col run-col">
          <ResultsPane
            libraries={[main]}
            main={main}
            dataset={dataset}
            outputColumns={OUTPUT_COLUMNS}
          />
          <TestsPane
            libraries={[main]}
            main={main}
            dataset={dataset}
            outputColumns={OUTPUT_COLUMNS}
          />
        </div>
        <div className="pane-col side-col">
          <DatasetPane
            dataset={dataset}
            onDatasetChange={setDataset}
            onEditResource={(index) => {
              const r = dataset?.resources?.[index];
              if (r && typeof r === "object") {
                setBuilderPrefill((prev) => ({
                  resource: r as Record<string, unknown>,
                  nonce: (prev?.nonce ?? 0) + 1,
                }));
              }
            }}
          />
          <ResourceBuilderPane
            onAddResource={(resource) => {
              const resources = [...(dataset?.resources ?? []), resource];
              setDataset(dataset ? { ...dataset, resources } : { resources });
              setBuilderPrefill(null);
            }}
            prefill={builderPrefill}
          />
          <EvidencePane
            libraries={[main]}
            main={main}
            dataset={
              dataset?.resources?.length
                ? { resources: dataset.resources as unknown[] }
                : null
            }
            outputColumns={OUTPUT_COLUMNS}
          />
          <FhirpathPane />
          <AstPane cqlText={active?.text ?? ""} />
          <GraphPane onApplyCql={(cql) => updateActiveText(cql)} />
        </div>
      </main>
      <BootOverlay state={boot} />
    </div>
  );
}
