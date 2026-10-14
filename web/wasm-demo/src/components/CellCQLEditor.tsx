/**
 * CellCQLEditor (c-wasm-bolton S3): the cell-based editing surface.
 *
 * Per FDD v2 §4.6 cell interaction spec (Muse-hardened):
 * - explicit persistent per-buffer toggle (never auto-detect)
 * - first-run coach mark
 * - Monaco decorations for `// # %%` markers (gutter glyphs) with text
 *   equivalents (aria labels on chips — no color-only states)
 * - per-cell run chips; RunMode segmented control (cell·cell_deps·to_here,
 *   default cell_deps); identical semantics both engines; "computed
 *   locally" badge on standalone runs
 * - inline results: collapsed-by-default when > N lines, always-expanded
 *   on error, per-cell clear + global clear-all, max-height + internal
 *   scroll (no layout shove)
 * - dep-closure PINNED (click a define chip to pin its closure; Esc clears)
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor from "@monaco-editor/react";
import { fixMonacoInputArea } from "../lib/monaco-shadow-fix";
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
  /** standalone (in-browser) execution badge — FDD Q2 */
  computedLocally?: boolean;
  ts: number;
}

interface CellCQLEditorProps {
  value: string;
  onChange: (value: string) => void;
  /** Insert a new cell marker before/after the given cell (name). */
  onInsertCell?: (anchor: string, where: "above" | "below") => void;
  /** Run a set of cells; resolves with per-cell output lines. */
  onRunCells: (names: string[], mode: CellRunMode) => Promise<Record<string, { ok: boolean; lines: string[] }>>;
  /** Connected (server) vs standalone (in-browser) — drives the badge. */
  connected: boolean;
}

const COACH_SEEN_KEY = "fhir4ds.cellCoachSeen";

export function CellCQLEditor({ value, onChange, onRunCells, onInsertCell, connected }: CellCQLEditorProps) {
  // S5 carry (S3 Muse): persist toggle + run mode across reloads.
  const [cellMode, setCellMode] = useState(
    () => localStorage.getItem("fhir4ds.cellMode") === "1",
  );
  const [runMode, setRunMode] = useState<CellRunMode>(
    () => (localStorage.getItem("fhir4ds.runMode") as CellRunMode | null) ?? "cell_deps",
  );
  useEffect(() => {
    localStorage.setItem("fhir4ds.cellMode", cellMode ? "1" : "0");
  }, [cellMode]);
  useEffect(() => {
    localStorage.setItem("fhir4ds.runMode", runMode);
  }, [runMode]);
  const [results, setResults] = useState<CellResult[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [pinnedClosure, setPinnedClosure] = useState<string | null>(null);
  const [expandedCells, setExpandedCells] = useState<Set<string>>(new Set());
  const [focusedCell, setFocusedCell] = useState<string | null>(null);
  const [coachOpen, setCoachOpen] = useState(false);
  const seenCoach = useRef(false);

  /** Splice an edited cell body back into the master buffer by span. */
  const spliceCell = useCallback(
    (order: number, newText: string) => {
      // Recompute spans against the CURRENT buffer (boxes semantics).
      const lines = value.split("\n");
      let offset = 0;
      let cellIdx = -1;
      let cellStart = -1;
      let cellEnd = -1;
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const isMarker = /^\s*\/\/\s*#\s*%%/.test(line);
        if (isMarker) {
          if (cellIdx === order) {
            // end of the target cell is this marker's start
            cellEnd = offset;
            break;
          }
          cellIdx += 1;
          cellStart = offset + line.length + 1; // past marker line + \n
        }
        offset += line.length + 1;
      }
      if (cellEnd === -1 && cellIdx === order) cellEnd = value.length;
      if (cellStart === -1 || cellEnd === -1) return;
      onChange(value.slice(0, cellStart) + (newText.endsWith("\n") ? newText : newText + "\n") + value.slice(cellEnd));
    },
    [value, onChange],
  );


  useEffect(() => {
    seenCoach.current = localStorage.getItem(COACH_SEEN_KEY) === "1";
  }, []);

  const graph: CellGraph = useMemo(() => buildCellGraph(value), [value]);
  const cells = useMemo(() => splitCells(value).cells, [value]);
  const hasMarkers = cells.length > 0;

  const toggleCellMode = useCallback(() => {
    setCellMode((v) => {
      const next = !v;
      if (next && !seenCoach.current) {
        setCoachOpen(true);
        localStorage.setItem(COACH_SEEN_KEY, "1");
        seenCoach.current = true;
      }
      return next;
    });
  }, []);

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
  // the focused cell (coach-mark-advertised keybinding — S3 Muse must-fix).
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
    <div className="cell-editor">
      <div className="cell-toolbar" role="toolbar" aria-label="Cell controls">
        <button
          type="button"
          className={`cell-toggle${cellMode ? " on" : ""}`}
          aria-pressed={cellMode}
          onClick={toggleCellMode}
          title="Cells split on `// # %%`. Ctrl/Cmd+Enter runs the focused cell."
          disabled={!hasMarkers && !cellMode}
        >
          Cells
        </button>
        <div className="cell-runmode" role="radiogroup" aria-label="Run mode">
          {(["cell", "cell_deps", "to_here"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={runMode === m}
              className={`cell-runmode-btn${runMode === m ? " on" : ""}`}
              onClick={() => setRunMode(m)}
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
        {results.length > 0 && (
          <button
            type="button"
            className="cell-clearall"
            onClick={() => setResults([])}
            title="Clear all cell outputs"
          >
            Clear all outputs
          </button>
        )}
        {pinnedClosure && (
          <span className="cell-pinned" role="status">
            pinned: {pinnedClosure} · {closureFor(pinnedClosure).join(" · ")}{" "}
            <button type="button" aria-label="Unpin dependency closure" onClick={() => setPinnedClosure(null)}>×</button>
          </span>
        )}
      </div>

      {coachOpen && (
        <div className="cell-coach" role="dialog" aria-label="Cell mode tips">
          <p>
            Cells split on <code>// # %%</code> markers. Use the run chip on each cell
            header (Ctrl/Cmd+Enter runs the focused cell). Click a define name to pin
            its dependency closure; Esc unpins.
          </p>
          <button type="button" onClick={() => setCoachOpen(false)}>Got it</button>
        </div>
      )}

      <div className="cell-editor-body">
        {cellMode && hasMarkers ? (
          <div className="cell-list">
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
                >
                  <div className="cell-head">
                    <button
                      type="button"
                      className="cell-addbtn"
                      aria-label={`Add cell above ${cell.name}`}
                      title="Add cell above"
                      onClick={() => onInsertCell?.(cell.name, "above")}
                    >
                      ＋↑
                    </button>
                    <button
                      type="button"
                      className="cell-addbtn"
                      aria-label={`Add cell below ${cell.name}`}
                      title="Add cell below"
                      onClick={() => onInsertCell?.(cell.name, "below")}
                    >
                      ＋↓
                    </button>
                    <button
                      type="button"
                      className="cell-namechip"
                      aria-label={`Cell ${cell.name}${deps.length ? ` — dependencies ${deps.join(", ")}` : ""}`}
                      onClick={() => setPinnedClosure((cur) => (cur === cell.name ? null : cell.name))}
                      onFocus={() => setFocusedCell(cell.name)}
                      title={deps.length ? `Deps: ${deps.join(", ")} (click to pin)` : "No dependencies"}
                    >
                      {cell.name}
                    </button>
                    <span className="cell-depcount" aria-hidden="true">
                      {deps.length ? `↳ ${deps.length}` : ""}
                    </span>
                    <button
                      type="button"
                      className="cell-run"
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
                  <Editor
                    language="sql"
                    theme="vs-dark"
                    value={cell.text}
                    onChange={(v) => spliceCell(cell.order, v ?? "")}
                    onMount={(editor) => {
                      fixMonacoInputArea(editor);
                      editor.onDidFocusEditorText(() => setFocusedCell(cell.name));
                    }}
                    options={{
                      minimap: { enabled: false },
                      fontSize: 13,
                      fontFamily: "var(--font-mono)",
                      lineNumbers: "on",
                      scrollBeyondLastLine: false,
                      wordWrap: "on",
                      padding: { top: 6 },
                      renderLineHighlight: "gutter",
                      automaticLayout: true,
                    }}
                  />
                  {res && (
                    <div className={`cell-out${collapsed && !expandedCells.has(cell.name) ? " collapsed" : ""}${res.ok ? "" : " expanded"}`} role="status">
                      {res.computedLocally && (
                        <span className="cell-localbadge" title="Executed by the in-browser engine">
                          computed locally
                        </span>
                      )}
                      <pre aria-label={`Output for ${cell.name}`}>
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
          <div className="editor-pane">
            <div className="pane-body">
              <Editor
                language="sql"
                theme="vs-dark"
                value={value}
                onChange={(v) => onChange(v ?? "")}
                onMount={fixMonacoInputArea}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  fontFamily: "var(--font-mono)",
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  padding: { top: 8 },
                  renderLineHighlight: "gutter",
                  automaticLayout: true,
                }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
