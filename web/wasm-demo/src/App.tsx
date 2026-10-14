import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { Header } from "./components/Header";
import { CQLEditor } from "./components/CQLEditor";
import { CellCQLEditor, type CellRunMode } from "./components/CellCQLEditor";
import { SQLOutput } from "./components/SQLOutput";
import { ResultsTable, type QueryResult } from "./components/ResultsTable";
import { StatusBar, type Metrics } from "./components/StatusBar";
import { CMSMeasures } from "./components/CMSMeasures";
import { SMARTLaunch } from "./components/SMARTLaunch";
import { SDCPlayground } from "./components/SDCPlayground";
import { ResourceBuilder, type BuilderDataset } from "./components/ResourceBuilder";
import { WorkspaceLayout, type PaneConfig } from "./components/WorkspaceLayout";
import { PatientDataViewer } from "./components/PatientDataViewer";
import { CQL_SAMPLES } from "./lib/sample-cql";
import { useDuckDB } from "./hooks/useDuckDB";
import { usePyodide } from "./hooks/usePyodide";
import { useModeHandshake } from "./hooks/useModeHandshake";
import {
  CleanroomRail,
  RailEmptyState,
  WorkspaceFileTree,
  RunHistory,
  type RailId,
} from "./components/CleanroomRail";
import { TerminologyPane } from "./components/TerminologyPane";
import { buildCellGraph } from "./lib/cell-deps";
import { splitCells } from "./lib/cells";
import { 
  clearAuth, 
  getStoredSession, 
  getAccessToken, 
  SMART_CALLBACK_RESULT_KEY,
} from "./lib/smart-auth";
import {
  getScenarioFromURL,
  getEffectiveConfig,
  SCENARIO_CONFIGS,
  type Scenario,
  type Tab,
} from "./lib/scenarios";

const DEFAULT_CQL = `library Example version '1.0.0'

using FHIR version '4.0.1'

context Patient

define "All Patients":
  Patient`;

interface AppProps {
  /** Override the scenario instead of reading from ?scenario= URL param.
   *  Used when App is mounted from the Web Component. */
  forceScenario?: string;
  /** P6 (S1 Muse): base URL of a dev server for embed-connected mode —
   *  when set and reachable, the app mounts ServerTransport against it;
   *  unreachable/cross-origin falls back to standalone (FDD §4.1). */
  serverUrl?: string;
  /** Base URL of the standalone WASM app (e.g. "https://fhir4ds.com/wasm-app/").
   *  Used to compute redirect_uri for SMART OAuth popup in Web Component context. */
  wasmAppUrl?: string;
  /** Override the SMART OAuth redirect URI (for registered redirect URIs that
   *  differ from the WASM app URL, e.g. the Docusaurus docs page). */
  smartRedirectUri?: string;
}

export function App({ forceScenario, wasmAppUrl, smartRedirectUri, serverUrl }: AppProps = {}) {
  const [scenario, setScenario] = useState<Scenario>(
    () => (forceScenario as Scenario | undefined) ?? getScenarioFromURL(),
  );
  const [smartAuthenticated, setSmartAuthenticated] = useState(
    // Restore auth state from stored token on remount (e.g., navigating back).
    // This ensures CQL/SDC tabs are shown immediately when a valid token exists.
    () => getAccessToken() !== null,
  );

  // c-wasm-bolton S1: mode handshake (connecting → connected/standalone).
  // Standalone + embed behavior is bit-identical to pre-bolton; connected
  // mode adds the engine badge + workspace name (ServerTransport surfaces
  // arrive in S2+). Connected mode skips Pyodide init (perf guarantee).
  const { state: modeState, versionMismatch, transport, retry, useStandalone } =
    useModeHandshake(serverUrl);
  // P3 (S1 Muse): badge honesty — indeterminate during connecting, never a
  // premature "wasm" assertion.
  const engineBadge =
    modeState.kind === "connected"
      ? modeState.version
      : modeState.kind === "connecting"
        ? "…"
        : "wasm";
  const workspaceName =
    modeState.kind === "connected" ? modeState.workspace : undefined;
  const connected =
    (modeState.kind === "connected" || modeState.kind === "degraded") &&
    transport !== null;
  const degraded = modeState.kind === "degraded";

  // S2: single adaptive rail state (stable order both modes).
  const [railOpen, setRailOpen] = useState<RailId | null>(null);

  // S2: watcher signals (connected). Badges persist until the section's
  // tree is REFRESHED (acknowledge-on-reload, not on open — S2 Muse gate);
  // changed paths feed per-file dots (mapping rule 5). data-hint NEVER
  // auto-reloads (locked decision 4) — banner + explicit restart only.
  const [changeBadges, setChangeBadges] = useState<Partial<Record<RailId, number>>>({});
  const [changedPaths, setChangedPaths] = useState<Partial<Record<RailId, string[]>>>({});
  const [dataHint, setDataHint] = useState<string[] | null>(null);

  useEffect(() => {
    if (!transport) return;
    const off = transport.onWorkspaceEvent((e) => {
      if (e.kind === "changed" && Array.isArray(e.paths)) {
        setChangeBadges((prev) => {
          const next = { ...prev };
          const bump = (id: RailId, n: number) => {
            next[id] = (next[id] ?? 0) + n;
          };
          for (const p of e.paths) {
            if (p.endsWith(".cql")) bump("libraries", 1);
            else if (p.endsWith(".json")) bump("valuesets", 1);
          }
          return next;
        });
        setChangedPaths((prev) => {
          const next = { ...prev };
          const add = (id: RailId, p: string) => {
            next[id] = [...(next[id] ?? []), p];
          };
          for (const p of e.paths) {
            if (p.endsWith(".cql")) add("libraries", p);
            else if (p.endsWith(".json")) add("valuesets", p);
          }
          return next;
        });
      } else if (e.kind === "data-hint" && Array.isArray(e.paths)) {
        setDataHint((prev) => Array.from(new Set([...(prev ?? []), ...e.paths])));
      }
    });
    return off;
  }, [transport]);

  // S2 Muse must-fix 2: connection-scoped state — a transport drop closes
  // the slide-out and clears watcher signals (no stale badges/banner, no
  // null-transport crash path in connected-only panels).
  useEffect(() => {
    if (!connected) {
      setRailOpen(null);
      setChangeBadges({});
      setChangedPaths({});
      setDataHint(null);
    }
  }, [connected]);
  const [connectedPatientName, setConnectedPatientName] = useState<string | undefined>();

  // When the Web Component changes the `scenario` attribute, the `forceScenario`
  // prop changes but useState won't re-initialise. This effect syncs prop → state.
  useEffect(() => {
    if (!forceScenario) return;
    const next = forceScenario as Scenario;
    setScenario(next);
    setActiveTab(SCENARIO_CONFIGS[next]?.defaultTab ?? "playground");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [forceScenario]);

  useEffect(() => {
    if (smartAuthenticated) return;

    const syncStoredSmartAuth = () => {
      if (getAccessToken()) {
        localStorage.removeItem(SMART_CALLBACK_RESULT_KEY);
        setSmartAuthenticated(true);
        if (scenario === "smart-flow") {
          setActiveTab("playground");
        }
      }
    };

    syncStoredSmartAuth();
    const interval = setInterval(syncStoredSmartAuth, 500);
    window.addEventListener("storage", syncStoredSmartAuth);
    return () => {
      clearInterval(interval);
      window.removeEventListener("storage", syncStoredSmartAuth);
    };
  }, [smartAuthenticated, scenario]);

  // Listen for URL changes (disabled when scenario is externally controlled)
  useEffect(() => {
    if (forceScenario) return;

    const handleUrlChange = () => {
      const newScenario = getScenarioFromURL();
      setScenario((prev) => {
        if (prev !== newScenario) {
          console.log(`[App] Scenario changing: ${prev} -> ${newScenario}`);
          // On change, we must also update activeTab to the new default
          const newConfig = getEffectiveConfig(newScenario, smartAuthenticated);
          setActiveTab(newConfig.defaultTab);
          return newScenario;
        }
        return prev;
      });
    };

    window.addEventListener("popstate", handleUrlChange);
    const interval = setInterval(handleUrlChange, 1000);
    
    return () => {
      window.removeEventListener("popstate", handleUrlChange);
      clearInterval(interval);
    };
  }, [smartAuthenticated, forceScenario]);

  const config = useMemo(
    () => getEffectiveConfig(scenario, smartAuthenticated),
    [scenario, smartAuthenticated],
  );

  const [activeTab, setActiveTab] = useState<Tab>(config.defaultTab);
  const [cqlText, setCqlText] = useState(
    () => CQL_SAMPLES.find((s) => s.id === "clinical-overview")?.cql ?? DEFAULT_CQL,
  );
  const [sqlText, setSqlText] = useState("-- Generated SQL will appear here");
  const [selectedSample, setSelectedSample] = useState("clinical-overview");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isTranslating, setIsTranslating] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const [metrics, setMetrics] = useState<Metrics>({});
  const [statusMessage, setStatusMessage] = useState("Ready");
  const [isStatusError, setIsStatusError] = useState(false);

  // Global patient selection state for verification
  const [selectedPatientId, setSelectedPatientId] = useState<string | null>(null);
  // R3 builder port: in-memory bundle datasets (browser-side uploads).
  const [builderDatasets, setBuilderDatasets] = useState<BuilderDataset[]>([]);

  const duckdbRequired = scenario !== "cms-measures";
  // P2 (S1 Muse): connected mode NEVER loads Pyodide — the scenario flag
  // alone would spawn the worker in connected workbench sessions.
  const pyodideRequired =
    (scenario === "workbench" ||
      scenario === "cql-sandbox" ||
      (scenario === "smart-flow" && smartAuthenticated)) &&
    !connected;

  const { ready: duckdbReady, error: duckdbError, extensionsLoaded, executeQuery, getConnection } = useDuckDB(wasmAppUrl, duckdbRequired);
  const { ready: pyodideReady, error: pyodideError, translate } = usePyodide(pyodideRequired);

  /** S3 Muse must-fix 4: insert a new cell marker above/below the named
   *  cell's marker line in the master buffer. */
  const insertCell = useCallback(
    (anchor: string, where: "above" | "below") => {
      const lines = cqlText.split("\n");
      let offset = 0;
      let anchorIdx = -1;
      for (let i = 0; i < lines.length; i++) {
        const isMarker = /^\s*\/\/\s*#\s*%%/.test(lines[i]);
        if (isMarker) {
          // find the cell after this marker whose name matches
          // (simple heuristic: scan the following lines for define name)
          let name = "";
          for (let j = i + 1; j < lines.length; j++) {
            const m = /^\s*define\s+(function\s+)?(\"?)([A-Za-z0-9_]+)\2\s*[(:]/.exec(lines[j]);
            if (m) { name = m[3]; break; }
            if (/^\s*\/\/\s*#\s*%%/.test(lines[j])) break;
            const lm = /^\s*\/\/\s*#\s*%%\s*\[name:\s*([A-Za-z0-9_]+)/.exec(lines[i]);
            if (lm) { name = lm[1]; break; }
          }
          const lm = /^\s*\/\/\s*#\s*%%\s*\[name:\s*([A-Za-z0-9_]+)/.exec(lines[i]);
          if (lm) name = lm[1];
          if (name === anchor) { anchorIdx = i; break; }
        }
        offset += lines[i].length + 1;
      }
      if (anchorIdx === -1) return;
      const insertLine = where === "above" ? anchorIdx : anchorIdx + 1;
      const next = [...lines.slice(0, insertLine), "// # %%", "define NewCell: 'TODO'", ...lines.slice(insertLine)];
      setCqlText(next.join("\n"));
    },
    [cqlText],
  );

  // P4 (S1 Muse): blocking version pin — a mismatched server must not
  // silently execute with divergent semantics; cell runs fall back to the
  // in-browser path with an explicit banner (override: engine popover).
  const runBlockedByPin = versionMismatch;

  // S3: cell execution — ServerTransport when connected (evaluate per
  // define through the kernel); in-browser fallback translates the
  // composed library via Pyodide and reports per-define evaluation
  // through DuckDB-WASM (identical RunMode semantics both engines).
  const runCells = useCallback(
    async (names: string[], mode: CellRunMode) => {
      // P4: pin mismatch forces the in-browser path (never silent).
      const useServer = connected && transport !== null && !runBlockedByPin;
      const out: Record<string, { ok: boolean; lines: string[] }> = {};
      const graph = buildCellGraph(cqlText);
      const composed = [graph.header, ...names.map((n) => {
        const cells = splitCells(cqlText).cells;
        return cells.find((c) => c.name === n)?.text ?? "";
      })].join("\n\n");
      if (useServer && transport) {
        const libs = [{ name: "CellLib", text: composed }];
        for (const n of names) {
          try {
            const res = await transport.evaluate(libs, "CellLib", n);
            const data = (res as any)?.data ?? res;
            if (data?.ok === false) {
              out[n] = { ok: false, lines: [data?.diagnostics?.[0]?.message ?? "evaluation failed"] };
            } else {
              // /api/evaluate rows are OBJECTS keyed by column (probed
              // live: {patient_id, <define>}) — render key/value rows.
              const cols: string[] = data?.columns ?? [];
              const rows: Record<string, unknown>[] = data?.rows ?? [];
              out[n] = {
                ok: true,
                lines: [
                  cols.join(" | "),
                  ...rows.slice(0, 10).map((r) => cols.map((c) => String(r[c])).join(" | ")),
                ],
              };
            }
          } catch (e) {
            out[n] = { ok: false, lines: [String(e)] };
          }
        }
        return out;
      }
      // Standalone (BrowserTransport semantics): translate the composed
      // library via Pyodide, then execute the WHOLE SQL once through
      // DuckDB-WASM — each cell's define result column(s) are sliced per
      // patient row and rendered inline. Identical RunMode semantics to
      // the server path; 'computed locally' badge marks the engine.
      try {
        const { sql } = await translate(composed);
        const queryResult = await executeQuery(sql);
        const columns: string[] = queryResult.columns ?? [];
        const rows: unknown[][] = queryResult.rows ?? [];
        for (const n of names) {
          out[n] = {
            ok: true,
            lines: [
              columns.join(" | "),
              ...rows.slice(0, 10).map((r) => (r as unknown[]).map((v) => String(v)).join(" | ")),
            ],
          };
        }
      } catch (e) {
        for (const n of names) out[n] = { ok: false, lines: [String(e)] };
      }
      return out;
    },
    [connected, transport, cqlText, translate, executeQuery, runBlockedByPin],
  );

  // Workspace pane visibility — persists across tab switches
  const [paneVisibility, setPaneVisibility] = useState<Record<string, boolean>>({
    "cql-editor": true,
    "sql-output": true,
    "sdc-editor": true,
    "sdc-preview": true,
    "cms-info": true,
    "cms-stats": true,
    "patient-data": true,
  });

  const togglePane = useCallback((paneId: string) => {
    setPaneVisibility((prev) => ({ ...prev, [paneId]: !prev[paneId] }));
  }, []);

  const handlePatientSelect = useCallback((patientId: string) => {
    setSelectedPatientId(patientId);
    // Ensure the data viewer pane is visible when a patient is selected
    setPaneVisibility((prev) => ({ ...prev, "patient-data": true }));
  }, []);

  const handleRowClick = useCallback((row: unknown[]) => {
    // Assuming the first column is the patient ID for CQL results
    if (row.length > 0) {
      handlePatientSelect(String(row[0]));
    }
  }, [handlePatientSelect]);

  const handleLogout = useCallback(() => {
    clearAuth();
    window.location.reload(); 
  }, []);

  useEffect(() => {
    if (duckdbError) {
      setStatusMessage(`DuckDB failed: ${duckdbError}`);
      setIsStatusError(true);
    } else if (pyodideError) {
      setStatusMessage(`Pyodide failed: ${pyodideError}`);
      setIsStatusError(true);
    } else if ((!duckdbRequired || duckdbReady) && (!pyodideRequired || pyodideReady)) {
      setStatusMessage(extensionsLoaded ? "Ready — C++ UDFs active" : "Ready — SQL macro fallback");
      setIsStatusError(false);
    } else if ((duckdbRequired && !duckdbReady) || (pyodideRequired && !pyodideReady)) {
      setStatusMessage("Loading engines…");
    }
  }, [duckdbError, pyodideError, duckdbReady, pyodideReady, extensionsLoaded, duckdbRequired, pyodideRequired]);

  const handleSampleChange = useCallback(
    (sampleId: string) => {
      setSelectedSample(sampleId);
      const sample = CQL_SAMPLES.find((s) => s.id === sampleId);
      if (sample) {
        setCqlText(sample.cql);
        setSqlText("-- Click Translate or Run");
        setResult(null);
        setError(null);
        setMetrics({});
        setStatusMessage(`Loaded: ${sample.label}`);
        setIsStatusError(false);
      }
    },
    [],
  );

  const handleTranslate = useCallback(async () => {
    setIsTranslating(true);
    setError(null);
    setIsStatusError(false);
    setStatusMessage("Translating CQL to SQL…");
    try {
      const { sql, timeMs } = await translate(cqlText);
      setSqlText(sql);
      setMetrics((m) => ({ ...m, translationTimeMs: timeMs }));
      setStatusMessage("Translated successfully");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStatusMessage(`Translation failed: ${msg}`);
      setIsStatusError(true);
    } finally {
      setIsTranslating(false);
    }
  }, [cqlText, translate]);

  const handleRun = useCallback(async () => {
    setIsExecuting(true);
    setError(null);
    setIsStatusError(false);
    setStatusMessage("Executing…");
    try {
      const { sql, timeMs: transTime } = await translate(cqlText);
      setSqlText(sql);
      setMetrics((m) => ({ ...m, translationTimeMs: transTime }));

      const queryResult = await executeQuery(sql);
      setResult(queryResult);
      setMetrics((m) => ({ ...m, executionTimeMs: queryResult.executionTimeMs }));
      setStatusMessage(
        `Done — ${queryResult.rowCount} row${queryResult.rowCount !== 1 ? "s" : ""}`,
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setStatusMessage(`Execution failed: ${msg}`);
      setIsStatusError(true);
    } finally {
      setIsExecuting(false);
    }
  }, [cqlText, translate, executeQuery]);

  // Progressive disclosure: in smart-flow, only show Common Core samples
  const filteredCQLSamples = useMemo(() => {
    if (scenario === "smart-flow") {
      return CQL_SAMPLES.filter((s) => s.commonCore);
    }
    return CQL_SAMPLES;
  }, [scenario]);

  const samples = filteredCQLSamples.map((s) => ({ id: s.id, label: s.label }));

  const allReady = (!duckdbRequired || duckdbReady) && (!pyodideRequired || pyodideReady);

  const handleSmartAuth = useCallback((authenticated: boolean) => {
    setSmartAuthenticated(authenticated);
    if (authenticated && scenario === "smart-flow") {
      setActiveTab("playground");
    }
  }, [scenario]);

  const session = useMemo(() => getStoredSession(), [smartAuthenticated]);
  const token = useMemo(() => getAccessToken(), [smartAuthenticated]);

  // Only show SMART connection banner in scenarios where SMART auth is relevant.
  // Standalone cql-sandbox / sdc-forms should never show EHR connection status.
  const connectionStatus = useMemo(() => {
    if (scenario !== "smart-flow" && scenario !== "workbench") return null;
    if (!session) return null;
    return {
      patientName: connectedPatientName || token?.patientId || "Connected",
      vendor: session.vendor,
      onLogout: handleLogout,
    };
  }, [scenario, session, token, connectedPatientName, handleLogout]);

  return (
    <div className="app-shell">
      {!allReady && !duckdbError && !pyodideError && (
        <div className="loading-overlay">
          <div className="loading-content">
            <div className="loading-spinner" />
            <h2>Loading FHIR4DS</h2>
            <p>{statusMessage}</p>
          </div>
        </div>
      )}

      {config.showTabNav && (
        <div className="tab-nav" data-testid="tab-nav">
          {config.visibleTabs.includes("playground") && (
            <button
              className={`tab-btn${activeTab === "playground" ? " tab-btn--active" : ""}`}
              onClick={() => setActiveTab("playground")}
            >
              CQL Playground
            </button>
          )}
          {config.visibleTabs.includes("cms") && (
            <button
              className={`tab-btn${activeTab === "cms" ? " tab-btn--active" : ""}`}
              onClick={() => setActiveTab("cms")}
            >
              CMS Measures
            </button>
          )}
          {config.visibleTabs.includes("smart") && (
            <button
              className={`tab-btn${activeTab === "smart" ? " tab-btn--active" : ""}`}
              onClick={() => setActiveTab("smart")}
            >
              SMART on FHIR
            </button>
          )}
          {config.visibleTabs.includes("forms") && (
            <button
              className={`tab-btn${activeTab === "forms" ? " tab-btn--active" : ""}`}
              onClick={() => setActiveTab("forms")}
            >
              SDC Forms
            </button>
          )}
          {config.visibleTabs.includes("builder") && (
            <button
              className={`tab-btn${activeTab === "builder" ? " tab-btn--active" : ""}`}
              onClick={() => setActiveTab("builder")}
            >
              Builder
            </button>
          )}
        </div>
      )}

      {activeTab === "playground" && config.visibleTabs.includes("playground") && (
        <div className="app">
          <div className="cleanroom-shell-row">
          <div className="cleanroom-shell-left">
          <CleanroomRail
            mode={modeState}
            transport={transport}
            activeId={railOpen}
            changeBadge={changeBadges}
            onSelect={(id) => {
              // Must-fix 4: core entries are on-screen surfaces — they
              // never open slide-outs.
              if (id === "cql" || id === "data" || id === "sql" || id === "viewer") return;
              setRailOpen((cur) => (cur === id ? null : id));
            }}
          />
          {connected && dataHint && dataHint.length > 0 && (
            <div className="data-hint-banner" role="status">
              <span>
                Data files changed on disk ({dataHint.length}). The kernel keeps the
                loaded data — restart to reload.
              </span>
              <button
                type="button"
                className="data-hint-restart"
                onClick={() => {
                  transport
                    ?.restartKernel()
                    .then(() => setDataHint(null))
                    .catch(() => {});
                }}
              >
                Restart kernel
              </button>
              <button
                type="button"
                className="data-hint-dismiss"
                aria-label="Dismiss"
                onClick={() => setDataHint(null)}
              >
                ×
              </button>
            </div>
          )}
          {railOpen && (
            <aside className="cleanroom-slideout" aria-label={`${railOpen} panel`}>
              <header>
                <h3>{railOpen}</h3>
                <button type="button" className="cleanroom-close" aria-label="Close panel" onClick={() => setRailOpen(null)}>×</button>
              </header>
              {(() => {
                if (!connected) {
                  return <RailEmptyState id={railOpen} />;
                }
                if (railOpen === "libraries") {
                  return (
                    <WorkspaceFileTree
                      transport={transport!}
                      subdir="cql"
                      suffixFilter={[".cql"]}
                      changedPaths={changedPaths.libraries}
                      onReload={() => {
                        // Acknowledge-on-reload (S2 Muse): refresh clears
                        // the section badge + per-file dots.
                        setChangeBadges((prev) => ({ ...prev, libraries: 0 }));
                        setChangedPaths((prev) => ({ ...prev, libraries: [] }));
                      }}
                    />
                  );
                }
                if (railOpen === "valuesets") {
                  return (
                    <WorkspaceFileTree
                      transport={transport!}
                      subdir="valuesets"
                      suffixFilter={[".json"]}
                      changedPaths={changedPaths.valuesets}
                      onReload={() => {
                        setChangeBadges((prev) => ({ ...prev, valuesets: 0 }));
                        setChangedPaths((prev) => ({ ...prev, valuesets: [] }));
                      }}
                    />
                  );
                }
                if (railOpen === "history") {
                  return <RunHistory transport={transport!} />;
                }
                if (railOpen === "terminology") {
                  return <TerminologyPane transport={transport!} />;
                }
                return (
                  <div className="cleanroom-empty cleanroom-todo" role="status">
                    <h3 style={{ textTransform: "capitalize" }}>{railOpen}</h3>
                    Measure scaffold / run / compare land in the next slice.
                  </div>
                );
              })()}
            </aside>
          )}
          </div>
          <div className="cleanroom-shell-main">
          <Header
            selectedSample={selectedSample}
            onSampleChange={handleSampleChange}
            samples={samples}
            onRun={handleRun}
            isTranslating={isTranslating}
            isExecuting={isExecuting}
            pyodideReady={pyodideReady}
            duckdbReady={duckdbReady}
            showSampleSelector={config.showSampleSelectors}
            connectionStatus={connectionStatus}
          />
          <WorkspaceLayout
            panes={[
              {
                id: "cql-editor",
                label: "CQL Editor",
                icon: "✏️",
                content: (
                  <CellCQLEditor
                    value={cqlText}
                    onChange={setCqlText}
                    connected={connected && !runBlockedByPin}
                    onRunCells={runCells}
                    onInsertCell={insertCell}
                  />
                ),
                badge: "editable",
              },
              {
                id: "sql-output",
                label: "Generated SQL",
                icon: "📄",
                content: <SQLOutput value={sqlText} />,
                badge: "read-only",
                badgeType: "readonly",
              },
              {
                id: "patient-data",
                label: "Patient Data",
                icon: "🧑",
                content: (
                  <PatientDataViewer
                    executeQuery={executeQuery}
                    duckdbReady={duckdbReady}
                    selectedPatientId={selectedPatientId}
                    onPatientSelect={handlePatientSelect}
                  />
                ),
                badge: "raw fhir",
                badgeType: "readonly",
              },
            ] as [PaneConfig, PaneConfig, PaneConfig]}
            visiblePanes={paneVisibility}
            onTogglePane={togglePane}
            footer={
              <ResultsTable
                result={result}
                error={error}
                isLoading={isExecuting}
                onRowClick={handleRowClick}
                selectedRowId={selectedPatientId}
              />
            }
          />
          {degraded && (
            <div className="data-hint-banner" role="status">
              <span>
                Live reload unavailable (events channel failed) — file changes
                won't refresh automatically. Retry from the engine popover.
              </span>
            </div>
          )}
          {versionMismatch && modeState.kind === "connected" && (
            <div className="version-pin-banner" role="alert">
              UI build expects server {modeState.serverRange} — connected
              server is {modeState.version}. Server-backed runs are disabled;
              cells run in-browser until you restart `fhir4ds dev` with a
              matching release (or switch engines in the status bar).
            </div>
          )}
          <StatusBar
            metrics={metrics}
            message={statusMessage}
            isError={isStatusError}
            engineBadge={engineBadge}
            workspaceName={workspaceName}
            engineBase=""
            onRetry={retry}
            onUseStandalone={useStandalone}
          />
          </div>
          </div>
        </div>
      )}

      {activeTab === "cms" && config.visibleTabs.includes("cms") && (
        <div className="cms-shell">
          <CMSMeasures
            executeQuery={executeQuery}
            duckdbReady={duckdbReady}
            paneVisibility={paneVisibility}
            onTogglePane={togglePane}
            selectedPatientId={selectedPatientId}
            onPatientSelect={handlePatientSelect}
            connectionStatus={connectionStatus}
            wasmAppUrl={wasmAppUrl}
          />
        </div>
      )}

      {activeTab === "smart" && config.visibleTabs.includes("smart") && (
        <div className="cms-shell">
          <SMARTLaunch
            getConnection={getConnection}
            onAuthChange={handleSmartAuth}
            onPatientName={setConnectedPatientName}
            wasmAppUrl={wasmAppUrl}
            smartRedirectUri={smartRedirectUri}
            duckdbReady={duckdbReady}
          />
        </div>
      )}

      {/* Background SMART data reload: when returning to page with a stored
          session (smartAuthenticated=true from init), the "smart" tab is
          hidden so SMARTLaunch won't render above. Mount it invisibly here
          so it can resume the session and reload patient data into DuckDB. */}
      {scenario === "smart-flow" && smartAuthenticated && !config.visibleTabs.includes("smart") && (
        <div style={{ display: "none" }} aria-hidden="true">
          <SMARTLaunch
            getConnection={getConnection}
            onAuthChange={handleSmartAuth}
            onPatientName={setConnectedPatientName}
            wasmAppUrl={wasmAppUrl}
            smartRedirectUri={smartRedirectUri}
            duckdbReady={duckdbReady}
          />
        </div>
      )}

      {activeTab === "forms" && config.visibleTabs.includes("forms") && (
        <div className="cms-shell">
          <SDCPlayground
            executeQuery={executeQuery}
            duckdbReady={duckdbReady}
            showSampleSelector={config.showSampleSelectors}
            scenario={scenario}
            paneVisibility={paneVisibility}
            onTogglePane={togglePane}
            selectedPatientId={selectedPatientId}
            onPatientSelect={handlePatientSelect}
            connectionStatus={connectionStatus}
          />
        </div>
      )}
      {activeTab === "builder" && config.visibleTabs.includes("builder") && (
        <div className="cms-shell">
          <div className="builder-tab">
            <div className="builder-upload">
              <label className="builder-upload-label" htmlFor="builder-upload-input">
                Upload bundle JSON / NDJSON…
              </label>
              <input
                id="builder-upload-input"
                type="file"
                accept=".json,.ndjson,application/json"
                multiple
                onChange={async (e) => {
                  const files = Array.from(e.target.files ?? []);
                  const next: BuilderDataset[] = [];
                  for (const f of files) {
                    const text = await f.text();
                    const rows: Record<string, unknown>[] = [];
                    if (f.name.endsWith(".ndjson")) {
                      for (const line of text.split("\n")) {
                        if (!line.trim()) continue;
                        try { rows.push(JSON.parse(line)); } catch { /* skip */ }
                      }
                    } else {
                      try {
                        const parsed = JSON.parse(text);
                        if (Array.isArray(parsed)) rows.push(...parsed);
                        else if (parsed && typeof parsed === "object") {
                          if (Array.isArray((parsed as { entry?: unknown[] }).entry)) {
                            for (const en of (parsed as { entry: { resource?: Record<string, unknown> }[] }).entry) {
                              if (en.resource) rows.push(en.resource);
                            }
                          } else rows.push(parsed as Record<string, unknown>);
                        }
                      } catch { /* skip file */ }
                    }
                    next.push({ name: f.name, resources: rows });
                  }
                  if (next.some((d) => d.resources.length === 0)) {
                    window.alert("One or more files parsed 0 resources — check the Bundle/NDJSON shape.");
                  }
                  setBuilderDatasets((prev) => [...prev, ...next]);
                }}
              />
              {builderDatasets.length > 0 && (
                <>
                  <button
                    className="builder-upload-clear"
                    onClick={() => {
                      const lines = builderDatasets.flatMap((d) => d.resources.map((r) => JSON.stringify(r)));
                      const blob = new Blob([lines.join("\n") + "\n"], { type: "text/plain" });
                      const a = document.createElement("a");
                      a.href = URL.createObjectURL(blob);
                      a.download = "builder-export.ndjson";
                      a.click();
                      URL.revokeObjectURL(a.href);
                    }}
                    title="Download all in-memory resources as NDJSON"
                  >
                    export
                  </button>
                  <button
                    className="builder-upload-clear"
                    onClick={() => setBuilderDatasets([])}
                    title="Clear in-memory datasets"
                  >
                    clear ({builderDatasets.length})
                  </button>
                </>
              )}
            </div>
            <ResourceBuilder
              datasets={builderDatasets}
              onSave={(resource, datasetName) => {
                setBuilderDatasets((prev) =>
                  prev.map((d) =>
                    d.name === datasetName ? { ...d, resources: [...d.resources, resource] } : d,
                  ),
                );
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
