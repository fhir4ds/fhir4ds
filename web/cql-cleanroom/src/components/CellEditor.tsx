/**
 * CellEditor (c-cleanroom-redo S5): cell-based editing surface, ported
 * from the salvaged Bolton S3 core (CellCQLEditor) into the cleanroom
 * EditorPane per the arc FDD.
 *
 * Muse-hardened interaction spec (carried from bolton S3 review):
 * - explicit persistent per-buffer toggle (never auto-detect)
 * - first-run coach mark
 * - per-cell name chips with ARIA dep lists (no color-only states)
 * - RunMode segmented control (cell·cell_deps·to_here, default
 *   cell_deps) with IDENTICAL semantics browser+server
 * - inline per-cell results: collapsed-by-default when > 12 lines,
 *   always-expanded on error, per-cell clear + global clear-all,
 *   max-height + internal scroll (no layout shove)
 * - "computed locally" badge on standalone runs
 * - dep-closure PINNED (click a define chip to pin its closure; Esc
 *   clears); Ctrl/Cmd+Enter runs the focused cell
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { splitCells } from "../lib/cells";
import {
  buildCellGraph,
  dependencyClosure,
  expandRunMode,
  type CellGraph,
} from "../lib/cell-deps";

export type CellRunMode = "cell" | "cell_deps" | "to_here";

export interface CellResult {
  cell: string;
  ok: boolean;
  lines: string[];
  /** standalone (in-browser) execution badge */
  computedLocally?: boolean;
  ts: number;
}

interface CellEditorProps {
  value: string;
  /** Render one cell's Monaco editor (the host owns monaco-setup). */
  renderEditor: (cell: { name: string; text: string; order: number }) => React.ReactNode;
  /** Run a set of cells; resolves per-cell output lines. */
  onRunCells: (names: string[], mode: CellRunMode) => Promise<Record<string, { ok: boolean; lines: string[] }>>;
  /** S7: on-demand cellification of a markerless buffer (Auto-split). */
  onAutoSplit?: () => void | boolean;
  /** Connected (server) vs standalone (in-browser) — drives the badge. */
  connected: boolean;
}

const COACH_SEEN_KEY = "fhir4ds.cleanroom.cellCoachSeen";

export function CellEditor({ value, renderEditor, onRunCells, onAutoSplit, connected }: CellEditorProps) {
  // The per-buffer toggle lives in EditorPane (cell-view-toggle) — this
  // component renders cards whenever mounted with markers. Run mode
  // persists across reloads (S3 Muse carry).
  const [runMode, setRunMode] = useState<CellRunMode>(
    () => (localStorage.getItem("fhir4ds.cleanroom.runMode") as CellRunMode | null) ?? "cell_deps",
  );
  useEffect(() => {
    localStorage.setItem("fhir4ds.cleanroom.runMode", runMode);
  }, [runMode]);
  const [results, setResults] = useState<CellResult[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [pinnedClosure, setPinnedClosure] = useState<string | null>(null);
  const [expandedCells, setExpandedCells] = useState<Set<string>>(new Set());
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
        const names = expandRunMode(runMode, name, graph);
        const out = await onRunCells(names, runMode);
        setResults((prev) => [
          ...prev.filter((r) => !names.includes(r.cell)),
          ...names.map((n) => ({
            cell: n,
            ok: out[n]?.ok ?? false,
            lines: out[n]?.lines ?? ["(no output)"],
            computedLocally: !connected,
            ts: Date.now(),
          })),
        ]);
      } finally {
        setRunning(null);
      }
    },
    [runMode, graph, onRunCells, connected],
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

  const closureFor = useCallback(
    (name: string) => dependencyClosure(name, graph.refs, new Set(graph.order)),
    [graph],
  );

  return (
    <div className="cell-editor" data-testid="cell-editor">
      <div className="cell-toolbar" role="toolbar" aria-label="Cell controls">
        {hasMarkers && (
          <div className="cell-runmode" role="radiogroup" aria-label="Run mode" data-testid="cell-runmode">
            {(["cell", "cell_deps", "to_here"] as const).map((m) => (
              <button
                key={m}
                type="button"
                role="radio"
                aria-checked={runMode === m}
                className={`cell-runmode-btn${runMode === m ? " on" : ""}`}
                onClick={() => setRunMode(m)}
                aria-label={
                  m === "cell"
                    ? "Run only this cell"
                    : m === "cell_deps"
                      ? "Run this cell and its dependency closure"
                      : "Run all authored cells up to and including this cell"
                }
                title={
                  m === "cell"
                    ? "Run only this cell"
                    : m === "cell_deps"
                      ? "Run this cell and its dependency closure"
                      : "Run all authored cells up to and including this cell"
                }
              >
                {m === "cell_deps" ? "cell + deps" : m === "to_here" ? "to here" : m}
              </button>
            ))}
          </div>
        )}
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
            save). Use the <strong>▶ Run</strong> button on each cell header
            (Ctrl/Cmd+Enter runs the focused cell). Run mode defaults to
            <strong>cell + deps</strong> — it runs this cell and everything it depends on.
            Click a cell's name to pin its dependency closure; Esc unpins.
          </p>
          <button type="button" onClick={() => setCoachOpen(false)}>Got it</button>
        </div>
      )}

      {hasMarkers ? (
        <div className="cell-list" data-testid="cell-list">
          {cells.map((cell) => {
            const deps = closureFor(cell.name).filter((d) => d !== cell.name);
            const res = results.find((r) => r.cell === cell.name);
            const collapsed = res?.ok && res.lines.length > 12;
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
                    title={deps.length ? `Deps: ${deps.join(", ")} (click to pin)` : "No dependencies"}
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
                    title={running !== null ? "running…" : `Run ${cell.name} (${runMode})`}
                    disabled={running !== null}
                    onClick={() => runCell(cell.name)}
                    aria-label={`Run ${cell.name} (${runMode})`}
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
                  {renderEditor(cell)}
                </div>
                {res && (
                  <div className={`cell-out${collapsed && !expandedCells.has(cell.name) ? " collapsed" : ""}${res.ok ? "" : " expanded"}`} role="status" data-testid="cell-out">
                    {res.computedLocally && (
                      <span className="cell-localbadge" title="Executed by the in-browser engine">
                        computed locally
                      </span>
                    )}
                    {!res.ok && (
                      <span className="cell-errortag" role="alert">error</span>
                    )}
                    <pre aria-label={`Output for ${cell.name}${res.ok ? "" : " (failed)"}`}>
                      {collapsed && !expandedCells.has(cell.name)
                        ? res.lines.slice(0, 4).join("\n") + "\n…"
                        : res.lines.join("\n")}
                    </pre>
                    {collapsed && (
                      <button
                        type="button"
                        className="cell-expand"
                        aria-expanded={expandedCells.has(cell.name)}
                        onClick={() =>
                          setExpandedCells((prev) => {
                            const next = new Set(prev);
                            if (next.has(cell.name)) next.delete(cell.name);
                            else next.add(cell.name);
                            return next;
                          })
                        }
                      >
                        {expandedCells.has(cell.name) ? "collapse" : `${res.lines.length} lines — expand`}
                      </button>
                    )}
                  </div>
                )}
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
