/**
 * CleanroomRail (c-wasm-bolton S2): the single adaptive rail.
 *
 * Per FDD v2 §4.6 + BOLTON_S2_RAIL_MAPPING.md (the gate artifact):
 * - ONE rail, stable order both modes — core section always active;
 *   cleanroom section capability-gated.
 * - Standalone NEVER hides cleanroom entries: disabled + remedy
 *   ("requires a connected server — run `fhir4ds dev`") per the hybrid
 *   rule; clicking a disabled entry opens an empty-state panel.
 * - Connected: Libraries opens the workspace file tree (fsList), History
 *   the runlog; watcher `changed` events badge Libraries/Valuesets.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import type { ModeState } from "../transport/handshake";
import type { HttpTransport } from "../transport/http-transport";

export type RailId =
  | "cql"
  | "data"
  | "sql"
  | "viewer"
  | "libraries"
  | "valuesets"
  | "measures"
  | "terminology"
  | "history";

interface RailEntryDef {
  id: RailId;
  label: string;
  glyph: string;
  title: string;
  cleanroom: boolean;
}

export const RAIL_ENTRIES: RailEntryDef[] = [
  { id: "cql", label: "CQL", glyph: "✏️", title: "CQL editor (alt+1)", cleanroom: false },
  { id: "data", label: "Data", glyph: "▤", title: "Data (alt+2)", cleanroom: false },
  { id: "sql", label: "SQL", glyph: "📄", title: "Generated SQL (alt+3)", cleanroom: false },
  { id: "viewer", label: "Viewer", glyph: "🧑", title: "Patient data viewer (alt+4)", cleanroom: false },
  { id: "libraries", label: "Libraries", glyph: "❯", title: "Workspace libraries (alt+5)", cleanroom: true },
  { id: "valuesets", label: "Valuesets", glyph: "◈", title: "Workspace valuesets (alt+6)", cleanroom: true },
  { id: "measures", label: "Measures", glyph: "✓", title: "Measures & expected results (alt+7)", cleanroom: true },
  { id: "terminology", label: "Terminology", glyph: "⌘", title: "Terminology import (alt+8)", cleanroom: true },
  { id: "history", label: "History", glyph: "⏱", title: "Run history (alt+9)", cleanroom: true },
];

export const REMEDY = "Requires a connected server — run `fhir4ds dev`";

interface CleanroomRailProps {
  mode: ModeState;
  transport: HttpTransport | null;
  activeId: RailId | null;
  onSelect: (id: RailId) => void;
  /** Libraries/Valuesets get change badges when watcher fires (connected). */
  changeBadge?: Partial<Record<RailId, number>>;
}

export function CleanroomRail({
  mode,
  transport,
  activeId,
  onSelect,
  changeBadge = {},
}: CleanroomRailProps) {
  const connected = mode.kind === "connected" && transport !== null;
  return (
    <nav className="cleanroom-rail" aria-label="Workspace navigation">
      {RAIL_ENTRIES.map((e, i) => {
        const disabled = e.cleanroom && !connected;
        const badge = changeBadge[e.id];
        return (
          <button
            key={e.id}
            type="button"
            className={`cleanroom-rail-btn${activeId === e.id ? " active" : ""}${disabled ? " disabled" : ""}${e.cleanroom ? " cleanroom" : ""}`}
            title={disabled ? `${e.title} — ${REMEDY}` : e.title}
            aria-label={disabled ? `${e.label} — ${REMEDY}` : e.label}
            aria-disabled={disabled}
            accessKey={String(((i % 9) + 1))}
            onClick={() => onSelect(e.id)}
          >
            <span className="cleanroom-rail-glyph" aria-hidden="true">{e.glyph}</span>
            <span className="cleanroom-rail-label">{e.label}</span>
            {disabled && <span className="cleanroom-rail-lock" aria-hidden="true">🔒</span>}
            {badge !== undefined && badge > 0 && (
              <span className="cleanroom-rail-badge" aria-label={`${badge} changed`}>{badge}</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

/** Empty-state panel for disabled entries / hidden interiors (hybrid rule). */
export function RailEmptyState({ id }: { id: RailId }) {
  const def = RAIL_ENTRIES.find((e) => e.id === id);
  return (
    <div className="cleanroom-empty" role="status">
      <h3>{def?.label ?? id}</h3>
      <p>{REMEDY}.</p>
      <code>fhir4ds dev</code>
    </div>
  );
}

/** Connected workspace file tree (server-mediated: fsList under root). */
interface FsEntry {
  name: string;
  kind: "dir" | "file";
  suffix: string;
}

export function WorkspaceFileTree({
  transport,
  suffixFilter,
  subdir,
  changedPaths,
  onReload,
  onOpenFile,
}: {
  transport: HttpTransport;
  suffixFilter?: string[];
  /** Conventional subdir to list (e.g. "cql" for libraries) — the
   *  workspace root itself holds directories, not artifacts. */
  subdir?: string;
  /** Watcher changed paths (per-file dots, mapping rule 5). */
  changedPaths?: string[];
  /** Called after a manual refresh — acknowledges the badge. */
  onReload?: () => void;
  onOpenFile?: (name: string) => void;
}) {
  const [entries, setEntries] = useState<FsEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    transport
      .fsList(subdir)
      .then((res) => {
        if (res.ok === false) {
          setError(res.diagnostics?.[0]?.message ?? "listing failed");
          setEntries(null);
        } else {
          setError(null);
          setEntries(res.entries ?? []);
        }
      })
      .catch((e: unknown) => setError(String(e)))
      .finally(() => onReload?.());
  }, [transport, subdir, onReload]);

  useEffect(load, [load]);
  const changedNames = useMemo(() => {
    if (!changedPaths || changedPaths.length === 0) return new Set<string>();
    return new Set(changedPaths.map((p) => p.split("/").pop() ?? p));
  }, [changedPaths]);

  const files = useMemo(() => {
    if (!entries) return null;
    return suffixFilter
      ? entries.filter((e) => e.kind === "dir" || suffixFilter.includes(e.suffix))
      : entries;
  }, [entries, suffixFilter]);

  if (error) return <div className="cleanroom-tree-error" role="alert">{error}</div>;
  if (!files) return <div className="cleanroom-tree-loading" aria-live="polite">loading…</div>;
  return (
    <div>
      <div className="cleanroom-tree-actions">
        <button type="button" className="data-hint-restart" onClick={load}>
          Refresh
        </button>
      </div>
      <ul className="cleanroom-tree" role="tree">
      {files.map((f) => (
        <li key={f.name} role="treeitem" aria-expanded={f.kind === "dir" ? false : undefined}>
          <button
            type="button"
            className="cleanroom-tree-row"
            onClick={() => f.kind === "file" && onOpenFile?.(f.name)}
            disabled={f.kind === "dir"}
            title={changedNames.has(f.name) ? `${f.name} — changed on disk` : f.name}
          >
            <span aria-hidden="true">{f.kind === "dir" ? "📁" : "📄"}</span> {f.name}
            {changedNames.has(f.name) && (
              <span className="cleanroom-file-dot" aria-label="changed on disk" title="changed on disk" />
            )}
          </button>
        </li>
      ))}
    </ul>
    </div>
  );
}

/** Connected run history (persistent runlog via runsList; runs/sql
 *  drill-down lands with the SQL history tab in S2b). */
export function RunHistory({ transport }: { transport: HttpTransport }) {
  const [runs, setRuns] = useState<{ ts: number; kind: string; library?: string }[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);

  const load = useCallback(() => {
    transport
      .runsList()
      .then((res: any) => {
        const data = res?.data ?? res;
        if (data?.ok === false) {
          setError(data?.diagnostics?.[0]?.message ?? "runlog unavailable");
          setRuns(null);
        } else {
          setError(null);
          setRuns(data?.runs ?? []);
        }
      })
      .catch((e: unknown) => setError(String(e)));
  }, [transport]);

  useEffect(load, [load]);

  if (error) return <div className="cleanroom-tree-error" role="alert">{error}</div>;
  if (!runs) return <div className="cleanroom-tree-loading" aria-live="polite">loading…</div>;
  return (
    <div className="runhistory-list">
      <div className="runhistory-actions">
        {runs.length > 0 && !confirmingClear && (
          <button type="button" className="data-hint-restart" onClick={() => setConfirmingClear(true)}>
            Clear history
          </button>
        )}
        {confirmingClear && (
          <span className="runhistory-confirm" role="alertdialog" aria-label="Confirm clear">
            Clear {runs.length} run{runs.length === 1 ? "" : "s"}?{" "}
            <button
              type="button"
              onClick={() => {
                transport
                  .runsClear()
                  .then(() => {
                    setRuns([]);
                    setConfirmingClear(false);
                  })
                  .catch(() => setConfirmingClear(false));
              }}
            >
              Yes, clear
            </button>
            <button type="button" onClick={() => setConfirmingClear(false)}>Cancel</button>
          </span>
        )}
      </div>
      {runs.length === 0 ? (
        <div className="cleanroom-empty">
          <p>No runs yet — run a cell or a measure to populate the history.</p>
        </div>
      ) : (
        <ul className="cleanroom-tree">
          {runs.map((r, i) => (
            <li key={`${r.ts}-${i}`} role="treeitem">
              <span className="cleanroom-tree-row">
                {new Date(r.ts).toLocaleTimeString()} · {r.kind}
                {r.library ? ` · ${r.library}` : ""}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
