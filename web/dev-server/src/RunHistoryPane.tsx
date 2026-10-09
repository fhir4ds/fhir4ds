import { useCallback, useEffect, useState } from "react";
import type { HttpTransport } from "./http-transport";

export interface RunEvent {
  id: string;
  ts: string;
  kind: string;
  target: string;
  status: string;
  duration_ms: number;
  row_count: number;
  summary?: Record<string, unknown>;
  params?: Record<string, unknown>;
  library_sha?: string;
  sql_sha?: string;
  error?: string;
  datasets?: string[];
  patient_count?: number;
}

const KINDS = ["all", "cell", "measure", "test", "view"] as const;

/**
 * Run-history pane (parity item 2) — debug-compare primary: newest-first
 * list of run events with kind filter, per-event summary/dataset context,
 * copy-sql-ref (resolves the CURRENT sql store; honest 'superseded' when
 * stale), and reopen-target. Shell-agnostic: renders anywhere (icon-rail
 * slide-out today, bottom-bar history tab later).
 */
export function RunHistoryPane({
  transport,
  onReopen,
  refreshKey,
}: {
  transport: HttpTransport;
  onReopen: (kind: string, target: string) => void;
  /** Refetch whenever this string changes while the pane is visible. */
  refreshKey: string;
}) {
  const [runs, setRuns] = useState<RunEvent[]>([]);
  const [filter, setFilter] = useState<(typeof KINDS)[number]>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const reload = useCallback(() => {
    transport
      .runsList()
      .then((r: { ok: boolean; runs?: RunEvent[] }) => setRuns(r.runs ?? []))
      .catch(() => setRuns([]));
  }, [transport]);

  useEffect(() => {
    reload();
  }, [reload, refreshKey]);

  const shown = filter === "all" ? runs : runs.filter((r) => r.kind === filter);

  const copySqlRef = useCallback(
    (sha: string) => {
      transport
        .runSqlGet(sha)
        .then((r: { ok: boolean; sql?: string; diagnostics?: { message: string }[] }) => {
          if (r.ok && r.sql) {
            navigator.clipboard?.writeText(r.sql).then(
              () => setMsg("SQL copied to clipboard"),
              () => setMsg("clipboard unavailable — SQL shown in console"),
            );
            // eslint-disable-next-line no-console
            console.log(r.sql);
          } else {
            setMsg(r.diagnostics?.[0]?.message ?? "sql superseded");
          }
        })
        .catch(() => setMsg("sql lookup failed"));
    },
    [transport],
  );

  return (
    <div className="dev-runhistory">
      <div className="dev-toolbar">
        <span className="dev-pane-label" title="Run history — debug-compare across runs (.runlog.jsonl)">
          Run history
        </span>
        {KINDS.map((k) => (
          <button
            key={k}
            className={"dev-rhfilter" + (filter === k ? " active" : "")}
            onClick={() => setFilter(k)}
          >
            {k}
          </button>
        ))}
        <button
          className="dev-rhclear"
          title="Clear the run history (deletes .runlog.jsonl)"
          onClick={() => {
            transport.runsClear().then(reload).catch(() => undefined);
          }}
        >
          clear
        </button>
      </div>
      {msg && <div className="dev-vsimportmsg" role="status">{msg}</div>}
      {shown.length === 0 && (
        <div className="dev-rhempty">No runs yet — history starts with your first run.</div>
      )}
      {shown.map((r) => (
        <div key={r.id} className="dev-rhrow" onClick={() => setExpanded(expanded === r.id ? null : r.id)}>
          <span className={"dev-rhdot " + r.status} title={r.status} />
          <span className="dev-rhkind" title={r.kind}>{r.kind}</span>
          <span className="dev-rhtarget" title={r.target}>{r.target}</span>
          <span className="dev-rhmeta" title={`${r.row_count} rows · ${r.duration_ms}ms`}>
            {r.row_count}r · {r.duration_ms}ms
          </span>
          <span className="dev-rhts">{r.ts}</span>
          {expanded === r.id && (
            <div className="dev-rhdetail" onClick={(e) => e.stopPropagation()}>
              {r.datasets && r.datasets.length > 0 && (
                <div>
                  datasets: {r.datasets.map((d) => d.split("/").pop()).join(", ")}
                  {r.patient_count != null && ` · ${r.patient_count} patients`}
                </div>
              )}
              {r.summary && (
                <div className="dev-rhsummary">
                  {Object.entries(r.summary).map(([k, v]) => (
                    <span key={k}>{k}: {String(v)}</span>
                  ))}
                </div>
              )}
              {r.params && Object.keys(r.params).length > 0 && (
                <div>params: {JSON.stringify(r.params)}</div>
              )}
              {r.error && <div className="dev-rherror">{r.error}</div>}
              <div className="dev-rhactions">
                <button onClick={() => onReopen(r.kind, r.target)}>reopen target</button>
                {r.sql_sha && <button onClick={() => copySqlRef(r.sql_sha!)}>copy SQL</button>}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
