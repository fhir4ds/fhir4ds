import { useCallback, useEffect, useMemo, useState } from "react";
import { CQLEditor } from "@wasm-demo/components/CQLEditor";
import { SQLOutput } from "@wasm-demo/components/SQLOutput";
import { ResultsTable } from "@wasm-demo/components/ResultsTable";
import type { QueryResult } from "@wasm-demo/components/ResultsTable";
import { HttpTransport } from "./http-transport";
import type {
  Diagnostic,
  EvaluateResult,
  HealthInfo,
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
    return off;
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
  }, [transport]);


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
