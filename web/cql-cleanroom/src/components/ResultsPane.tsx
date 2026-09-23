import { useState } from "react";
import type { EvaluateResult, Diagnostics } from "../lib/protocol";
import { workerRequest } from "./BootOverlay";
import type { LibraryText } from "../lib/protocol";

export function ResultsPane({
  libraries,
  main,
  dataset,
  outputColumns,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: { resources?: Record<string, unknown>[] } | null;
  outputColumns: Record<string, string> | null;
}) {
  const [result, setResult] = useState<EvaluateResult | null>(null);
  const [diags, setDiags] = useState<Diagnostics[] | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setDiags(null);
    try {
      const resp = await workerRequest({
        type: "evaluate_library",
        libraries,
        main,
        dataset,
        output_columns: outputColumns,
        emit_sql: true,
      });
      const env: EvaluateResult = JSON.parse(resp.envelope);
      if (env.ok) setResult(env);
      else setDiags(env.diagnostics ?? []);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="pane" data-testid="results-pane">
      <header className="pane-header">
        <h2>Results</h2>
        <button onClick={run} disabled={busy} data-testid="run-eval">
          {busy ? "Running…" : "Evaluate"}
        </button>
      </header>
      {diags && (
        <ul className="diag-list" data-testid="eval-diags">
          {diags.map((d, i) => (
            <li key={i} className="diag-row">
              <span className="diag-code">{d.code}</span> {d.message}
            </li>
          ))}
        </ul>
      )}
      {result && (
        <>
          <div className="eval-meta" data-testid="eval-meta">
            {result.patient_count} patients · {result.timing_ms.evaluate}ms
          </div>
          <table className="results-table" data-testid="results-table">
            <thead>
              <tr>
                {result.columns.map((c) => (
                  <th key={c}>
                    {c}
                    {result.column_types[c] && (
                      <span
                        className="type-badge"
                        data-testid={`type-badge-${c}`}
                        title="CQL type"
                      >
                        {result.column_types[c]}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, i) => (
                <tr key={i}>
                  {result.columns.map((c) => (
                    <td key={c}>{renderValue(row[c])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {result.sql && <SqlViewer sql={result.sql} />}
        </>
      )}
    </section>
  );
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

export function SqlViewer({ sql }: { sql: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="sql-viewer" data-testid="sql-viewer">
      <button onClick={() => setOpen(!open)} data-testid="sql-toggle">
        {open ? "Hide SQL" : "Show SQL"}
      </button>
      {open && <pre className="sql-pre">{sql}</pre>}
    </div>
  );
}
