import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import { Header } from "./components/Header";
import { CQLEditor } from "./components/CQLEditor";
import { SQLOutput } from "./components/SQLOutput";
import { ResultsTable, type QueryResult } from "./components/ResultsTable";
import { StatusBar, type Metrics } from "./components/StatusBar";
import { CMSMeasures } from "./components/CMSMeasures";
import { SMARTLaunch } from "./components/SMARTLaunch";
import { SDCPlayground } from "./components/SDCPlayground";
import { WorkspaceLayout, type PaneConfig } from "./components/WorkspaceLayout";
import { PatientDataViewer } from "./components/PatientDataViewer";
import { CQL_SAMPLES } from "./lib/sample-cql";
import { useDuckDB } from "./hooks/useDuckDB";
import { usePyodide } from "./hooks/usePyodide";
import { 
  clearAuth, 
  getStoredSession, 
  getAccessToken, 
  handleCallback 
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
  /** Base URL of the standalone WASM app (e.g. "https://fhir4ds.com/wasm-app/").
   *  Used to compute redirect_uri for SMART OAuth popup in Web Component context. */
  wasmAppUrl?: string;
  /** Override the SMART OAuth redirect URI (for registered redirect URIs that
   *  differ from the WASM app URL, e.g. the Docusaurus docs page). */
  smartRedirectUri?: string;
}

export function App({ forceScenario, wasmAppUrl, smartRedirectUri }: AppProps = {}) {
  const [scenario, setScenario] = useState<Scenario>(
    () => (forceScenario as Scenario | undefined) ?? getScenarioFromURL(),
  );
  const [smartAuthenticated, setSmartAuthenticated] = useState(
    // Restore auth state from stored token on remount (e.g., navigating back).
    // This ensures CQL/SDC tabs are shown immediately when a valid token exists.
    () => getAccessToken() !== null,
  );
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

  const { ready: duckdbReady, error: duckdbError, extensionsLoaded, executeQuery, getConnection } = useDuckDB(wasmAppUrl);
  const { ready: pyodideReady, error: pyodideError, translate } = usePyodide();

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
    } else if (duckdbReady && pyodideReady) {
      setStatusMessage(extensionsLoaded ? "Ready — C++ UDFs active" : "Ready — SQL macro fallback");
      setIsStatusError(false);
    } else if (!duckdbReady || !pyodideReady) {
      setStatusMessage("Loading engines…");
    }
  }, [duckdbError, pyodideError, duckdbReady, pyodideReady, extensionsLoaded]);

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

  const allReady = duckdbReady && pyodideReady;

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
        </div>
      )}

      {activeTab === "playground" && config.visibleTabs.includes("playground") && (
        <div className="app">
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
                content: <CQLEditor value={cqlText} onChange={setCqlText} />,
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
          <StatusBar
            metrics={metrics}
            message={statusMessage}
            isError={isStatusError}
          />
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
    </div>
  );
}
