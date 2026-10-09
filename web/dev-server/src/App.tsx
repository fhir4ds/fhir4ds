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
import { TerminologyDialog } from "./TerminologyDialog";
import { PathPickerDialog } from "./PathPickerDialog";
import { MeasurePane } from "./MeasurePane";
import { VdPane } from "./VdPane";
import { DatasetPane } from "./DatasetPane";
import { ResourceBuilderPane } from "./ResourceBuilderPane";

type Tab = "results" | "sql" | "errors";

function guideSteps(rail: { kind: string; id?: string } | null): { title: string; steps: string[] } {
  if (!rail) return { title: "Getting started", steps: [
    "Pick a dataset (click it in the Data list to inspect it)",
    "Click ▶ Run on a cell box",
    "Cmd/Ctrl+Enter re-runs the last-run cell",
  ] };
  switch (rail.kind) {
    case "valueset": return { title: "Getting started — valuesets", steps: [
      "Edit system/code cells; display is ignored for membership",
      "Insert the valueset declaration into the library header",
      "Restart the kernel after saving, then re-run tests",
    ] };
    case "params": return { title: "Getting started — parameters", steps: [
      "Add a parameter row (name, type, optional default)",
      "Reference it in CQL as %Name",
      "Edits apply to the library header box on Apply",
    ] };
    case "measure": return { title: "Getting started — measures", steps: [
      "Select scoring, then map populations to Boolean defines",
      "Scaffold preview shows the Measure JSON (never auto-saves)",
      "Run computes counts + per-patient MeasureReports; save a baseline or paste expected JSON to compare",
    ] };
    case "view": return { title: "Getting started — ViewDefinitions", steps: [
      "Edit the VD JSON (constants table and path assist can help)",
      "Click ▶ Run view to execute over the loaded dataset",
      "Inspect Results and VD → SQL tabs; invariant errors show inline",
    ] };
    case "builder": return { title: "Getting started — resource builder", steps: [
      "Pick a starter template (form rows are helpers; JSON is authoritative)",
      "Validate, choose a dataset file, and Save to append",
      "Restart the kernel to load the new data",
    ] };
    case "dataset": return { title: "Getting started — datasets", steps: [
      "Review kernel-loaded stats and the file's resource list",
      "Click a resource to inspect its JSON",
      "\u274e Edit in builder opens the resource pre-filled for a new appended line",
    ] };
    default: return { title: "Getting started", steps: [
      "Pick a dataset (click it in the Data list to inspect it)",
      "Click \u25b6 Run on a cell box",
      "Cmd/Ctrl+Enter re-runs the last-run cell",
    ] };
  }
}

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
  const [termDialog, setTermDialog] = useState(false);
  const [pickerKind, setPickerKind] = useState<"cql" | "valueset" | "measure" | "data" | "view" | null>(null);
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [tab, setTab] = useState<Tab>("results");
  const [busy, setBusy] = useState(false);
  const [dataHint, setDataHint] = useState<string[]>([]);
  const [runMode, setRunMode] = useState<RunMode>("cell");
  const [cellStates, setCellStates] = useState<Record<string, string>>({});
  const [cellStaleReasons, setCellStaleReasons] = useState<Record<string, string>>({});
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
  // v3.1: rail count badges — patients (kernel stats), valueset concept
  // counts (lazy fetch), VD column counts (client-side text parse).
  const [vsCounts, setVsCounts] = useState<Record<string, number> | null>(null);
  const [vsPeek, setVsPeek] = useState<{ path: string; codes: string[] } | null>(null);

  const boxes = useMemo(() => splitBoxes(buffer), [buffer]);
  const defineBoxes = useMemo(() => boxes.filter((b) => b.kind === "define"), [boxes]);

  // v3.1: lazily fetch valueset concept counts once per workspace snapshot;
  // VD column badges are parsed client-side from the file text we already
  // have via the view route when opened — here we parse the rail names only
  // for the patient badge source (datasetStats is fetched on mount below).
  useEffect(() => {
    let alive = true;
    const targets = (workspace?.valuesets ?? []).slice(0, 12);
    if (targets.length === 0) {
      setVsCounts(null);
      return;
    }
    (async () => {
      const next: Record<string, number> = {};
      await Promise.all(
        targets.map(async (v) => {
          try {
            const env = (await (
              await fetch(`/api/valueset?path=${encodeURIComponent(v)}`)
            ).json()) as { ok?: boolean; concepts?: unknown[] };
            if (env?.ok && Array.isArray(env.concepts)) next[v] = env.concepts.length;
          } catch {
            /* best-effort badge */
          }
        }),
      );
      if (alive) setVsCounts(next);
    })();
    return () => {
      alive = false;
    };
  }, [workspace?.valuesets]);

  const vdColumnCount = useCallback((text: string): number | null => {
    try {
      const vd = JSON.parse(text) as { select?: unknown };
      const first = Array.isArray(vd?.select) ? (vd.select[0] as { column?: unknown }) : null;
      return Array.isArray(first?.column) ? first.column.length : null;
    } catch {
      return null;
    }
  }, []);

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
      if ((e.kind === "cellstate" || e.kind === "synced") && e.states) {
        setCellStates((prev) => ({ ...prev, ...e.states! }));
        if (e.stale_reasons) setCellStaleReasons((prev) => ({ ...prev, ...e.stale_reasons! }));
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
        setCellStaleReasons((prev) => {
          const next = { ...prev };
          for (const n of e.cells ?? []) delete next[n];
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
          {health?.terminology && (
            <span
              className={`dev-termpill dev-termpill-${health.terminology.provider}`}
              title={`terminology: ${health.terminology.provider} (api key set: ${health.terminology.api_key_set}) — click to configure`}
              onClick={() => setTermDialog(true)}
            >
              <span
                className={
                  "dev-termdot " +
                  (health.terminology.provider !== "disabled" &&
                  health.terminology.configured &&
                  health.terminology.api_key_set
                    ? "dev-termdot-connected"
                    : "dev-termdot-offline")
                }
              />
              {health.terminology.provider !== "disabled" &&
              health.terminology.configured &&
              health.terminology.api_key_set
                ? "VSAC connected"
                : "VSAC offline — local only"}
            </span>
          )}
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
          <h2>Libraries <button className="dev-addrail" title="Add a cql path to the workspace (persists to fhir4ds.toml [dev])" onClick={() => setPickerKind("cql")}>+</button></h2>
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
          <h2>Data <button className="dev-addrail" title="Add a data path to the workspace (persists to fhir4ds.toml [dev])" onClick={() => setPickerKind("data")}>+</button></h2>
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
              {datasetStats && workspace?.datasets.length === 1 ? (
                <span className="dev-railbadge" title={`${datasetStats.total} resources loaded in the kernel`}>
                  {datasetStats.total}
                </span>
              ) : null}
            </div>
          ))}
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
          {(workspace?.valuesets ?? []).length > 0 && <h2>ValueSets <button className="dev-addrail" title="Add a valueset path to the workspace (persists to fhir4ds.toml [dev])" onClick={() => setPickerKind("valueset")}>+</button></h2>}
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
              {vsCounts?.[v] != null ? (
                <span
                  className="dev-railbadge dev-railbadge-vs"
                  title={`${vsCounts[v]} concepts — click badge to peek codes`}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (vsPeek?.path === v) {
                      setVsPeek(null);
                    } else {
                      fetch(`/api/valueset?path=${encodeURIComponent(v)}`)
                        .then((r) => r.json())
                        .then((env: { ok?: boolean; concepts?: { system?: string; code?: string }[] }) => {
                          if (env?.ok && Array.isArray(env.concepts)) {
                            setVsPeek({
                              path: v,
                              codes: env.concepts.slice(0, 25).map((c) => `${c.code ?? "?"}`),
                            });
                          }
                        })
                        .catch(() => setVsPeek(null));
                    }
                  }}
                >
                  {vsCounts[v]}
                </span>
              ) : null}
            </div>
          ))}
          {vsPeek ? (
            <div className="dev-vspeek" role="note">
              <div className="dev-vspeek-head">
                <span>{vsPeek.path.split("/").pop()?.replace(/\.json$/, "")} — codes (first {vsPeek.codes.length})</span>
                <button className="dev-vspeek-close" onClick={() => setVsPeek(null)}>
                  ✕
                </button>
              </div>
              <div className="dev-vspeek-list">
                {vsPeek.codes.map((c, i) => (
                  <code key={i} className="dev-vspeek-code">
                    {c}
                  </code>
                ))}
              </div>
              <div className="dev-vspeek-note">expansion preview — membership uses system + code</div>
            </div>
          ) : null}
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
          <h2>Measures <button className="dev-addrail" title="Add a measure path to the workspace (persists to fhir4ds.toml [dev])" onClick={() => setPickerKind("measure")}>+</button></h2>
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
          <h2>ViewDefinitions <button className="dev-addrail" title="Add a view path to the workspace (persists to fhir4ds.toml [dev])" onClick={() => setPickerKind("view")}>+</button></h2>
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
              onImported={() => {
                refreshWorkspace();
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
                      title={
                        vsStale && (cellStates[box.name ?? ""] ?? "idle") !== "running"
                          ? "STALE — terminology changed; restart kernel to reload"
                          : cellStaleReasons[box.name ?? ""]
                            ? `STALE — ${cellStaleReasons[box.name ?? ""]}`
                            : undefined
                      }
                    >
                      {vsStale && (cellStates[box.name ?? ""] ?? "idle") !== "running"
                        ? "stale"
                        : (cellStates[box.name ?? ""] ?? "idle") === "idle"
                          ? "Not run"
                          : cellStates[box.name ?? ""] ?? "idle"}
                    </span>
                    {!vsStale &&
                      cellStates[box.name ?? ""] === "stale" &&
                      cellStaleReasons[box.name ?? ""] && (
                        <span className="dev-stalereason">
                          — {cellStaleReasons[box.name ?? ""]}
                        </span>
                      )}
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
                    <span
                      className="dev-resultctx dev-resultterm"
                      title="terminology state at run time — stale means a valueset changed on disk after the kernel loaded it"
                    >
                      {" "}· terminology: {vsStale ? "stale" : "clean"}
                    </span>
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
                {!result && !resultHeader && (() => {
                  const g = guideSteps(railView);
                  return (
                    <div className="dev-guide">
                      <h3>{g.title}</h3>
                      <ol>
                        {g.steps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ol>
                    </div>
                  );
                })()}
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
      {termDialog && (
        <TerminologyDialog
          transport={transport}
          onClose={() => setTermDialog(false)}
          onSaved={() => refreshWorkspace()}
        />
      )}
      {pickerKind && (
        <PathPickerDialog
          transport={transport}
          kind={pickerKind}
          onClose={() => setPickerKind(null)}
          onAdded={() => refreshWorkspace()}
        />
      )}
    </div>
  );
}
