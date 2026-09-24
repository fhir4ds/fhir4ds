import { useEffect, useMemo, useRef, useState } from "react";
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
import { MeasurePane } from "./components/MeasurePane";
import { ViewPane } from "./components/ViewPane";
import { DatasetPane } from "./components/DatasetPane";
import { ResourceBuilderPane } from "./components/ResourceBuilderPane";
import {
  exportBundle,
  importBundle,
  mergeDatasets,
} from "./lib/bundleIo";
import { EvidencePane } from "./components/EvidencePane";
import { FhirpathPane } from "./components/FhirpathPane";
import type { RunEntry } from "./state/workspace";
import { RUN_HISTORY_CAP } from "./state/workspace";
import {
  appendRun,
  artifactFromRows,
  datasetHash as computeDatasetHash,
  defaultRunName,
  libraryHash as computeLibraryHash,
  newRunId,
} from "./lib/runHistory";
import type { ResultsTab } from "./components/ResultsPane";
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

/**
 * INV-3: population-role semantics resolve from the Measure resource
 * ONLY. The hardcoded OUTPUT_COLUMNS alias map is DELETED; the alias
 * map feeding translate/evaluate is derived from the measure via
 * output_columns_from_measure (column = population_code with the DQM
 * underscore convention).
 */
const DEFAULT_MEASURE: Record<string, unknown> = {
  resourceType: "Measure",
  name: "CleanroomMeasure",
  status: "draft",
  group: [
    {
      id: "group-1",
      extension: [
        {
          url: "http://hl7.org/fhir/us/cqf-measures/StructureDefinition/cqfm-populationBasis",
          valueCode: "boolean",
        },
      ],
      population: [
        {
          code: {
            coding: [
              {
                system: "http://terminology.hl7.org/CodeSystem/measure-population",
                code: "initial-population",
              },
            ],
          },
          criteria: {
            language: "text/cql-identifier",
            expression: "Initial Population",
          },
        },
        {
          code: {
            coding: [
              {
                system: "http://terminology.hl7.org/CodeSystem/measure-population",
                code: "numerator",
              },
            ],
          },
          criteria: {
            language: "text/cql-identifier",
            expression: "Has Name",
          },
        },
      ],
    },
  ],
};

function outputColumnsFromMeasure(
  measure: Record<string, unknown> | null,
): Record<string, string> | null {
  if (!measure) return null;
  const groups = (measure.group as Array<Record<string, unknown>>) ?? [];
  const out: Record<string, string> = {};
  for (const g of groups) {
    for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
      const coding =
        (
          (pop.code as Record<string, unknown>)?.coding as
            Array<Record<string, unknown>>
        )?.[0] ?? {};
      const criteria = pop.criteria as Record<string, unknown> | undefined;
      const code = coding.code;
      const define = criteria?.expression;
      if (typeof code === "string" && typeof define === "string" && code && define) {
        out[code.replace(/-/g, "_")] = define;
      }
    }
  }
  return Object.keys(out).length ? out : null;
}

function populationCodesFromMeasure(
  measure: Record<string, unknown> | null,
): string[] {
  // Authority form: hyphenated FHIR measure-population codes
  // (initial-population). Consumers snake_case for column keys.
  if (!measure) return [];
  const groups = (measure.group as Array<Record<string, unknown>>) ?? [];
  const out: string[] = [];
  for (const g of groups) {
    for (const pop of (g.population as Array<Record<string, unknown>>) ?? []) {
      const coding =
        (
          (pop.code as Record<string, unknown>)?.coding as
            Array<Record<string, unknown>>
        )?.[0] ?? {};
      if (typeof coding.code === "string" && coding.code) {
        out.push(coding.code);
      }
    }
  }
  return out;
}

export default function App() {
  const boot = useBootProgress();
  const [libraries, setLibraries] = useState<WorkspaceLibrary[]>([
    { name: "CleanroomDemo", text: DEFAULT_CQL },
  ]);
  const [activeTab, setActiveTab] = useState(0);
  const [dataset, setDataset] = useState<DatasetSpec | null>(null);
  // Measure resource: population-mapping authority (INV-3). NULL when
  // the workspace has none — evaluation falls back to raw define names.
  const [measure, setMeasure] = useState<Record<string, unknown> | null>(
    DEFAULT_MEASURE,
  );
  const [expectedValues, setExpectedValues] = useState<{
    [pid: string]: { [code: string]: boolean };
  } | null>(null);
  // MeasureReports from the last evaluation (View drawer default source).
  const [lastReports, setLastReports] = useState<
    Array<Record<string, unknown>> | null
  >(null);
  // Editor-column visual-editor drawer (default collapsed).
  const [graphOpen, setGraphOpen] = useState(false);
  // Editor-column FHIRPath scratchpad drawer (default collapsed).
  const [fhirpathOpen, setFhirpathOpen] = useState(false);
  // WORKBENCH_REORG §3.1/§3.3 — Results tab pref + local run history.
  const [resultsTab, setResultsTab] = useState<ResultsTab>("cql");
  const [runHistory, setRunHistory] = useState<RunEntry[]>([]);
  // Flatten SQL of the last View run (Show-SQL context for the View tab).
  const [viewSql, setViewSql] = useState<string | null>(null);
  // Row-shaped memberships + hashes of the LATEST evaluation (compare
  // target + drift reference). Cleared when inputs change.
  const [currentRun, setCurrentRun] = useState<{
    artifact: RunEntry["artifact"];
    libraryHash: string;
    datasetHash: string;
  } | null>(null);
  // §3.5 View drawer config — persisted in workspace (schemaVersion 2).
  const [viewConfig, setViewConfig] = useState<{
    overrides: Record<string, { name?: string; path?: string }>;
  } | null>(null);
  // C3-U3: builder prefill for dataset-row editing (nonce re-triggers).
  const [builderPrefill, setBuilderPrefill] = useState<{
    resource: Record<string, unknown>;
    nonce: number;
  } | null>(null);
  // §3.2: per-patient `+` context — subject-class pickers default to
  // Patient/<id> (builder v2 consumes; v1 ignores gracefully).
  const [builderContext, setBuilderContext] = useState<{
    patientId: string;
    nonce: number;
  } | null>(null);
  const [restored, setRestored] = useState(false);
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  // Derived from the Measure — the ONLY alias/order source (INV-3).
  const outputColumns = useMemo(
    () => outputColumnsFromMeasure(measure),
    [measure],
  );
  const populationCodes = useMemo(
    () => populationCodesFromMeasure(measure),
    [measure],
  );

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
        if (ws?.measure) {
          setMeasure(ws.measure);
        }
        if (ws?.viewConfig) {
          setViewConfig(ws.viewConfig);
        }
        if (ws && Array.isArray(ws.runHistory)) {
          setRunHistory(ws.runHistory);
        }
        if (
          ws &&
          (ws.activeTabPref === "cql" ||
            ws.activeTabPref === "measure" ||
            ws.activeTabPref === "view")
        ) {
          setResultsTab(ws.activeTabPref);
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
        cases: expectedValues
          ? (Object.entries(expectedValues).flatMap(([pid, codes]) =>
              Object.entries(codes).map(([code, expect]) => ({
                patient: pid,
                population: code,
                expect,
              })),
            ) as unknown[])
          : null,
        prefs: {},
        measure,
        viewConfig,
        runHistory,
        activeTabPref: resultsTab,
      }).catch(() => undefined);
    }, 800);
    return () => clearTimeout(t);
  }, [
    libraries,
    dataset,
    measure,
    expectedValues,
    viewConfig,
    runHistory,
    resultsTab,
    restored,
  ]);

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
      outputColumns: outputColumns,
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
      cases: expectedValues
        ? (Object.entries(expectedValues).flatMap(([pid, codes]) =>
            Object.entries(codes).map(([code, expect]) => ({
              patient: pid,
              population: code,
              expect,
            })),
          ) as unknown[])
        : null,
      prefs: {},
      measure,
      viewConfig,
      runHistory,
      activeTabPref: resultsTab,
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

  // §3.4 Bundle export/import for the dataset.
  const bundleFileRef = useRef<HTMLInputElement | null>(null);
  const [bundleMode, setBundleMode] = useState<"merge" | "replace">("merge");

  const exportBundleFile = () => {
    const resources = (dataset?.resources ?? []) as Array<
      Record<string, unknown>
    >;
    if (!resources.length) {
      setStatusNote("nothing to export: dataset is empty");
      return;
    }
    const bundle = exportBundle(resources);
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/fhir+json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "cleanroom-dataset-bundle.json";
    a.click();
    URL.revokeObjectURL(url);
  };

  const importBundleFile = async (file: File) => {
    try {
      const parsed = JSON.parse(await file.text());
      const result = importBundle(parsed);
      if (result.rejected.length) {
        setStatusNote(
          `imported ${result.resources.length} resource(s); ` +
            `rejected ${result.rejected.length} entry/entries without id ` +
            `or fullUrl (indexes ${result.rejected.slice(0, 5).join(", ")})`,
        );
      } else if (result.synthesizedIds) {
        setStatusNote(
          `imported ${result.resources.length} resource(s); ` +
            `synthesized ${result.synthesizedIds} id(s) from fullUrl`,
        );
      }
      const current = (dataset?.resources ?? []) as Array<
        Record<string, unknown>
      >;
      const next =
        bundleMode === "replace"
          ? result.resources
          : mergeDatasets(current, result.resources);
      setDataset(next.length ? { resources: next } : null);
    } catch (e) {
      setStatusNote(
        `bundle import failed: ${e instanceof Error ? e.message : String(e)}`,
      );
    }
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
      setMeasure(state.measure ?? DEFAULT_MEASURE);
      setViewConfig(state.viewConfig ?? null);
      if (Array.isArray(state.cases)) {
        const ev: { [pid: string]: { [code: string]: boolean } } = {};
        for (const c of state.cases as Array<{ patient?: string; population?: string; expect?: boolean }>) {
          if (typeof c?.patient === "string" && typeof c?.population === "string") {
            ev[c.patient] = { ...(ev[c.patient] ?? {}), [c.population]: c.expect === true };
          }
        }
        setExpectedValues(Object.keys(ev).length ? ev : null);
      } else {
        setExpectedValues(null);
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
          <button data-testid="bundle-export" onClick={exportBundleFile}>
            Export Bundle
          </button>
          <button
            data-testid="bundle-import"
            onClick={() => bundleFileRef.current?.click()}
            title={`import mode: ${bundleMode} (click mode to toggle)`}
          >
            Import Bundle
          </button>
          <button
            data-testid="bundle-mode"
            onClick={() =>
              setBundleMode((m) => (m === "merge" ? "replace" : "merge"))
            }
          >
            mode: {bundleMode}
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
              setMeasure(DEFAULT_MEASURE);
              setExpectedValues(null);
              setLastReports(null);
              setViewConfig(null);
              setRunHistory([]);
              setResultsTab("cql");
              setCurrentRun(null);
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
          <input
            ref={bundleFileRef}
            type="file"
            accept=".json,application/json"
            hidden
            data-testid="bundle-import-input"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void importBundleFile(f);
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
          <div className="results-drawer editor-drawer" data-testid="drawer-graph">
            <button
              className="drawer-toggle"
              data-testid="drawer-graph-toggle"
              onClick={() => setGraphOpen(!graphOpen)}
            >
              {graphOpen ? "▾" : "▸"} Visual editor
            </button>
            {graphOpen && (
              <div className="drawer-body">
                <p className="pane-hint">
                  The graph writes CQL only — Apply replaces the library
                  text after a parse round-trip. Full text→graph parsing is
                  future scope; the canvas starts from the default graph.
                </p>
                <GraphPane onApplyCql={(cql) => updateActiveText(cql)} />
              </div>
            )}
          </div>
          <div className="results-drawer editor-drawer" data-testid="drawer-fhirpath">
            <button
              className="drawer-toggle"
              data-testid="drawer-fhirpath-toggle"
              onClick={() => setFhirpathOpen(!fhirpathOpen)}
            >
              {fhirpathOpen ? "▾" : "▸"} FHIRPath scratchpad
            </button>
            {fhirpathOpen && (
              <div className="drawer-body">
                <FhirpathPane dataset={dataset} />
              </div>
            )}
          </div>
        </div>
        <div className="pane-col run-col">
          <ResultsPane
            libraries={[main]}
            main={main}
            dataset={dataset}
            outputColumns={outputColumns}
            measure={measure}
            onReports={(reports) => {
              setLastReports(reports);
            }}
            activeTab={resultsTab}
            onTabChange={setResultsTab}
            viewSql={viewSql}
            reports={lastReports}
            onEvaluated={async (env) => {
              // §3.3: capture the run (row-shaped artifact + hashes).
              const [libHash, dsHash] = await Promise.all([
                computeLibraryHash(main.text),
                computeDatasetHash(
                  dataset?.resources?.length
                    ? { resources: dataset.resources as unknown[] }
                    : null,
                ),
              ]);
              const entry: RunEntry = {
                id: newRunId(),
                name: defaultRunName(Date.now()),
                createdAt: Date.now(),
                libraryHash: libHash,
                datasetHash: dsHash,
                artifact: artifactFromRows(env.rows, env.columns),
              };
              setRunHistory((h) => appendRun(h, entry, RUN_HISTORY_CAP));
              setCurrentRun({
                artifact: entry.artifact,
                libraryHash: libHash,
                datasetHash: dsHash,
              });
            }}
            measureSlot={
              <MeasurePane
                libraries={[main]}
                main={main}
                measure={measure}
                onChange={(m) => {
                  setMeasure(m);
                  setLastReports(null);
                }}
              />
            }
            viewSlot={
              <ViewPane
                measure={measure}
                measureReports={lastReports}
                viewConfig={viewConfig?.overrides ?? null}
                onViewConfigChange={(overrides) => setViewConfig({ overrides })}
                onSql={setViewSql}
              />
            }
            evidenceSlot={
              <EvidencePane
                libraries={[main]}
                main={main}
                dataset={
                  dataset?.resources?.length
                    ? { resources: dataset.resources as unknown[] }
                    : null
                }
                outputColumns={outputColumns}
                runHistory={runHistory}
                currentArtifact={currentRun?.artifact ?? null}
                currentLibraryHash={currentRun?.libraryHash ?? null}
                currentDatasetHash={currentRun?.datasetHash ?? null}
                onDeleteRun={(id) =>
                  setRunHistory((h) => h.filter((r) => r.id !== id))
                }
                onRenameRun={(id, name) =>
                  setRunHistory((h) =>
                    h.map((r) => (r.id === id ? { ...r, name } : r)),
                  )
                }
              />
            }
            testsSlot={
              <TestsPane
                libraries={[main]}
                main={main}
                dataset={dataset}
                outputColumns={outputColumns}
                populationCodes={populationCodes}
                expectedValues={expectedValues}
                onExpectedValuesChange={setExpectedValues}
                measure={measure}
              />
            }
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
            onAddForPatient={(patientId) => {
              setBuilderPrefill(null);
              setBuilderContext({ patientId, nonce: Date.now() });
            }}
          />
          <ResourceBuilderPane
            onAddResource={(resource) => {
              const resources = [...(dataset?.resources ?? []), resource];
              setDataset(dataset ? { ...dataset, resources } : { resources });
              setBuilderPrefill(null);
              setBuilderContext(null);
            }}
            prefill={builderPrefill}
            context={builderContext}
            dataset={dataset}
          />
        </div>
      </main>
      <BootOverlay state={boot} />
    </div>
  );
}
