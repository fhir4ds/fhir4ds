/**
 * App: SQL-on-FHIR Viewing Room.
 *
 * Two-pane layout (design §4): left = FHIR RESOURCES (Editor|Browse tabs),
 * right = VIEWDEFINITION editor + output tabs (OUTPUT TABLE / SQL /
 * DIAGNOSTICS). Run button + Cmd/Ctrl+Enter; auto-run on sample load only.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { BootStatus, flattenView, onBootStatus } from "./lib/engineClient";
import { boot as bootEngine } from "./lib/engineClient";
import { DEFAULT_SAMPLE, Sample, SAMPLES, parseResourcesInput, sampleUrl } from "./lib/samples";
import { ResultsTable } from "./components/ResultsTable";
import { DiagnosticsList } from "./components/DiagnosticsList";
import { SqlView } from "./components/SqlView";

type OutputTab = "table" | "sql" | "diagnostics";

interface RunState {
  running: boolean;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  sql: string | null;
  diagnostics: Array<{ code: string; severity?: string; message: string }> | null;
  ranAt: number | null;
}

const EMPTY_RUN: RunState = {
  running: false,
  columns: [],
  rows: [],
  sql: null,
  diagnostics: null,
  ranAt: null,
};

export default function App() {
  const [bootStatus, setBootStatus] = useState<BootStatus>({ phase: "idle" });
  const [resourcesText, setResourcesText] = useState("// loading sample…");
  const [vdText, setVdText] = useState("");
  const [sample, setSample] = useState<Sample | null>(null);
  const [run, setRun] = useState<RunState>(EMPTY_RUN);
  const [outputTab, setOutputTab] = useState<OutputTab>("table");
  const vdRef = useRef<string>("");
  vdRef.current = vdText;
  const resRef = useRef<string>("");
  resRef.current = resourcesText;

  useEffect(() => onBootStatus(setBootStatus), []);

  // Boot the engine immediately on mount.
  useEffect(() => {
    void bootEngine().catch(() => {
      /* boot failures surface via bootStatus */
    });
  }, []);

  const loadSample = useCallback(async (s: Sample): Promise<{ vd: string; res: string }> => {
    setSample(s);
    const [vd, res] = await Promise.all([
      fetch(sampleUrl(s.vdUrl)).then((r) => {
        if (!r.ok) throw new Error(`sample VD fetch failed: ${s.vdUrl}`);
        return r.text();
      }),
      fetch(sampleUrl(s.resourcesUrl)).then((r) => {
        if (!r.ok) throw new Error(`sample resources fetch failed: ${s.resourcesUrl}`);
        return r.text();
      }),
    ]);
    const vdText = vd.trimEnd() + "\n";
    const resText = res.trimEnd() + "\n";
    setVdText(vdText);
    setResourcesText(resText);
    return { vd: vdText, res: resText };
  }, []);

  // Auto-load the default sample once (auto-run on sample load only).
  const defaultLoaded = useRef(false);
  useEffect(() => {
    if (defaultLoaded.current) return;
    defaultLoaded.current = true;
    loadSample(DEFAULT_SAMPLE)
      // Pass the loaded text EXPLICITLY: refs update on render, and the
      // post-promise microtask can run before React commits the new state.
      .then((t) => void doRunRef.current?.(t.vd, t.res))
      .catch((e) => console.error("sample load failed", e));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const doRun = useCallback(async (vdOverride?: string, resOverride?: string) => {
    const vdTextNow = vdOverride ?? vdRef.current;
    const resTextNow = resOverride ?? resRef.current;
    setRun((r) => ({ ...r, running: true }));
    let vd: Record<string, unknown>;
    try {
      vd = JSON.parse(vdTextNow);
    } catch (e) {
      setRun({
        ...EMPTY_RUN,
        diagnostics: [{ code: "vd_json_error", message: `ViewDefinition is not valid JSON: ${(e as Error).message}` }],
      });
      setOutputTab("diagnostics");
      return;
    }
    const parsed = parseResourcesInput(resTextNow);
    if (parsed.error) {
      setRun({
        ...EMPTY_RUN,
        diagnostics: [{ code: "resources_parse_error", message: parsed.error }],
      });
      setOutputTab("diagnostics");
      return;
    }
    const env = await flattenView(vd, parsed.resources);
    setRun({
      running: false,
      columns: env.ok ? (env.columns ?? []) : [],
      rows: env.ok ? (env.rows ?? []) : [],
      sql: env.sql ?? null,
      diagnostics: env.ok ? null : (env.diagnostics ?? []),
      ranAt: Date.now(),
    });
    setOutputTab(env.ok ? "table" : "diagnostics");
  }, []);

  const doRunRef = useRef<((vd?: string, res?: string) => void) | null>(null);
  doRunRef.current = (vd?, res?) => void doRun(vd, res);

  // Cmd/Ctrl+Enter runs.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void doRun();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [doRun]);

  const engineReady = bootStatus.phase === "ready";

  return (
    <div className="app">
      <header className="header">
        <h1>SQL-on-FHIR Viewing Room</h1>
        <span className="tagline">live imaging for SQL-on-FHIR views</span>
        <div className="header-spacer" />
        <select
          title="Load a sample"
          value={sample?.slug ?? ""}
          onChange={(e) => {
            const s = SAMPLES.find((x) => x.slug === e.target.value);
            if (s) void loadSample(s).then((t) => doRunRef.current?.(t.vd, t.res));
          }}
        >
          {!sample && <option value="" disabled>Load a sample…</option>}
          {SAMPLES.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.name}
            </option>
          ))}
        </select>
        {bootStatus.phase === "ready" ? (
          <span className="version-badge" data-testid="version-badge">
            fhir4ds {bootStatus.wheelVersion}
          </span>
        ) : bootStatus.phase === "error" ? (
          <span className="boot-status error" title={bootStatus.error}>
            engine boot failed
          </span>
        ) : (
          <span className="boot-status">
            {bootStatus.phase === "booting" ? "booting engine…" : "starting…"}
          </span>
        )}
        <button className="run-button" onClick={() => void doRun()} disabled={!engineReady || run.running}>
          {run.running ? "Running…" : "Run view"}
          <span className="run-kbd">⌘⏎</span>
        </button>
      </header>

      <div className="main">
        <section className="pane pane-resources" aria-label="FHIR resources">
          <div className="pane-header">FHIR Resources</div>
          <div className="pane-body">
            <Editor
              className="editor-container"
              language="json"
              value={resourcesText}
              onChange={(v) => setResourcesText(v ?? "")}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 12,
                wordWrap: "on",
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
          </div>
        </section>

        <section className="pane pane-viewdef" aria-label="ViewDefinition">
          <div className="pane-header">ViewDefinition</div>
          <div className="pane-body">
            <div className="editor-container" style={{ flex: "0 0 38%" }}>
            <Editor
              className="editor-container"
              language="json"
              value={vdText}
              onChange={(v) => setVdText(v ?? "")}
              theme="vs-dark"
              options={{
                minimap: { enabled: false },
                fontSize: 12,
                wordWrap: "on",
                scrollBeyondLastLine: false,
                automaticLayout: true,
              }}
            />
            </div>
            <div className="output-tabs" style={{ flex: "1 1 62%" }}>
              <div className="tab-strip" role="tablist">
                <button role="tab" aria-selected={outputTab === "table"} className={outputTab === "table" ? "active" : ""} onClick={() => setOutputTab("table")}>
                  Output table
                </button>
                <button role="tab" aria-selected={outputTab === "sql"} className={outputTab === "sql" ? "active" : ""} onClick={() => setOutputTab("sql")}>
                  SQL
                </button>
                <button role="tab" aria-selected={outputTab === "diagnostics"} className={outputTab === "diagnostics" ? "active" : ""} onClick={() => setOutputTab("diagnostics")}>
                  Diagnostics{run.diagnostics ? ` (${run.diagnostics.length})` : ""}
                </button>
              </div>
              <div className="output-body">
                <div className="tab-panel" role="tabpanel" hidden={outputTab !== "table"}>
                  <ResultsTable columns={run.columns} rows={run.rows} ranAt={run.ranAt} vdResource={vdResourceOf(vdText)} />
                </div>
                <div className="tab-panel" role="tabpanel" hidden={outputTab !== "sql"}>
                  <SqlView sql={run.sql} />
                </div>
                <div className="tab-panel" role="tabpanel" hidden={outputTab !== "diagnostics"}>
                  <DiagnosticsList diagnostics={run.diagnostics ?? []} />
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>

      {!engineReady && bootStatus.phase !== "error" && (
        <div className="boot-overlay" data-testid="boot-overlay">
          <div className="spinner" />
          <div className="boot-message">
            Initializing in-browser SQL-on-FHIR engine (Pyodide + DuckDB-WASM)…
          </div>
        </div>
      )}
      {bootStatus.phase === "error" && (
        <div className="boot-overlay" data-testid="boot-overlay">
          <div className="boot-error">
            Engine boot failed: {bootStatus.error}
          </div>
          <button className="run-button" onClick={() => void bootEngine()}>
            Retry boot
          </button>
        </div>
      )}
    </div>
  );
}

function vdResourceOf(vdText: string): string | null {
  try {
    const vd = JSON.parse(vdText);
    return typeof vd?.resource === "string" ? vd.resource : null;
  } catch {
    return null;
  }
}
