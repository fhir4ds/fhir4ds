import { useEffect, useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import { PaginatedTable } from "./PaginatedTable";
import { DiagnosticsRow } from "./EditorPane";
import { renderValue } from "../lib/formatValue";
import type {
  Diagnostics,
  LibraryText,
  DatasetSpec,
} from "../lib/protocol";

/**
 * Visual editor step 1 — the live defines matrix. Evaluates the ACTIVE
 * library with every define as an output column (output_columns
 * omitted → engine returns all defines) and renders patient × define.
 * Re-evaluates (debounced) whenever the library text, dataset, or
 * parameters change — but only while the tab is visible; hidden tabs
 * never spend engine time.
 */
interface MatrixState {
  loading: boolean;
  ok?: boolean;
  rows?: Array<Record<string, unknown>>;
  columns?: string[];
  column_types?: Record<string, string>;
  ms?: number | null;
  diags?: Diagnostics[];
  error?: string;
}

export function DefinesMatrix({
  libraries,
  main,
  dataset,
  parameters,
  visible,
  debounceMs,
}: {
  libraries: LibraryText[];
  main: LibraryText;
  dataset: DatasetSpec | null;
  parameters: Record<string, unknown>;
  visible: boolean;
  /** Debounce before evaluating (mirrors the heartbeat recalc delay). */
  debounceMs: number;
}) {
  const [state, setState] = useState<MatrixState | null>(null);
  const seqRef = useRef(0);
  const canRun = visible && !!dataset && !!main.text;

  useEffect(() => {
    if (!canRun) return;
    const seq = ++seqRef.current;
    setState({ loading: true });
    const t = setTimeout(async () => {
      try {
        const resp = (await workerRequest({
          type: "evaluate_library",
          libraries,
          main,
          dataset,
          parameters,
          emit_sql: false,
        })) as unknown as { envelope: string };
        if (seq !== seqRef.current) return;
        const env = JSON.parse(resp.envelope) as {
          ok: boolean;
          rows?: Array<Record<string, unknown>>;
          columns?: string[];
          column_types?: Record<string, string>;
          diagnostics?: Diagnostics[];
          timing_ms?: Record<string, number>;
        };
        setState({
          loading: false,
          ok: env.ok,
          rows: env.rows,
          columns: env.columns,
          column_types: env.column_types,
          ms: env.timing_ms?.evaluate ?? null,
          diags: env.ok ? [] : env.diagnostics ?? [],
        });
      } catch (e) {
        if (seq !== seqRef.current) return;
        setState({
          loading: false,
          ok: false,
          diags: [],
          error: e instanceof Error ? e.message : String(e),
        });
      }
    }, debounceMs);
    return () => clearTimeout(t);
  }, [canRun, libraries, main, dataset, parameters, debounceMs]);

  if (!visible) return null;
  if (!dataset || !main.text) {
    return (
      <p className="pane-hint" data-testid="defines-empty">
        A dataset and library text are needed to evaluate defines.
      </p>
    );
  }
  if (state?.loading) {
    return (
      <p className="pane-hint" data-testid="defines-loading">
        evaluating every define…
      </p>
    );
  }
  if (state?.error) {
    return (
      <p className="pane-error" data-testid="defines-error">
        {state.error}
      </p>
    );
  }
  if (state && !state.ok) {
    return (
      <div>
        <div className="diag-list" data-testid="defines-diags">
          {(state.diags ?? []).map((d, i) => (
            <DiagnosticsRow key={i} diag={d} />
          ))}
        </div>
      </div>
    );
  }
  if (!state?.rows || !state.columns?.length) {
    return (
      <p className="pane-hint" data-testid="defines-empty">
        No defines to show yet.
      </p>
    );
  }
  return (
    <PaginatedTable
      testId="defines-table"
      rowCount={state.rows.length}
      stats={
        <>
          {state.rows.length} patients · {state.columns.length} defines
          {state.ms != null ? ` · ${Math.round(state.ms)}ms` : ""}
        </>
      }
      header={
        <tr>
          {state.columns.map((c) => (
            <th key={c}>
              {c}
              {state.column_types?.[c] && (
                <span className="type-badge" title="CQL type">
                  {state.column_types[c]}
                </span>
              )}
            </th>
          ))}
        </tr>
      }
      renderRows={({ slice }) =>
        slice(state.rows!).map((row, i) => (
          <tr key={String(row.patient_id ?? i)}>
            {state.columns!.map((c) => (
              <td key={c} title={renderValue(row[c])}>
                {renderValue(row[c])}
              </td>
            ))}
          </tr>
        ))
      }
    />
  );
}
