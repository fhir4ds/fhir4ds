import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { SQLOutput } from "@wasm-demo/components/SQLOutput";
import { ResultsTable } from "@wasm-demo/components/ResultsTable";
import type { QueryResult } from "@wasm-demo/components/ResultsTable";
import { HttpTransport } from "./http-transport";
import {
  appendBox,
  defineDevTheme,
  markerLineEnd,
  renameDefine,
  renameLabel,
  spliceBox,
  splitBoxes,
} from "./boxes";
import type { Box } from "./boxes";
import type {
  CellEvent,
  Diagnostic,
  EvaluateResult,
  HealthInfo,
  RunMode,
  WorkspaceEvent,
  WorkspaceInfo,
} from "./transport";
import { ValueSetPane } from "./ValueSetPane";
import { ParamsPane } from "./ParamsPane";
import { TestsPane } from "./TestsPane";
import { MeasurePane } from "./MeasurePane";
import { VdPane } from "./VdPane";
import { DatasetPane } from "./DatasetPane";
import { ResourceBuilderPane } from "./ResourceBuilderPane";

type Tab = "results" | "sql" | "errors";

export function App() {
  const transport = useMemo(() => new HttpTransport(""), []);
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceInfo | null>(null);
  const [selected, setSelected] = useState<string>("");
  const [buffer, setBuffer] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [evaluate, setEvaluate] = useState<EvaluateResult | null>(null);
  const [sql, setSql] = useState("");
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [tab, setTab] = useState<Tab>("results");
  const [busy, setBusy] = useState(false);
  const [dataHint, setDataHint] = useState<string[]>([]);
  const [runMode, setRunMode] = useState<RunMode>("cell");
  const [cellStates, setCellStates] = useState<Record<string, string>>({});
  const [cellRows, setCellRows] = useState<Record<string, Record<string, unknown>[]>>({});
  const [cellErrors, setCellErrors] = useState<Record<string, string>>({});
  const [resultHeader, setResultHeader] = useState("");
  const [lastRun, setLastRun] = useState<{ cell: string; time: string } | null>(null);
  const [cellFullRows, setCellFullRows] = useState<
    Record<string, Record<string, unknown>[]>
  >({});
  const lastFocusedCell = useRef<string>("");
  // ux3: boxes projection + index + kernel status + dataset detail.
  const [editingTitle, setEditingTitle] = useState<{ box: Box; value: string } | null>(null);
  const [indexOpen, setIndexOpen] = useState(false);
  const [kernelBusy, setKernelBusy] = useState<"idle" | "busy" | "restarting">("idle");
  const [datasetStats, setDatasetStats] = useState<{ total: number; by_type: Record<string, number> } | null>(null);
  // v3: resource panes + dataset context. The left rail lists ALL resource
  // types; railView picks what the center column shows (null = cell boxes).
  const [railView, setRailView] = useState<
    | { kind: "valueset"; id: string }
    | { kind: "params"; id: string }
    | { kind: "measure"; id: string }
    | { kind: "view"; id: string }
    | { kind: "dataset"; id: string }
    | { kind: "builder" }
    | null
  >(null);
  const [builderPrefill, setBuilderPrefill] = useState<{
    resource: Record<string, unknown>;
    datasetPath: string;
  } | null>(null);
  const [vsStale, setVsStale] = useState(false);
  const [patients, setPatients] = useState<string[]>([]);
  // v4.3: last measure run's MeasureReports for the VD pane's
  // run-against-measure-output toggle.
  const [lastMeasureReports, setLastMeasureReports] = useState<Record<string, unknown>[] | null>(null);

  const boxes = useMemo(() => splitBoxes(buffer), [buffer]);
  const defineBoxes = useMemo(() => boxes.filter((b) => b.kind === "define"), [boxes]);

  const loadLibrary = useCallback(
    async (name: string) => {
      setSelected(name);
      setRailView(null);
      const r = await transport.library(name);
      setBuffer((r as unknown as { text?: string }).text ?? "");
      setDirty(false);
    },
    [transport],
  );

  const selectValueset = useCallback((path: string) => {
    // Keep `selected` intact — the workspace-load effect re-selects the
    // first library otherwise and discards the valueset view. The center
    // column branches on railView first, and loadLibrary resets it.
    setRailView({ kind: "valueset", id: path });
  }, []);

  const refreshWorkspace = useCallback(async () => {
    const w = await transport.workspace();
    setWorkspace(w);
    if (w.libraries.length && !w.libraries.find((l) => l.name === selected)) {
      await loadLibrary(w.libraries[0].name);
    }
  }, [transport, selected, loadLibrary]);

  useEffect(() => {
    transport.health().then(setHealth).catch(() => {});
    refreshWorkspace().catch(() => {});
    const off = transport.onWorkspaceEvent((e: WorkspaceEvent) => {
      if (e.kind === "changed" && e.workspace) setWorkspace(e.workspace);
      if (e.kind === "data-hint") setDataHint(e.paths);
      // Staleness can originate from ANY edit source (API, another tab),
      // not just this page's ValueSet pane.
      if (e.kind === "stale") setVsStale(Boolean(e.valuesets_stale));
    });
    const offCells = transport.onCellEvent((e: CellEvent) => {
      if (e.kind === "cellstate" && e.states) {
        setCellStates((prev) => ({ ...prev, ...e.states! }));
      } else if (e.kind === "result" && e.per_cell) {
        const rows: Record<string, Record<string, unknown>[]> = {};
        for (const [name, slice] of Object.entries(e.per_cell)) {
          rows[name] = slice.rows ?? [];
        }
        setCellRows((prev) => ({ ...prev, ...rows }));
        if (e.cell && e.rows) {
          setCellFullRows((prev) => ({ ...prev, [e.cell!]: e.rows! }));
        }
        setCellStates((prev) => {
          const next = { ...prev };
          for (const n of e.cells ?? []) next[n] = "ok";
          return next;
        });
        setCellErrors((prev) => {
          const next = { ...prev };
          for (const n of e.cells ?? []) delete next[n];
          return next;
        });
        const cell = e.cell ?? "";
        const slice = e.per_cell[cell];
        if (slice) {
          const timing = Object.values(e.timing_ms ?? {}).reduce((a, b) => a + b, 0);
          setResult({
            columns: [cell],
            rows: (slice.rows ?? []).map((row) => [String(row[cell])]),
            rowCount: slice.rows?.length ?? 0,
            executionTimeMs: timing,
          });
          setResultHeader(`${cell} - ${slice.rows?.length ?? 0} rows - ${timing}ms`);
          setSql(e.sql ?? "");
          setTab("results");
        }
        setLastRun({ cell, time: new Date().toLocaleTimeString() });
      } else if (e.kind === "cellerror") {
        const message =
          e.diagnostics?.[0]?.message ?? "evaluation failed";
        setCellErrors((prev) => {
          const next = { ...prev };
          for (const n of e.cells ?? []) next[n] = message;
          return next;
        });
        setCellStates((prev) => {
          const next = { ...prev };
          for (const n of e.cells ?? []) next[n] = "error";
          return next;
        });
      } else if (e.kind === "runerror") {
        setCellErrors((prev) => ({ ...prev, [e.cell ?? "?"]: e.message ?? "run failed" }));
      }
    });
    return () => {
      off();
      offCells();
    };
  }, [transport, refreshWorkspace]);

  const apply = useCallback(
    async (mode: "translate" | "evaluate") => {
      if (!selected) return;
      setBusy(true);
      try {
        const libraries = [{ name: selected, text: buffer }];
        if (mode === "translate") {
          const r = await transport.translate(libraries, selected);
          setSql(r.sql ?? "");
          setDiagnostics(r.diagnostics ?? []);
          setTab(r.ok ? "sql" : "errors");
        } else {
          const r = await transport.evaluate(libraries, selected);
          setEvaluate(r);
          setSql(r.sql ?? "");
          setDiagnostics(r.diagnostics ?? []);
          if (r.ok) {
            setResult({
              columns: r.columns,
              rows: r.rows.map((row) => r.columns.map((c) => row[c])),
              rowCount: r.rows.length,
              executionTimeMs:
                Object.values(r.timing_ms ?? {}).reduce((a, b) => a + b, 0) || 0,
            });
            setTab("results");
          } else {
            setTab("errors");
          }
        }
        setDirty(false);
      } finally {
        setBusy(false);
      }
    },
    [buffer, selected, transport],
  );

  const restartKernel = useCallback(async () => {
    setKernelBusy("restarting");
    try {
      const h = await transport.restartKernel();
      setHealth(h);
    } finally {
      setKernelBusy("idle");
    }
    setVsStale(false);
    setDataHint([]);
    setCellStates((prev) => {
      const next: Record<string, string> = {};
      for (const [k, v] of Object.entries(prev)) {
        next[k] = v === "ok" || v === "error" ? "stale" : v;
      }
      return next;
    });
  }, [transport]);

  const runCell = useCallback(
    (name: string, mode: RunMode = runMode) => {
      if (!selected) return;
      transport.syncCells(selected, buffer);
      transport.runCell(selected, name, mode, buffer);
    },
    [buffer, runMode, selected, transport],
  );
  const runCellRef = useRef(runCell);
  runCellRef.current = runCell;

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if ((ev.metaKey || ev.ctrlKey) && ev.key === "Enter") {
        ev.preventDefault();
        if (lastFocusedCell.current) runCellRef.current(lastFocusedCell.current);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const anyCellOk = useMemo(
    () => Object.values(cellStates).some((s) => s === "ok"),
    [cellStates],
  );
  useEffect(() => {
    setKernelBusy(
      Object.values(cellStates).some((s) => s === "running") ? "busy" : "idle",
    );
  }, [cellStates]);

  const commitTitle = useCallback(() => {
    if (!editingTitle) return;
    const { box, value } = editingTitle;
    const t = value.trim();
    if (t && /^[A-Za-z][A-Za-z0-9_]*$/.test(t)) {
      if (box.title_source === "label") {
        setBuffer((b) => renameLabel(b, box, t));
        setDirty(true);
      } else if (box.title_source === "define" && box.name) {
        setBuffer((b) => renameDefine(b, box.name!, t));
        setDirty(true);
      }
    }
    setEditingTitle(null);
  }, [editingTitle]);

  // Normalize /api/dataset-stats payloads: the API emits by_type as an
  // ARRAY of {resourceType, count}; map it to a Record for rendering.
  const normalizeStats = (d: {
    total: number;
    by_type: Array<{ resourceType: string; count: number }> | Record<string, number>;
  }): { total: number; by_type: Record<string, number> } => ({
    total: d.total,
    by_type: Array.isArray(d.by_type)
      ? Object.fromEntries(d.by_type.map((s) => [s.resourceType, s.count]))
      : d.by_type,
  });

  // v3: dataset context — load stats once so the results header can echo
  // dataset + patient count alongside the kernel id.
  useEffect(() => {
    fetch("/api/dataset-stats")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d) setDatasetStats(normalizeStats(d));
      })
      .catch(() => {});
  }, [health?.kernel_id]);

  // Patients list lives at App level: it survives TestsPane remounts
  // (workspace refreshes can flip the selected library and unmount panes).
  useEffect(() => {
    if (!health?.kernel_id) return;
    let cancelled = false;
    const attempt = async (tries: number) => {
      try {
        const ps = await transport.patients();
        if (!cancelled && ps.length > 0) setPatients(ps);
        else if (!cancelled && tries > 0)
          setTimeout(() => attempt(tries - 1).catch(() => {}), 1500);
      } catch {
        if (!cancelled && tries > 0)
          setTimeout(() => attempt(tries - 1).catch(() => {}), 1500);
      }
    };
    attempt(5).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [health?.kernel_id, transport]);

  const jumpToBox = useCallback((title: string) => {
    document
      .querySelector(`[data-box="${title}"]`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, []);

  const boxBody = (box: Box): string =>
    box.kind === "header"
      ? buffer.slice(box.start, box.end)
      : buffer.slice(markerLineEnd(buffer, box), box.end);

  const renameable = (box: Box) =>
    box.title_source === "label" || box.title_source === "define";

  return (
    <div className="dev-app">
      <header className="dev-header">
        <h1>FHIR4DS CQL Cleanroom</h1>
        <span className={"dev-kerneldot " + kernelBusy} title={`kernel ${kernelBusy}`} />
        <span className="dev-status">
          {health ? `${health.kernel_id} · ${health.watching} files` : "…"}
        </span>
        {lastRun && (
          <span className="dev-lastrun">
            Last run: {lastRun.cell} · {lastRun.time}
          </span>
        )}
        {dataHint.length > 0 && (
          <span className="dev-hint">
            data changed ({dataHint.length}) —{" "}
            <button onClick={restartKernel}>restart kernel</button>
          </span>
        )}
        <button onClick={restartKernel} title="Fresh DB from data dirs">
          Restart kernel
        </button>
      </header>
      <main className="dev-main">
        <aside className="dev-libraries">
          <h2>Libraries</h2>
          {(workspace?.libraries ?? []).map((lib) => (
            <div
              key={lib.name}
              className={
                "dev-lib" + (lib.name === selected ? " selected" : "") +
                (lib.parse_ok ? "" : " broken")
              }
              onClick={() => loadLibrary(lib.name)}
            >
              {lib.name}
              {!lib.parse_ok && <em title={lib.error ?? ""}> ⚠</em>}
            </div>
          ))}
          {workspace?.datasets.length ? <h2>Data</h2> : null}
          {(workspace?.datasets ?? []).map((d) => (
            <div
              key={d}
              className={
                "dev-lib small dev-dataset" +
                (railView?.kind === "dataset" && railView.id === d ? " selected" : "")
              }
              title={d}
              onClick={() => setRailView({ kind: "dataset", id: d })}
            >
              {d.split("/").pop()}
            </div>
          ))}
          {(workspace?.valuesets ?? []).length > 0 && <h2>ValueSets</h2>}
          {(workspace?.valuesets ?? []).map((v) => (
            <div
              key={v}
              className={
                "dev-lib small" + (railView?.kind === "valueset" && railView.id === v ? " selected" : "")
              }
              title={v}
              onClick={() => selectValueset(v)}
            >
              {v.split("/").pop()?.replace(/\.json$/, "")}
            </div>
          ))}
          {(workspace?.libraries ?? []).length > 0 && <h2>Parameters</h2>}
          {(workspace?.libraries ?? []).map((lib) => (
            <div
              key={lib.name}
              className={
                "dev-lib small" + (railView?.kind === "params" && railView.id === lib.name ? " selected" : "")
              }
              title={`Parameters for ${lib.name}`}
              onClick={async () => {
                if (selected !== lib.name) await loadLibrary(lib.name);
                setRailView({ kind: "params", id: lib.name });
              }}
            >
              {lib.name} · parameters
            </div>
          ))}
          <h2>Measures</h2>
          {(workspace?.measures ?? []).map((m) => (
            <div
              key={m}
              className={
                "dev-lib small" + (railView?.kind === "measure" && railView.id === m ? " selected" : "")
              }
              title={m}
              onClick={() => setRailView({ kind: "measure", id: m })}
            >
              {m.split("/").pop()?.replace(/\.json$/, "")}
            </div>
          ))}
          {(workspace?.libraries ?? []).map((lib) => (
            <div
              key={lib.name + "-scaffold"}
              className={
                "dev-lib small" +
                (railView?.kind === "measure" && railView.id === lib.name + "-scaffold" ? " selected" : "")
              }
              title={`Scaffold a Measure from ${lib.name} defines (preview + run)`}
              onClick={async () => {
                if (selected !== lib.name) await loadLibrary(lib.name);
                setRailView({ kind: "measure", id: lib.name + "-scaffold" });
              }}
            >
              + {lib.name} scaffold
            </div>
          ))}
          <h2>ViewDefinitions</h2>
          {(workspace?.views ?? []).map((v) => (
            <div
              key={v}
              className={
                "dev-lib small" + (railView?.kind === "view" && railView.id === v ? " selected" : "")
              }
              title={v}
              onClick={() => setRailView({ kind: "view", id: v })}
            >
              {v.split("/").pop()?.replace(/\.json$/, "")}
            </div>
          ))}
          <h2>Build</h2>
          <div
            className={
              "dev-lib small" + (railView?.kind === "builder" ? " selected" : "")
            }
            title="Form/JSON hybrid resource builder with schema-tree guidance and validate_resource gating"
            onClick={() => {
              setBuilderPrefill(null);
              setRailView({ kind: "builder" });
            }}
          >
            + Resource
          </div>
        </aside>
        <section className="dev-editor">
          {railView?.kind === "valueset" ? (
            <ValueSetPane
              transport={transport}
              path={railView.id}
              onStaleChange={setVsStale}
              onInsertDeclaration={(decl) => {
                // Splice the valueset declaration into the open library's
                // header box (in-memory buffer + dirty; Apply persists).
                if (!selected) return;
                const header = boxes.find((b) => b.kind === "header");
                if (!header) return;
                const body = boxBody(header);
                setBuffer((b) =>
                  spliceBox(b, header, (body.endsWith("\n") ? body : body + "\n") + decl + "\n", true),
                );
                setDirty(true);
              }}
            />
          ) : railView?.kind === "params" ? (
            <div className="dev-panewrap">
              <div className="dev-toolbar">
                <span className="dev-pane-label">Parameters</span>
                <span>{railView.id}</span>
                <span className="dev-pane-hint">edits apply to the library header box</span>
              </div>
              <ParamsPane
                transport={transport}
                library={railView.id}
                onText={(text) => {
                  setBuffer(text);
                  setDirty(true);
                }}
              />
            </div>
          ) : railView?.kind === "measure" ? (
            <div className="dev-panewrap">
              <div className="dev-toolbar">
                <span className="dev-pane-label">Measure</span>
                <span>{railView.id}</span>
              </div>
              <MeasurePane
                transport={transport}
                library={selected}
                buffer={buffer}
                definitions={
                  workspace?.libraries.find((l) => l.name === selected)
                    ?.definitions ?? []
                }
                onMeasureReports={setLastMeasureReports}
              />
            </div>
          ) : railView?.kind === "dataset" ? (
            <DatasetPane
              transport={transport}
              path={railView.id}
              datasetName={railView.id.split("/").pop() ?? railView.id}
              onEditInBuilder={(resource, datasetPath) => {
                setBuilderPrefill({ resource, datasetPath });
                setRailView({ kind: "builder" });
              }}
            />
          ) : railView?.kind === "view" ? (
            <VdPane
              transport={transport}
              path={railView.id}
              datasetName={
                (workspace?.datasets ?? [])[0]?.split("/").pop()?.replace(/\.ndjson$/, "") ?? ""
              }
              patientCount={datasetStats?.total ?? null}
              lastMeasureReports={lastMeasureReports}
            />
          ) : railView?.kind === "builder" ? (
            <ResourceBuilderPane
              transport={transport}
              datasets={workspace?.datasets ?? []}
              dataHint={dataHint.length > 0 ? `data changed (${dataHint.length}) — restart kernel to load` : null}
              initialResource={builderPrefill?.resource ?? null}
              initialDatasetPath={builderPrefill?.datasetPath ?? null}
            />
          ) : (
            <>
          <div className="dev-toolbar">
            <span className="dev-pane-label">Editor</span>
            <span>{selected}{dirty ? " *" : ""}</span>
            <select
              value={runMode}
              onChange={(e) => setRunMode(e.target.value as RunMode)}
              title="Cell run mode"
            >
              <option value="cell">cell (+ deps)</option>
              <option value="cell_deps">cell + deps</option>
              <option value="cell_only">cell only</option>
              <option value="all">all</option>
              <option value="to_here">to here</option>
            </select>
            <button
              onClick={() => {
                setBuffer((b) => appendBox(b));
                setDirty(true);
              }}
              title={"Inserts:\n// # %%\ndefine NewCell: 'TODO'"}
            >
              + cell
            </button>
            <button
              disabled={busy || !anyCellOk}
              onClick={() => apply("translate")}
              title="Show generated SQL (enabled after a cell run succeeds)"
            >
              Show SQL
            </button>
            <button
              disabled={busy || vsStale}
              onClick={() => apply("evaluate")}
              title={
                vsStale
                  ? "Terminology changed — Restart kernel to reload before running"
                  : "Run the whole library as one batch evaluation"
              }
            >
              Run all cells
            </button>
          </div>
           <div className="dev-boxes">
            {boxes.map((box) => (
              <div key={`${box.title}-${box.start}`} className="dev-box" data-box={box.title}>
                {editingTitle?.box.start === box.start ? (
                  <input
                    className="dev-box-title-input"
                    value={editingTitle.value}
                    autoFocus
                    onChange={(e) =>
                      setEditingTitle({ box, value: e.target.value })
                    }
                    onBlur={commitTitle}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitTitle();
                      if (e.key === "Escape") setEditingTitle(null);
                    }}
                  />
                ) : (
                  <div
                    className={
                      "dev-box-title" + (renameable(box) ? " renameable" : "")
                    }
                    title={
                      renameable(box)
                        ? "Click to rename (updates marker label or define + refs)"
                        : "This section's title is derived from its content"
                    }
                    onClick={() => {
                      if (renameable(box)) setEditingTitle({ box, value: box.title });
                    }}
                  >
                    {box.title}
                  </div>
                )}
                {box.kind === "define" ? (
                  <div className="dev-boxbar">
                    <button
                      className="dev-cellrun"
                      disabled={vsStale}
                      onMouseDown={() => (lastFocusedCell.current = box.name ?? "")}
                      onClick={() => runCell(box.name ?? "", "cell")}
                      title={
                        vsStale
                          ? "Terminology changed — Restart kernel to reload before running"
                          : `Run ${box.name} (auto-includes its dependencies; Cmd/Ctrl+Enter re-runs last-run cell)`
                      }
                    >
                      ▶ Run
                    </button>
                    <button
                      className="dev-cellrundeps"
                      disabled={vsStale}
                      onMouseDown={() => (lastFocusedCell.current = box.name ?? "")}
                      onClick={() => runCell(box.name ?? "", "cell_only")}
                      title={
                        vsStale
                          ? "Terminology changed — Restart kernel to reload before running"
                          : `Strict: run ${box.name} alone (advanced; dangling deps surface engine diagnostics)`
                      }
                    >
                      ▶ Run cell only
                    </button>
                    <span
                      className={
                        "dev-chip " +
                        (vsStale && (cellStates[box.name ?? ""] ?? "idle") !== "running"
                          ? "stale"
                          : cellStates[box.name ?? ""] ?? "idle")
                      }
                    >
                      {vsStale && (cellStates[box.name ?? ""] ?? "idle") !== "running"
                        ? "stale"
                        : (cellStates[box.name ?? ""] ?? "idle") === "idle"
                          ? "Not run"
                          : cellStates[box.name ?? ""] ?? "idle"}
                    </span>
                    {cellErrors[box.name ?? ""] && (
                      <span
                        className="dev-cellerr"
                        title={cellErrors[box.name ?? ""]}
                      >
                        ⚠
                      </span>
                    )}
                    {cellRows[box.name ?? ""] && (
                      <span className="dev-cellcount">
                        {cellRows[box.name ?? ""].length} rows
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="dev-boxbar">
                    <span className="dev-box-kind">{box.kind}</span>
                  </div>
                )}
                <div
                  className="dev-box-editor"
                  style={
                    box.kind === "header"
                      ? { height: `${Math.min(18 + 18 * boxBody(box).split("\n").length, 360)}px` }
                      : undefined
                  }
                >
                  <Editor
                    language="sql"
                    theme="dev-cql"
                    value={boxBody(box)}
                    onMount={(_e, monaco) => defineDevTheme(monaco)}
                    onChange={(v) => {
                      setBuffer((b) => spliceBox(b, box, v ?? "", box.kind === "header"));
                      setDirty(true);
                    }}
                    options={{
                      minimap: { enabled: false },
                      fontSize: 13,
                      fontFamily: "var(--font-mono)",
                      lineNumbers: "off",
                      scrollBeyondLastLine: false,
                      wordWrap: "on",
                      padding: { top: 4, bottom: 4 },
                      renderLineHighlight: "none",
                      automaticLayout: true,
                    }}
                  />
                </div>
                {cellFullRows[box.name ?? ""]?.length > 0 && (
                  <div className="dev-celltable">
                    <div className="dev-celltable-row dev-celltable-head">
                      <span>#</span>
                      <span>patient</span>
                      <span>{box.name}</span>
                    </div>
                    <div className="dev-celltable-body">
                      {cellFullRows[box.name ?? ""].slice(0, 5).map((row, i) => (
                        <div key={i} className="dev-celltable-row dev-cellresult-row">
                          <span>{i + 1}</span>
                          <span>{String(row.patient_id ?? "")}</span>
                          <span>{String(row[box.name ?? ""] ?? "")}</span>
                        </div>
                      ))}
                      {cellFullRows[box.name ?? ""].length > 5 && (
                        <div className="dev-cellresult-more">
                          +{cellFullRows[box.name ?? ""].length - 5} more rows — see
                          Results
                        </div>
                      )}
                    </div>
                    <button
                      className="dev-cellview"
                      onClick={() => setTab("results")}
                    >
                      View in Results →
                    </button>
                  </div>
                )}
                {cellErrors[box.name ?? ""] && (
                  <div className="dev-cellerror">{cellErrors[box.name ?? ""]}</div>
                )}
              </div>
            ))}
          </div>
          <div className="dev-cellindex">
            <button
              className="dev-cellindex-toggle"
              onClick={() => setIndexOpen((o) => !o)}
            >
              {indexOpen ? "▾" : "▸"} Cell index ({defineBoxes.length})
            </button>
            {indexOpen && (
              <div className="dev-cellindex-rows">
                {defineBoxes.map((box) => (
                  <div
                    key={box.title}
                    className="dev-cellindex-row"
                    onClick={() => jumpToBox(box.title)}
                    title="Jump to this cell"
                  >
                    <span
                      className={
                        "dev-chip " + (cellStates[box.name ?? ""] ?? "idle")
                      }
                    >
                      {(cellStates[box.name ?? ""] ?? "idle") === "idle"
                        ? "Not run"
                        : cellStates[box.name ?? ""] ?? "idle"}
                    </span>
                    <span className="dev-cellname">{box.title}</span>
                    <span
                      className="dev-cellindex-rename"
                      title="Rename this cell"
                      onClick={(e) => {
                        e.stopPropagation();
                        jumpToBox(box.title);
                        if (renameable(box))
                          setEditingTitle({ box, value: box.title });
                      }}
                    >
                      ✎
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
            </>
          )}
          {selected && (
            <TestsPane
              transport={transport}
              library={selected}
              buffer={buffer}
              kernelId={health?.kernel_id ?? "unknown"}
              patients={patients}
              definitions={
                workspace?.libraries.find((l) => l.name === selected)
                  ?.definitions ?? []
              }
            />
          )}
        </section>
        <section className="dev-output">
          <div className="dev-tabs">
            {(["results", "sql", "errors"] as Tab[]).map((t) => (
              <button
                key={t}
                className={tab === t ? "active" : ""}
                onClick={() => setTab(t)}
              >
                {t}
                {t === "errors" && diagnostics.length ? ` (${diagnostics.length})` : ""}
              </button>
            ))}
          </div>
          <div className="dev-pane">
            {tab === "results" && (
              <>
                {resultHeader && (
                  <div className="dev-resultheader">
                    {resultHeader}
                    {datasetStats && (
                      <span className="dev-resultctx" title="dataset context">
                        {" "}· {datasetStats.total} patients · kernel {health?.kernel_id ?? "?"}
                      </span>
                    )}
                  </div>
                )}
                {vsStale && (
                  <div
                    className="dev-stale"
                    title="Terminology changed on disk — restart the kernel to reload it, then re-run tests"
                  >
                    ⚠ Valueset changed — Restart kernel to reload
                  </div>
                )}
                {!result && !resultHeader && (
                  <div className="dev-guide">
                    <h3>Getting started</h3>
                    <ol>
                      <li>Pick a dataset (click it in the Data list to inspect it)</li>
                      <li>Click ▶ Run on a cell box</li>
                      <li>Cmd/Ctrl+Enter re-runs the last-run cell</li>
                    </ol>
                  </div>
                )}
                <ResultsTable
                  result={result}
                  error={
                    evaluate && !evaluate.ok && evaluate.diagnostics.length
                      ? evaluate.diagnostics[0].message
                      : null
                  }
                  isLoading={busy}
                />
              </>
            )}
            {tab === "sql" && <SQLOutput value={sql} />}
            {tab === "errors" && (
              <ul className="dev-errors">
                {diagnostics.length === 0 && <li>No diagnostics.</li>}
                {diagnostics.map((d, i) => (
                  <li key={i}>
                    <strong>{d.code}</strong> {d.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
