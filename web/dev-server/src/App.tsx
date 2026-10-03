import { useCallback, useEffect, useMemo, useState } from "react";
import { CQLEditor } from "@wasm-demo/components/CQLEditor";
import { SQLOutput } from "@wasm-demo/components/SQLOutput";
import { ResultsTable } from "@wasm-demo/components/ResultsTable";
import type { QueryResult } from "@wasm-demo/components/ResultsTable";
import { HttpTransport } from "./http-transport";
import { chunkEditor } from "./cells";
import type {
  CellEvent,
  Diagnostic,
  EvaluateResult,
  HealthInfo,
  RunMode,
  WorkspaceEvent,
  WorkspaceInfo,
} from "./transport";

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

  const loadLibrary = useCallback(
    async (name: string) => {
      setSelected(name);
      const r = await transport.library(name);
      setBuffer((r as unknown as { text?: string }).text ?? "");
      setDirty(false);
    },
    [transport],
  );

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
    const h = await transport.restartKernel();
    setHealth(h);
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
    (name: string) => {
      if (!selected) return;
      transport.syncCells(selected, buffer);
      transport.runCell(selected, name, runMode, buffer);
    },
    [buffer, runMode, selected, transport],
  );


  return (
    <div className="dev-app">
      <header className="dev-header">
        <h1>FHIR4DS CQL Cleanroom</h1>
        <span className="dev-status">
          {health ? `${health.kernel_id} · ${health.watching} files` : "…"}
        </span>
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
          {workspace?.datasets.length ? (
            <h2>Data</h2>
          ) : null}
          {(workspace?.datasets ?? []).map((d) => (
            <div key={d} className="dev-lib small" title={d}>
              {d.split("/").pop()}
            </div>
          ))}
        </aside>
        <section className="dev-editor">
          <div className="dev-toolbar">
            <span>{selected}{dirty ? " *" : ""}</span>
            <select
              value={runMode}
              onChange={(e) => setRunMode(e.target.value as RunMode)}
              title="Cell run mode"
            >
              <option value="cell">cell</option>
              <option value="cell_deps">cell + deps</option>
              <option value="all">all</option>
              <option value="to_here">to here</option>
            </select>
            <button disabled={busy} onClick={() => apply("translate")}>
              Translate
            </button>
            <button disabled={busy} onClick={() => apply("evaluate")}>
              Run ▶
            </button>
          </div>
          <CQLEditor
            value={buffer}
            onChange={(v) => {
              setBuffer(v);
              setDirty(true);
            }}
          />
          <div className="dev-cellrail">
            {chunkEditor(buffer)
              .filter((c) => c.type === "cell")
              .map((c) => (
                <div key={c.name ?? c.order} className="dev-cellrow">
                  <button
                    className="dev-cellrun"
                    onClick={() => runCell(c.name ?? "")}
                    title={`Run ${c.name} (${runMode})`}
                  >
                    ▶
                  </button>
                  <span className="dev-cellname">{c.name}</span>
                  <span className={"dev-chip " + (cellStates[c.name ?? ""] ?? "idle")}>
                    {cellStates[c.name ?? ""] ?? "idle"}
                  </span>
                  {cellErrors[c.name ?? ""] && (
                    <span className="dev-cellerr" title={cellErrors[c.name ?? ""]}>
                      ⚠
                    </span>
                  )}
                  {cellRows[c.name ?? ""] && (
                    <span className="dev-cellcount">
                      {cellRows[c.name ?? ""].length} rows
                    </span>
                  )}
                </div>
              ))}
          </div>
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
              <ResultsTable
                result={result}
                error={
                  evaluate && !evaluate.ok && evaluate.diagnostics.length
                    ? evaluate.diagnostics[0].message
                    : null
                }
                isLoading={busy}
              />
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
