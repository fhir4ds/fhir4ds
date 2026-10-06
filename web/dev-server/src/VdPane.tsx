import { useEffect, useMemo, useState } from "react";
import Editor from "@monaco-editor/react";
import { defineDevTheme } from "./boxes";
import { ResultsTable } from "@wasm-demo/components/ResultsTable";
import type { QueryResult } from "@wasm-demo/components/ResultsTable";
import { SQLOutput } from "@wasm-demo/components/SQLOutput";
import type { Transport, Diagnostic, ViewRunResult } from "./transport";

interface Props {
  transport: Transport;
  path: string;
  datasetName: string | null;
  patientCount: number | null;
}

export function VdPane({ transport, path, datasetName, patientCount }: Props) {
  const stem = useMemo(() => path.split("/").pop()?.replace(/\.json$/, "") ?? path, [path]);
  const [text, setText] = useState("");
  const [dirty, setDirty] = useState(false);
  const [resource, setResource] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<ViewRunResult | null>(null);
  const [tab, setTab] = useState<"results" | "sql">("results");
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setDirty(false);
    setResult(null);
    setRunError(null);
    setError(null);
    transport
      .view(path)
      .then((v) => {
        if (!alive) return;
        setText(v.text);
        setResource(v.resource);
      })
      .catch((e: unknown) => alive && setError(String(e instanceof Error ? e.message : e)));
    return () => {
      alive = false;
    };
  }, [transport, path]);

  const run = async () => {
    setBusy(true);
    setRunError(null);
    setResult(null);
    try {
      const r = await transport.viewRun(text, undefined);
      if (r.ok) {
        setResult(r);
        setTab("results");
      } else {
        const d = (r.diagnostics as Diagnostic[] | undefined)?.[0];
        setRunError(d?.message ?? "view run failed");
      }
    } catch (e: unknown) {
      setRunError(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dev-vdpane">
      <div className="dev-vdhead">
        <strong>ViewDefinition: {stem}</strong>
        {resource ? <span className="dev-vdres"> · resource {resource}</span> : null}
        {datasetName ? (
          <span className="dev-vdctx"> · dataset {datasetName}{patientCount !== null ? ` (${patientCount} patients)` : ""}</span>
        ) : null}
      </div>
      <div className="dev-vdbar">
        <button className="dev-vdrun" onClick={run} disabled={busy || dirty} title={dirty ? "Apply edits first (editors are the writer; the file is the source)" : "Run this view over the loaded dataset"}>
          ▶ Run view
        </button>
        {dirty ? <span className="dev-vddirty">buffer edited — file preview only; Save writes are not part of v1</span> : null}
      </div>
      {error ? <div className="dev-vderror">{error}</div> : null}
      <div className="dev-vdeditor">
        <Editor
          height="220px"
          theme="dev-cql"
          defaultLanguage="json"
          value={text}
          onMount={(_, monaco) => defineDevTheme(monaco)}
          onChange={(v) => {
            setText(v ?? "");
            setDirty(true);
          }}
          options={{ minimap: { enabled: false }, lineNumbers: "on", scrollBeyondLastLine: false, tabSize: 2 }}
        />
      </div>
      <div className="dev-vdhint">
        where paths evaluate against the iterated focus — use %resource for the row resource, %context for the current node.
      </div>
      {runError ? (
        <div className="dev-vderror" role="alert">
          {runError}
        </div>
      ) : null}
      {result ? (
        <div className="dev-vdresults">
          <div className="dev-vdtabs">
            <button className={tab === "results" ? "on" : ""} onClick={() => setTab("results")}>
              Results ({result.rows.length} rows)
            </button>
            <button className={tab === "sql" ? "on" : ""} onClick={() => setTab("sql")}>
              SQL
            </button>
            <span className="dev-vdcount">{result.resource_count} {result.resource_count === 1 ? "resource" : "resources"} staged</span>
          </div>
          {tab === "results" ? (
            <ResultsTable
              result={{ columns: result.columns, rows: result.rows.map((r) => result.columns.map((c) => r[c])), rowCount: result.rows.length, executionTimeMs: 0 } satisfies QueryResult}
              error={null}
              isLoading={false}
            />
          ) : (
            <SQLOutput value={result.sql} />
          )}
        </div>
      ) : null}
    </div>
  );
}
