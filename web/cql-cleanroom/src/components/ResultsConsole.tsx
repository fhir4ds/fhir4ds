import { useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import { PaginatedTable } from "./PaginatedTable";
import { DiagnosticsRow } from "./EditorPane";
import type { Diagnostics, LibraryText, DatasetSpec } from "../lib/protocol";

/**
 * WORKBENCH_REORG phase 4 — the CQL console below the editor.
 *
 * Run evaluates the WHOLE visible library; Run-Selection evaluates the
 * highlighted expression in the library's context (worker
 * evaluate_snippet: hidden __snippet__ define, narrowed output,
 * diagnostics renumbered back into the selection). Replaces the
 * FHIRPath scratchpad as the quick-eval surface.
 */

type ConsoleRows = { columns: string[]; rows: Array<Record<string, unknown>>; ms: number | null };

export function ResultsConsole({
  libraries,
  main,
  dataset,
  parameters,
  selection,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: DatasetSpec | null;
  parameters: Record<string, unknown>;
  /** Current editor selection text (null/empty disables Run-Selection). */
  selection: string | null;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [diags, setDiags] = useState<Diagnostics[]>([]);
  const [result, setResult] = useState<ConsoleRows | null>(null);
  const seqRef = useRef(0);

  const run = async (mode: "library" | "selection") => {
    const seq = ++seqRef.current;
    setBusy(true);
    setError(null);
    setDiags([]);
    try {
      const resp = await workerRequest(
        mode === "selection"
          ? {
              type: "evaluate_snippet",
              libraries,
              main,
              snippet: selection ?? "",
              dataset,
              parameters,
            }
          : {
              type: "evaluate_library",
              libraries,
              main,
              dataset,
              parameters,
              emit_sql: false,
            },
      );
      if (seq !== seqRef.current) return;
      const env = JSON.parse((resp as { envelope: string }).envelope) as {
        ok: boolean;
        diagnostics?: Diagnostics[];
        columns?: string[];
        rows?: Array<Record<string, unknown>>;
        timing_ms?: Record<string, number>;
        patient_count?: number;
      };
      if (!env.ok) {
        setDiags(env.diagnostics ?? []);
        setResult(null);
      } else {
        setResult({
          columns: env.columns ?? [],
          rows: env.rows ?? [],
          ms: env.timing_ms?.evaluate ?? null,
        });
      }
    } catch (e) {
      if (seq === seqRef.current) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (seq === seqRef.current) setBusy(false);
    }
  };

  const hasSelection = (selection ?? "").trim().length > 0;

  return (
    <section className="pane results-console" data-testid="results-console">
      <header className="pane-header">
        <h2>CQL console</h2>
        <div className="pane-actions">
          <button
            data-testid="console-run-library"
            disabled={busy}
            onClick={() => void run("library")}
          >
            {busy ? "running…" : "Run"}
          </button>
          <button
            data-testid="console-run-selection"
            disabled={busy || !hasSelection}
            title={hasSelection ? "evaluate the selected expression" : "select code in the editor first"}
            onClick={() => void run("selection")}
          >
            Run selection
          </button>
        </div>
      </header>
      {error && <p className="pane-error" data-testid="console-error">{error}</p>}
      {diags.length > 0 && (
        <div className="diag-list" data-testid="console-diags">
          {diags.map((d, i) => (
            <DiagnosticsRow key={i} diag={d} />
          ))}
        </div>
      )}
      {result && result.columns.length > 0 && (
        <PaginatedTable
          testId="console-table"
          rowCount={result.rows.length}
          stats={
            <>
              {result.rows.length} rows ·{" "}
              {result.ms != null ? `${Math.round(result.ms)}ms` : ""}
            </>
          }
          header={
            <tr>
              <th>patient_id</th>
              {result.columns.filter((c) => c !== "patient_id").map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          }
          renderRows={(range) => (
            <>
              {result.rows.slice(range.start, range.end).map((r, i) => (
                <tr key={range.start + i}>
                  <td>{String(r.patient_id ?? "")}</td>
                  {result.columns.filter((c) => c !== "patient_id").map((c) => (
                    <td key={c}>{String(r[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </>
          )}
        />
      )}
      {!result && diags.length === 0 && !error && (
        <p className="pane-hint" data-testid="console-empty">
          Run evaluates the whole library; select an expression and Run
          selection evaluates just that, in context.
        </p>
      )}
    </section>
  );
}
