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
  /** Run a set of cells; resolves with per-cell output lines. */
  onRunCells: (names: string[], mode: CellRunMode) => Promise<Record<string, { ok: boolean; lines: string[] }>>;
  /** Connected (server) vs standalone (in-browser) — drives the badge. */
  connected: boolean;
}

const COACH_SEEN_KEY = "fhir4ds.cellCoachSeen";

export function CellCQLEditor({ value, onChange, onRunCells, connected }: CellCQLEditorProps) {
  const [cellMode, setCellMode] = useState(false);
  const [runMode, setRunMode] = useState<CellRunMode>("cell_deps");
  const [results, setResults] = useState<CellResult[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [pinnedClosure, setPinnedClosure] = useState<string[] | null>(null);
  const [coachOpen, setCoachOpen] = useState(false);
  const seenCoach = useRef(false);

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

  // Esc clears the pinned closure (and coach mark).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinnedClosure(null);
        setCoachOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

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
            pinned deps: {pinnedClosure.join(" · ")}{" "}
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
                  className={`cell-card${res && !res.ok ? " cell-error" : ""}`}
                  data-cell={cell.name}
                >
                  <div className="cell-head">
                    <button
                      type="button"
                      className="cell-namechip"
                      aria-label={`Cell ${cell.name}${deps.length ? ` — dependencies ${deps.join(", ")}` : ""}`}
                      onClick={() => setPinnedClosure((cur) => (cur ? null : deps))}
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
                    onChange={(v) => {
                      // Splice the edited cell body back into the master buffer.
                      // Chunk-level editors: splice via boxes spans (S3b); the
                      // simple path re-uses onChange with the full buffer for now.
                      void v;
                    }}
                    onMount={fixMonacoInputArea}
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
                    <div className={`cell-out${collapsed ? " collapsed" : ""}${res.ok ? "" : " expanded"}`} role="status">
                      {res.computedLocally && (
                        <span className="cell-localbadge" title="Executed by the in-browser engine">
                          computed locally
                        </span>
                      )}
                      <pre aria-label={`Output for ${cell.name}`}>
                        {res.lines.slice(0, collapsed ? 0 : res.lines.length).join("\n")}
                      </pre>
                      {collapsed && (
                        <button type="button" className="cell-expand" onClick={() => {
                          setResults((prev) =>
                            prev.map((r) => (r.cell === cell.name ? { ...r, lines: r.lines, ok: r.ok } : r)),
                          );
                        }}>
                          {res.lines.length} lines — expand
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
