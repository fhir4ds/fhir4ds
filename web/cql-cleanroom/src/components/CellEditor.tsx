/**
 * CellEditor (c-cleanroom-redo S5): cell-based editing surface, ported
 * from the salvaged Bolton S3 core (CellCQLEditor) into the cleanroom
 * EditorPane per the arc FDD.
 *
 * Muse-hardened interaction spec (carried from bolton S3 review):
 * - explicit persistent per-buffer toggle (never auto-detect)
 * - first-run coach mark
 * - per-cell name chips with ARIA dep lists (no color-only states)
 * - closure-always Run semantics (S8: the RunMode control was removed —
 *   every Run executes the cell + its dependency closure, identical on
 *   both engines)
 * - inline per-cell results: ALWAYS expanded (S13 — the table's own
 *   scroll + 100-row cap replaced auto-collapse), per-cell clear +
 *   global clear-all, max-height + internal scroll (no layout shove)
 * - "computed locally" badge on standalone runs
 * - dep-closure PINNED (click a define chip to pin its closure; Esc
 *   clears); Ctrl/Cmd+Enter runs the focused cell
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { splitCells } from "../lib/cells";
import {
  buildCellGraph,
  dependencyClosure,
  type CellGraph,
} from "../lib/cell-deps";

export type CellRunMode = "cell" | "cell_deps" | "to_here";

export interface CellResult {
  cell: string;
  ok: boolean;
  lines: string[];
  /** S12: structured result (preferred over lines when present). */
  columns?: string[];
  rows?: Array<Array<string>>;
  /** standalone (in-browser) execution badge */
  computedLocally?: boolean;
  ts: number;
}

const CELL_TABLE_ROW_CAP = 100;
const CELL_HEIGHTS_KEY = "fhir4ds.cleanroom.cellHeights";

/** S14: per-card drag-resize heights, persisted per session (localStorage
 *  keyed by cell name — survives reloads). */
function loadCellHeights(libraryKey: string): Record<string, number> {
  try {
    const all = JSON.parse(localStorage.getItem(CELL_HEIGHTS_KEY) ?? "{}");
    return all[libraryKey] ?? {};
  } catch {
    return {};
  }
}

function writeCellHeights(libraryKey: string, heights: Record<string, number>) {
  try {
    const all = JSON.parse(localStorage.getItem(CELL_HEIGHTS_KEY) ?? "{}");
    all[libraryKey] = heights;
    localStorage.setItem(CELL_HEIGHTS_KEY, JSON.stringify(all));
  } catch {
    /* storage blocked — session-only fallback */
  }
}

interface CellEditorProps {
  value: string;
  /** Render one cell's Monaco editor (the host owns monaco-setup). */
  renderEditor: (
    cell: { name: string; text: string; order: number },
    /** S14: per-cell resize override (px) — the host threads it to the editor. */
    overrideHeight?: number,
  ) => React.ReactNode;
  /** Run a set of cells; resolves per-cell output lines. */
  onRunCells: (
    names: string[],
    mode: CellRunMode,
  ) => Promise<
    Record<string, { ok: boolean; lines: string[]; columns?: string[]; rows?: Array<Array<string>> }>
  >;
  /** S7: on-demand cellification of a markerless buffer (Auto-split). */
  onAutoSplit?: () => void | boolean;
  /** Connected (server) vs standalone (in-browser) — drives the badge. */
  connected: boolean;
}

const COACH_SEEN_KEY = "fhir4ds.cleanroom.cellCoachSeen";

export function CellEditor({ value, renderEditor, onRunCells, onAutoSplit, connected }: CellEditorProps) {
  // S8 directive 3: RunMode REMOVED — every Run executes the cell's
  // dependency closure (one behavior per cell).
  const [results, setResults] = useState<CellResult[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [pinnedClosure, setPinnedClosure] = useState<string | null>(null);
  const [focusedCell, setFocusedCell] = useState<string | null>(null);
  const [coachOpen, setCoachOpen] = useState(false);
  const seenCoach = useRef(false);

  const graph: CellGraph = useMemo(() => buildCellGraph(value), [value]);
  const cells = useMemo(() => splitCells(value).cells, [value]);
  const hasMarkers = cells.length > 0;

  useEffect(() => {
    seenCoach.current = localStorage.getItem(COACH_SEEN_KEY) === "1";
  }, []);
  useEffect(() => {
    if (hasMarkers && !seenCoach.current) {
      setCoachOpen(true);
      localStorage.setItem(COACH_SEEN_KEY, "1");
      seenCoach.current = true;
    }
  }, [hasMarkers]);

  const runCell = useCallback(
    async (name: string) => {
      setRunning(name);
      try {
        const names = dependencyClosure(name, graph.refs, new Set(graph.order));
        const out = await onRunCells(names, "cell_deps");
        setResults((prev) => [
          ...prev.filter((r) => !names.includes(r.cell)),
          ...names.map((n) => ({
            cell: n,
            ok: out[n]?.ok ?? false,
            lines: out[n]?.lines ?? ["(no output)"],
            columns: out[n]?.columns,
            rows: out[n]?.rows,
            computedLocally: !connected,
            ts: Date.now(),
          })),
        ]);
      } finally {
        setRunning(null);
      }
    },
    [graph, onRunCells, connected],
  );

  // Esc clears the pinned closure (and coach mark); Ctrl/Cmd+Enter runs
  // the focused cell.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinnedClosure(null);
        setCoachOpen(false);
      }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        if (focusedCell) void runCell(focusedCell);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [focusedCell, runCell]);

  // S14: per-card heights (drag handle). The stored value drives the
  // editor host height; results keep their fixed 240px internal-scroll
  // region — the handle sizes the card's editable footprint.
  const libraryKey =
    /^\s*library\s+([A-Za-z0-9_]+)/m.exec(value)?.[1] ?? "default";
  const [cellHeights, setCellHeights] = useState<Record<string, number>>(() =>
    loadCellHeights(libraryKey),
  );
  const cellHeightsRef = useRef(cellHeights);
  cellHeightsRef.current = cellHeights;
  const dragCell = useRef<{ name: string; startY: number; startH: number } | null>(null);

  const persistHeights = (next: Record<string, number>, writeThrough = true) => {
    setCellHeights(next);
    if (!writeThrough) return; // during drag: state only; write on release
    writeCellHeights(libraryKey, next);
  };

  const naturalHeight = (name: string) =>
    Math.min(
      420,
      Math.max(
        160,
        (cells.find((c) => c.name === name)?.text.split("\n").length ?? 1) * 19 + 16,
      ),
    );

  const beginDrag = (name: string, startY: number) => {
    dragCell.current = { name, startY, startH: cellHeightsRef.current[name] ?? naturalHeight(name) };
  };
  const moveDrag = (e: React.PointerEvent) => {
    const d = dragCell.current;
    if (!d) return;
    const next = Math.min(600, Math.max(160, d.startH + (e.clientY - d.startY)));
    persistHeights({ ...cellHeightsRef.current, [d.name]: next }, false);
  };
  const endDrag = () => {
    if (dragCell.current) {
      // Write-through once, on release.
      writeCellHeights(libraryKey, cellHeightsRef.current);
    }
    dragCell.current = null;
  };

  // Keyboard alternative: Enter/double-click toggles default <-> tall.
  const cycleHeight = (name: string) => {
    if (cellHeightsRef.current[name] == null) {
      persistHeights({ ...cellHeightsRef.current, [name]: 480 });
    } else {
      const { [name]: _drop, ...rest } = cellHeightsRef.current;
      persistHeights(rest);
    }
  };

  const closureFor = useCallback(
    (name: string) => dependencyClosure(name, graph.refs, new Set(graph.order)),
    [graph],
  );

  return (
    <div className="cell-editor" data-testid="cell-editor">
      <div className="cell-toolbar" role="toolbar" aria-label="Cell controls">

        {results.length > 0 && (
          <button
            type="button"
            className="cell-clearall"
            data-testid="cell-clearall"
            onClick={() => setResults([])}
            title="Clear all cell outputs"
          >
            Clear all outputs
          </button>
        )}
        {pinnedClosure && (
          <span className="cell-pinned" role="status" data-testid="cell-pinned">
            pinned: {pinnedClosure} · {closureFor(pinnedClosure).join(" · ")}{" "}
            <button type="button" aria-label="Unpin dependency closure" onClick={() => setPinnedClosure(null)}>×</button>
          </span>
        )}
      </div>

      {coachOpen && (
        <div className="cell-coach" role="dialog" aria-label="Cell mode tips" data-testid="cell-coach">
          <p>
            Cells split on <code>// # %%</code> markers. Markers may have just been
            added in-buffer (Ctrl+Z undoes; nothing is saved to disk until you
            save). <strong>▶ Run</strong> on a cell executes it and everything it
            depends on (Ctrl/Cmd+Enter runs the focused cell). Cells without
            a define show the whole library's columns. Click a cell's name
            to pin its dependency closure; Esc unpins.
          </p>
          <button type="button" onClick={() => setCoachOpen(false)}>Got it</button>
        </div>
      )}

      {hasMarkers ? (
        <div className="cell-list" data-testid="cell-list">
          {cells.map((cell) => {
            const deps = closureFor(cell.name).filter((d) => d !== cell.name);
            const res = results.find((r) => r.cell === cell.name);
            return (
              <div
                key={`${cell.name}-${cell.order}`}
                className={`cell-card${res && !res.ok ? " cell-error" : ""}${
                  pinnedClosure && pinnedClosure !== cell.name && closureFor(pinnedClosure).includes(cell.name)
                    ? " cell-in-closure"
                    : ""
                }${pinnedClosure && !closureFor(pinnedClosure).includes(cell.name) && pinnedClosure !== cell.name ? " cell-dimmed" : ""}`}
                data-cell={cell.name}
                aria-label={res && !res.ok ? `Cell ${cell.name} failed` : undefined}
                data-testid="cell-card"
              >
                <div className="cell-head">
                  <button
                    type="button"
                    className="cell-namechip"
                    data-testid="cell-namechip"
                    aria-label={`Cell ${cell.name}${deps.length ? ` — dependencies ${deps.join(", ")}` : ""}`}
                    onClick={() => setPinnedClosure((cur) => (cur === cell.name ? null : cell.name))}
                    onFocus={() => setFocusedCell(cell.name)}
                    title={
                      /^cell-\d+$/.test(cell.name)
                        ? "Unnamed cell — runs show all columns (add a define or a [name:] marker to narrow)"
                        : deps.length
                          ? `Deps: ${deps.join(", ")} (click to pin)`
                          : "No dependencies"
                    }
                  >
                    {cell.name}
                  </button>
                  <span className="cell-depcount" aria-hidden="true">
                    {deps.length ? `${deps.length} dep${deps.length === 1 ? "" : "s"}` : ""}
                  </span>
                  <button
                    type="button"
                    className="cell-run"
                    data-testid="cell-run"
                    title={running !== null ? "running…" : `Run ${cell.name} and its dependencies`}
                    disabled={running !== null}
                    onClick={() => runCell(cell.name)}
                    aria-label={`Run ${cell.name} and its dependencies`}
                  >
                    {running === cell.name ? "…" : "▶"}
                  </button>
                  {res && (
                    <button
                      type="button"
                      className="cell-out-clear"
                      aria-label={`Clear output for ${cell.name}`}
                      onClick={() => setResults((prev) => prev.filter((r) => r.cell !== cell.name))}
                    >
                      ×
                    </button>
                  )}
                </div>
                <div
                  className="cell-monaco"
                  onFocusCapture={() => setFocusedCell(cell.name)}
                >
                  {renderEditor(cell, cellHeights[cell.name])}
                </div>
                {res && (
                  <div className={"cell-out"} role="status" data-testid="cell-out">
                    {res.computedLocally && (
                      <span className="cell-localbadge" title="Executed by the in-browser engine">
                        computed locally
                      </span>
                    )}
                    {!res.ok && (
                      <span className="cell-errortag" role="alert">error</span>
                    )}
                    {res.columns && res.columns.length > 0 && res.rows ? (
                      <div
                        className="cell-table-wrap"
                        data-testid="cell-table"
                        role="region"
                        tabIndex={0}
                        aria-label={`Results table for ${cell.name}`}
                      >
                        <table className="cell-table">
                          <thead>
                            <tr>
                              {res.columns.map((c) => (
                                <th key={c} scope="col">{c}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {res.rows.slice(0, CELL_TABLE_ROW_CAP).map((r, i) => (
                              <tr key={i}>
                                {r.map((v, j) => (
                                  <td key={j} title={v}>{v}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        {res.rows.length > CELL_TABLE_ROW_CAP && (
                          <div className="cell-table-cap" role="status">
                            showing {CELL_TABLE_ROW_CAP} of {res.rows.length} rows
                          </div>
                        )}
                      </div>
                    ) : null}
                    {!(res.columns && res.columns.length > 0 && res.rows) && (
                      <pre aria-label={`Output for ${cell.name}${res.ok ? "" : " (failed)"}`}>
                        {res.lines.join("\n")}
                      </pre>
                    )}
                  </div>
                )}
                  <div
                    className="cell-resize-handle"
                    role="separator"
                    aria-orientation="horizontal"
                    aria-label={`Resize ${cell.name}`}
                    aria-valuenow={cellHeights[cell.name] ?? naturalHeight(cell.name)}
                    aria-valuemin={160}
                    aria-valuemax={600}
                    data-testid="cell-resize"
                    tabIndex={0}
                    onPointerDown={(e) => {
                      e.currentTarget.setPointerCapture(e.pointerId);
                      beginDrag(cell.name, e.clientY);
                    }}
                    onPointerMove={moveDrag}
                    onPointerUp={endDrag}
                    onPointerCancel={endDrag}
                    onDoubleClick={() => cycleHeight(cell.name)}
                    onKeyDown={(e) => {
                      const cur = cellHeights[cell.name] ?? naturalHeight(cell.name);
                      if (e.key === "ArrowDown") {
                        e.preventDefault();
                        persistHeights({ ...cellHeights, [cell.name]: Math.min(600, cur + 20) });
                      } else if (e.key === "ArrowUp") {
                        e.preventDefault();
                        persistHeights({ ...cellHeights, [cell.name]: Math.max(160, cur - 20) });
                      } else if (e.key === "Enter") {
                        cycleHeight(cell.name);
                      }
                    }}
                    title="Drag to resize · double-click or Enter to reset · arrow keys ±20px"
                  >
                    <span className="grip" />
                  </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="pane-hint" style={{ padding: "10px 14px" }} data-testid="cell-empty-hint">
          <p>
            No <code>// # %%</code> markers in this buffer. Add{" "}
            <code>{"// # %% [name: MyDefine]"}</code> above a define to split it
            into a runnable cell.
          </p>
          {onAutoSplit && (
            <button
              type="button"
              className="cell-toggle"
              data-testid="cell-autosplit"
              onClick={() => {
                onAutoSplit();
              }}
              title="Insert // # %% markers before each top-level define"
            >
              Auto-split
            </button>
          )}
        </div>
      )}
    </div>
  );
}
