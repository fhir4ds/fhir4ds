import { useEffect, useRef, useState } from "react";
import type { Transport } from "./transport";

/** Normalise the /api/dataset-stats by_type payload into a Record for rendering. */
function normalizeStats(payload: { total: number; by_type: unknown }): { total: number; byType: Record<string, number> } {
  const raw = payload.by_type;
  if (Array.isArray(raw)) {
    const byType: Record<string, number> = {};
    for (const entry of raw) {
      if (entry && typeof entry === "object" && "resourceType" in entry && "count" in entry) {
        const e = entry as { resourceType: string; count: number };
        byType[e.resourceType] = e.count;
      }
    }
    return { total: payload.total, byType };
  }
  if (raw && typeof raw === "object") {
    return { total: payload.total, byType: raw as Record<string, number> };
  }
  return { total: payload.total, byType: {} };
}

interface Props {
  transport: Transport;
  path: string;
  datasetName: string;
  onEditInBuilder: (resource: Record<string, unknown>, datasetPath: string) => void;
}

interface ParsedFile {
  resources: Record<string, unknown>[];
  parse_errors: { line: number; error: string }[];
}

export function DatasetPane({ transport, path, datasetName, onEditInBuilder }: Props) {
  const [stats, setStats] = useState<{ total: number; byType: Record<string, number> } | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [file, setFile] = useState<ParsedFile | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number>(-1);
  const alive = useRef(true);

  // Fresh stats fetch on EVERY pane open / path change — never cached from mount.
  useEffect(() => {
    alive.current = true;
    setStatsLoading(true);
    setStats(null);
    fetch("/api/dataset-stats")
      .then((r) => r.json())
      .then((payload) => {
        if (alive.current) {
          setStats(normalizeStats(payload));
          setStatsLoading(false);
        }
      })
      .catch(() => {
        if (alive.current) setStatsLoading(false);
      });
    return () => {
      alive.current = false;
    };
  }, [path]);

  useEffect(() => {
    let cancelled = false;
    setFile(null);
    setFileError(null);
    setSelected(-1);
    transport
      .dataset(path)
      .then((r) => {
        if (!cancelled) setFile({ resources: r.resources, parse_errors: r.parse_errors });
      })
      .catch((e: unknown) => {
        if (!cancelled) setFileError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [transport, path]);

  const sel = file && selected >= 0 && selected < file.resources.length ? file.resources[selected] : null;
  const selType =
    sel && typeof sel === "object" && "resourceType" in sel && typeof (sel as { resourceType: unknown }).resourceType === "string"
      ? (sel as { resourceType: string }).resourceType
      : "";
  const selId =
    sel && typeof sel === "object" && "id" in sel && typeof (sel as { id: unknown }).id === "string"
      ? (sel as { id: string }).id
      : "";

  return (
    <div className="dev-dspane">
      <div className="dev-dshead">
        Dataset: <strong>{datasetName}</strong> · kernel loaded:
        {statsLoading ? (
          <span className="dev-dsloading"> loading stats…</span>
        ) : stats ? (
          <span className="dev-dsstats">
            {" "}
            <span className="dev-dstotal">total: {stats.total}</span>
            {Object.entries(stats.byType).map(([t, n]) => (
              <span key={t} className="dev-dschipstat">
                {t}: {n}
              </span>
            ))}
          </span>
        ) : (
          <span className="dev-dsloading"> stats unavailable</span>
        )}
      </div>
      {stats && stats.total === 0 && file && file.resources.length > 0 ? (
        <div className="dev-dserrors">
          ⚠ kernel loaded 0 resources but the file holds {file.resources.length} — a malformed line (see below) makes the
          strict kernel load fail. Fix the line and restart the kernel.
        </div>
      ) : null}
      {fileError ? <div className="dev-dserrors">{fileError}</div> : null}
      {file && file.parse_errors.length > 0 ? (
        <div className="dev-dserrors">
          {file.parse_errors.map((p) => (
            <div key={p.line}>
              ⚠ line {p.line}: {p.error}
            </div>
          ))}
        </div>
      ) : null}
      <div className="dev-dsmain">
        <div className="dev-dslist">
          <div className="dev-dsrow dev-dsrowhead">
            <span className="dev-dsctype">#</span>
            <span className="dev-dsctype">type</span>
            <span className="dev-dsid">id</span>
          </div>
          {file
            ? file.resources.map((r, i) => {
                const rt =
                  r && typeof r === "object" && typeof (r as { resourceType?: unknown }).resourceType === "string"
                    ? (r as { resourceType: string }).resourceType
                    : "?";
                const rid =
                  r && typeof r === "object" && typeof (r as { id?: unknown }).id === "string"
                    ? (r as { id: string }).id
                    : "";
                return (
                  <div
                    key={i}
                    className={"dev-dsrow" + (i === selected ? " on" : "")}
                    onClick={() => setSelected(i)}
                    title={`Show ${rt}/${rid}`}
                  >
                    <span className="dev-dsctype">{i + 1}</span>
                    <span className="dev-dsctype">{rt}</span>
                    <span className="dev-dsid">{rid}</span>
                  </div>
                );
              })
            : null}
          {file && file.resources.length === 0 ? <div className="dev-dsempty">file has no readable resources</div> : null}
        </div>
        <div className="dev-dsdetail">
          {sel ? (
            <>
              <div className="dev-dsbar">
                <span>
                  {selType}
                  {selId ? ` / ${selId}` : ""}
                </span>
                <button className="dev-dsedit" onClick={() => onEditInBuilder(sel, path)} title="Open this resource in the builder (save appends a new line to the same file)">
                  ✎ Edit in builder
                </button>
              </div>
              <pre className="dev-dsjson">{JSON.stringify(sel, null, 2)}</pre>
            </>
          ) : (
            <div className="dev-dsempty">select a resource to view it</div>
          )}
          <div className="dev-pane-hint">
            Saving from the builder appends a NEW line to the file — restart the kernel to load new data.
          </div>
        </div>
      </div>
    </div>
  );
}
