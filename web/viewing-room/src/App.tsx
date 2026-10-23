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
import { DEFAULT_SAMPLE, Sample, SAMPLES, parseResourcesInput, resourceStats, sampleUrl } from "./lib/samples";
import { ResultsTable } from "./components/ResultsTable";
import { DiagnosticsList } from "./components/DiagnosticsList";
import { SqlView } from "./components/SqlView";
import { ResourceDataViewer } from "./components/ResourceDataViewer";

type OutputTab = "table" | "sql" | "diagnostics";
type ResourcesTab = "editor" | "browse";

interface RunState {
  running: boolean;
  columns: string[];
  rows: Array<Record<string, unknown>>;
  sql: string | null;
  diagnostics: Array<{ code: string; severity?: string; message: string }> | null;
  ranAt: number | null;
  parsedResources: Array<Record<string, unknown>> | null;
}

const EMPTY_RUN: RunState = {
  running: false,
  columns: [],
  rows: [],
  sql: null,
  diagnostics: null,
  ranAt: null,
  parsedResources: null,
};

export default function App() {
  const [bootStatus, setBootStatus] = useState<BootStatus>({ phase: "idle" });
  const [resourcesText, setResourcesText] = useState("// loading sample…");
  const [vdText, setVdText] = useState("");
  const [sample, setSample] = useState<Sample | null>(null);
  const [run, setRun] = useState<RunState>(EMPTY_RUN);
  const [outputTab, setOutputTab] = useState<OutputTab>("table");
  const [resourcesTab, setResourcesTab] = useState<ResourcesTab>("editor");
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

  // The last LOADED sample content (dirty-guard baseline).
  const loadedRef = useRef<{ vd: string; res: string }>({ vd: "", res: "" });

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
    loadedRef.current = { vd: vdText, res: resText };
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
      parsedResources: parsed.resources,
    });
    setOutputTab(env.ok ? "table" : "diagnostics");
  }, []);

  const doRunRef = useRef<((vd?: string, res?: string) => void) | null>(null);
  doRunRef.current = (vd?, res?) => void doRun(vd, res);

  // AUTO-RECALC (Joel, S5): debounced auto-run on editor changes once the
  // engine is ready AND at least one run has happened (i.e. after the initial
  // sample auto-run). Rapid edits collapse to the latest text; the single
  // worker serializes runs naturally (postMessage queue) and the S3
  // staging-race fix made table reuse safe.
  const autoRunArmed = useRef(false);
  const engineReadyRef = useRef(false);
  engineReadyRef.current = bootStatus.phase === "ready";
  useEffect(() => {
    if (!engineReadyRef.current || !run.ranAt) return;
    autoRunArmed.current = true;
  }, [bootStatus.phase, run.ranAt]);
  useEffect(() => {
    if (!autoRunArmed.current) return;
    if (!engineReadyRef.current) return;
    const t = window.setTimeout(() => void doRun(), 800);
    return () => window.clearTimeout(t);
    // vdText/resourcesText intentionally read via closure; doRun reads refs.
  }, [vdText, resourcesText, bootStatus.phase]);

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

  // Stale badge (S5): editors changed since the last completed run.
  const lastRunText = useRef<{ vd: string; res: string }>({ vd: "", res: "" });
  useEffect(() => {
    if (run.ranAt) lastRunText.current = { vd: vdText, res: resourcesText };
  }, [run.ranAt]); // eslint-disable-line react-hooks/exhaustive-deps
  const autoStale =
    autoRunArmed.current && run.ranAt !== null &&
    (vdText !== lastRunText.current.vd || resourcesText !== lastRunText.current.res);

  // Resource stats (design §4: resource stats on the pane header) —
  // derived from the last PARSED editor content (shown after a run).
  const stats = resourceStats(run.parsedResources ?? []);
  const resourceStatsText = stats.total
    ? `${stats.total} resource${stats.total === 1 ? "" : "s"}: ${stats.byType.map((t) => `${t.count} ${t.type}`).join(", ")}`
    : "";

  // Dirty guard (Muse rec): switching samples with edited content asks first.
  const dirty = resourcesText !== loadedRef.current.res || vdText !== loadedRef.current.vd;

  const selectSample = useCallback(
    (s: Sample) => {
      if (dirty && !window.confirm("Editors have unsaved edits — load sample anyway?")) return;
      void loadSample(s).then((t) => doRunRef.current?.(t.vd, t.res));
    },
    [dirty, loadSample],
  );

  // Splitter (Muse rec): pointer-drag + keyboard resizing between panes.
  const [splitPct, setSplitPct] = useState(40);
  const mainRef = useRef<HTMLDivElement | null>(null);
  const onSplitterKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowLeft") setSplitPct((p) => Math.max(15, p - 3));
    else if (e.key === "ArrowRight") setSplitPct((p) => Math.min(85, p + 3));
    else return;
    e.preventDefault();
  };
  const onSplitterPointerDown = (e: React.PointerEvent) => {
    e.preventDefault();
    const el = mainRef.current;
    if (!el) return;
    const move = (ev: PointerEvent) => {
      const rect = el.getBoundingClientRect();
      const pct = ((ev.clientX - rect.left) / rect.width) * 100;
      setSplitPct(Math.min(85, Math.max(15, pct)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div className="app">
      <header className="header">
        <h1>SQL-on-FHIR Viewing Room</h1>
        <span className="tagline">live imaging for SQL-on-FHIR views</span>
        <div className="header-spacer" />
        <select
          aria-label="Load a sample"
          title="Load a sample"
          value={sample?.slug ?? ""}
          onChange={(e) => {
            const s = SAMPLES.find((x) => x.slug === e.target.value);
            if (s) selectSample(s);
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
          {run.running ? "Running…" : autoStale ? "Run view (stale)" : "Run view"}
          <span className="run-kbd">⌘⏎</span>
        </button>
      </header>

      <div className="main" ref={mainRef}>
        <section className="pane pane-resources" aria-label="FHIR resources" style={{ flex: `${splitPct} 1 0%` }}>
          <div className="pane-header">
            FHIR Resources
            {run.ranAt && <span className="pane-stats" data-testid="resource-stats">{resourceStatsText}</span>}
          </div>
          <div className="resources-tabs tab-strip" role="tablist" aria-label="Resources pane views">
            <button
              id="vr-res-tab-editor"
              role="tab"
              aria-selected={resourcesTab === "editor"}
              className={resourcesTab === "editor" ? "active" : ""}
              onClick={() => setResourcesTab("editor")}
            >
              Editor
            </button>
            <button
              id="vr-res-tab-browse"
              role="tab"
              aria-selected={resourcesTab === "browse"}
              className={resourcesTab === "browse" ? "active" : ""}
              onClick={() => setResourcesTab("browse")}
            >
              Browse
            </button>
          </div>
          <div className="pane-body">
            {resourcesTab === "editor" ? (
              <div className="editor-container" data-testid="resources-editor">
                <Editor
                  language="json"
                  value={resourcesText}
                  onChange={(v) => setResourcesText(v ?? "")}
                  onMount={(editor) => {
                    (window as any).__vrResourcesEditor = editor;
                  }}
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
            ) : (
              <ResourceDataViewer
                resources={run.parsedResources ?? []}
                highlightTypes={vdResourceOf(vdText) ? [vdResourceOf(vdText)!] : null}
              />
            )}
          </div>
        </section>

        <div
          className="splitter"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize panes (arrow keys)"
          tabIndex={0}
          onKeyDown={onSplitterKeyDown}
          onPointerDown={onSplitterPointerDown}
        />
        <section className="pane pane-viewdef" aria-label="ViewDefinition" style={{ flex: `${100 - splitPct} 1 0%` }}>
          <div className="pane-header">ViewDefinition</div>
          <div className="pane-body">
            <div className="editor-container" style={{ flex: "0 0 38%" }} data-testid="vd-editor">
              <Editor
                language="json"
                value={vdText}
                onChange={(v) => setVdText(v ?? "")}
                onMount={(editor) => {
                  (window as any).__vrVdEditor = editor;
                }}
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
              <div
                className="tab-strip"
                role="tablist"
                aria-label="Output views"
                onKeyDown={(e) => {
                  const order: OutputTab[] = ["table", "sql", "diagnostics"];
                  const i = order.indexOf(outputTab);
                  if (e.key === "ArrowRight") setOutputTab(order[(i + 1) % order.length]);
                  else if (e.key === "ArrowLeft") setOutputTab(order[(i + order.length - 1) % order.length]);
                  else return;
                  e.preventDefault();
                }}
              >
                <button id="vr-tab-table" role="tab" aria-controls="vr-panel-table" aria-selected={outputTab === "table"} className={outputTab === "table" ? "active" : ""} onClick={() => setOutputTab("table")}>
                  Output table
                </button>
                <button id="vr-tab-sql" role="tab" aria-controls="vr-panel-sql" aria-selected={outputTab === "sql"} className={outputTab === "sql" ? "active" : ""} onClick={() => setOutputTab("sql")}>
                  SQL
                </button>
                <button id="vr-tab-diagnostics" role="tab" aria-controls="vr-panel-diagnostics" aria-selected={outputTab === "diagnostics"} className={outputTab === "diagnostics" ? "active" : ""} onClick={() => setOutputTab("diagnostics")}>
                  Diagnostics{run.diagnostics ? ` (${run.diagnostics.length})` : ""}
                </button>
              </div>
              <div className="output-body">
                <div className="tab-panel" id="vr-panel-table" role="tabpanel" aria-labelledby="vr-tab-table" hidden={outputTab !== "table"}>
                  <ResultsTable columns={run.columns} rows={run.rows} ranAt={run.ranAt} vdResource={vdResourceOf(vdText)} loadedTypes={stats.byType.map((t) => t.type).join(", ")} />
                </div>
                <div className="tab-panel" id="vr-panel-sql" role="tabpanel" aria-labelledby="vr-tab-sql" hidden={outputTab !== "sql"}>
                  <SqlView sql={run.sql} />
                </div>
                <div className="tab-panel" id="vr-panel-diagnostics" role="tabpanel" aria-labelledby="vr-tab-diagnostics" hidden={outputTab !== "diagnostics"}>
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
