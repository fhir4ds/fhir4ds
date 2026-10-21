import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import { BuilderPane } from "./BuilderPane";
import { CellEditor } from "./CellEditor";
import { countReferences, extractCqlSymbols } from "../lib/cqlSymbols";
import { cellify, hasSplittableDefines } from "../lib/cellify";
import { splitCells } from "../lib/cells";

/**
 * S22a: the pristine in-browser CleanroomDemo default (raw or
 * auto-cellified) — the connected boot-purity pass replaces it with the
 * workspace's first disk library, so cellify/adoption bookkeeping must
 * skip it while connected (see the auto-cellify effect).
 */
function isPristineDemoDefault(text: string): boolean {
  if (!text.startsWith("library CleanroomDemo")) return false;
  const cellified = cellify(text);
  return cellified === null || text === cellified;
}
import type { Diagnostics, ParseResult } from "../lib/protocol";

/**
 * C1-U5: Monaco CQL editor with live diagnostics.
 *
 * - parse_cql on a 400ms debounce; Diagnostics.location → Monaco markers
 * - declarations block → parameter panel (values kept client-side and
 *   forwarded as default parameter bindings at evaluation time)
 * - data-testids for the e2e suite (editor, marker, params)
 */

interface Props {
  text: string;
  onTextChange: (text: string) => void;
  onDiagnostics?: (diags: Diagnostics[]) => void;
  onParamsDetected?: (names: string[]) => void;
  /** Which workspace resource this editor shows ("library:lib_0").
   *  One Monaco ITextModel per key: undo stacks + cursors survive tab
   *  switches; models for keys dropped from knownTabKeys are disposed. */
  tabKey?: string;
  knownTabKeys?: string[];
  /** Selection text ("" when empty) for the console's Run-Selection. */
  onSelectionChange?: (text: string) => void;
  /** REORG 6g: the header Run button (and Ctrl/Cmd+Enter) — runs the
   *  selection when one exists, else the whole library. */
  onRun?: () => void;
  /** REORG 6d: the visual-editor drawer lives under this pane; its
   *  toggle is a header button (was a standalone bottom bar). */
  graphOpen?: boolean;
  onGraphOpenChange?: (open: boolean) => void;
  /** S23-2: cell view visibility changes (the App suppresses the
   *  auto-recalc heartbeat while cells are the active surface). */
  onCellsViewChange?: (open: boolean) => void;
  /** S5: run a set of cells (cell-based editor execution). */
  onRunCells?: (
    names: string[],
    mode: "cell" | "cell_deps" | "to_here",
  ) => Promise<Record<string, { ok: boolean; lines: string[] }>>;
  /** S5: connected (server) vs standalone — drives the local badge. */
  connected?: boolean;
  /**
   * S22a: hold the S7 auto-cellify/adoption bookkeeping while TRUE —
   * the server handshake may still flip the app to connected, where
   * boot purity replaces the pristine demo default (adopting it first
   * would persist a bogus cellsRemoved entry for the tab).
   */
  holdAutoSplit?: boolean;
  /** S16/S19: open the evidence popover for a row — carries the run's
   *  composition + parameters so evidence matches the run exactly. */
  onExplainRow?: (
    patientId: string,
    define: string,
    context?: {
      composedText?: string;
      params?: Record<string, unknown>;
      computedLocally?: boolean;
    },
  ) => void;
  /** S20: popover factory — rendered ONLY in the cell whose
   *  (cellName, patientId) matches the clicked row. */
  cellEvidenceSlot?: (cellName: string) => React.ReactNode;
  /** S19: current runtime parameters (stored on each cell run result). */
  parameters?: Record<string, unknown>;
}

interface DiagnosticsRowProps {
  diag: Diagnostics;
  onSelect?: (d: Diagnostics) => void;
}

function severityClass(sev: string | undefined): string {
  switch (sev) {
    case "error":
      return "diag-error";
    case "warning":
      return "diag-warning";
    default:
      return "diag-info";
  }
}

export function DiagnosticsRow({ diag, onSelect }: DiagnosticsRowProps) {
  const loc = diag.location;
  const where = loc
    ? `L${loc.start_line ?? "?"}${loc.start_column != null ? `:${loc.start_column}` : ""}`
    : "";
  return (
    <button
      className={`diag-row ${severityClass(diag.severity)}`}
      data-testid="diag-row"
      onClick={() => onSelect?.(diag)}
      type="button"
    >
      <span className="diag-code">{diag.code}</span>
      {where && <span className="diag-loc">{where}</span>}
      <span className="diag-msg">{diag.message}</span>
    </button>
  );
}

export function EditorPane({
  text,
  onTextChange,
  onDiagnostics,
  onParamsDetected,
  tabKey = "library:solo",
  knownTabKeys,
  onSelectionChange,
  onRun,
  graphOpen,
  onGraphOpenChange,
  onRunCells,
  onCellsViewChange,
  connected,
  holdAutoSplit,
  onExplainRow,
  cellEvidenceSlot,
  parameters,
}: Props) {
  const editorDiv = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const [diags, setDiags] = useState<Diagnostics[]>([]);
  const [parseMs, setParseMs] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modelsRef = useRef<Map<string, any>>(new Map());
  const viewStatesRef = useRef<Map<string, any>>(new Map());
  const prevKeyRef = useRef<string>(tabKey);
  const textRef = useRef(text);
  textRef.current = text;
  const tabKeyRef = useRef(tabKey);
  tabKeyRef.current = tabKey;
  // S5: per-buffer cell mode (split view with cards vs plain editor).
  const [cellViewOpen, setCellViewOpenRaw] = useState(false);
  // S23-2/S24-1: notify the App on every visibility flip (heartbeat
  // gating). The notify runs in a COMMIT effect — calling it inside the
  // state updater was a render-phase side effect that could be missed
  // (or double-fired under StrictMode), leaving the App's ref stale.
  const onCellsViewChangeRef = useRef(onCellsViewChange);
  onCellsViewChangeRef.current = onCellsViewChange;
  const setCellViewOpen = useCallback(
    (next: boolean | ((v: boolean) => boolean)) => {
      setCellViewOpenRaw(next);
    },
    [],
  );
  useEffect(() => {
    onCellsViewChangeRef.current?.(cellViewOpen);
  }, [cellViewOpen]);
  const hasCellMarkers = useMemo(
    () => splitCells(text).cells.length > 0,
    [text],
  );
  // S7: first-open auto-cellification — once per library (keyed by tab),
  // respects user removal (adopted-and-removed never re-triggers).
  // Muse 3: removal persists across reloads (localStorage) — markers are
  // indistinguishable from hand-authored, so there is no provenance to
  // recover after a reload without this flag.
  const adoptedRef = useRef<Set<string>>(new Set());
  const removedPersisted = new Set<string>(
    JSON.parse(localStorage.getItem("fhir4ds.cleanroom.cellsRemoved") ?? "[]") as string[],
  );
  const removedRef = useRef<Set<string>>(removedPersisted);
  // Muse 5: an explicit in-session close suppresses further auto-opens —
  // PER TAB (a global flag would suppress first-open cellification for
  // every other library this session).
  const userClosedCellsRef = useRef<Set<string>>(new Set());
  const applyCellify = useCallback(() => {
    const next = cellify(textRef.current);
    if (next != null) onTextChangeRef.current(next);
    return next != null;
  }, []);
  useEffect(() => {
    if (!onRunCells) return;
    // S22a: hold while the server handshake is pending OR while the
    // text is the pristine demo default in a connected session — the
    // connected boot-purity pass will REPLACE it with the workspace's
    // first disk library (adopting it first would persist a bogus
    // cellsRemoved entry for the tab, suppressing cellify for the
    // real library).
    if (holdAutoSplit) return;
    if (connected && isPristineDemoDefault(text)) return;
    if (adoptedRef.current.has(tabKey) || removedRef.current.has(tabKey)) return;
    if (hasCellMarkers) {
      // Library arrived WITH markers — count as adopted (hand-authored).
      adoptedRef.current.add(tabKey);
      return;
    }
    if (hasSplittableDefines(text)) {
      if (applyCellify()) {
        adoptedRef.current.add(tabKey);
        if (!userClosedCellsRef.current.has(tabKey)) setCellViewOpen(true);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabKey, hasCellMarkers, onRunCells, holdAutoSplit, text]);
  // Muse 2 (superseded by S7 directive): the toggle now ALWAYS renders —
  // deleting all markers keeps the view open with the empty hint + the
  // Auto-split affordance; adoption marks removed when the user saves a
  // markerless buffer so first-open cellification never fights them.
  // S22a: the connected boot-purity swap (default → disk library) must
  // NOT count as "user saved a markerless buffer" — skip while the text
  // is still the pristine default being replaced.
  useEffect(() => {
    if (holdAutoSplit) return;
    if (connected && isPristineDemoDefault(text)) return;
    if (adoptedRef.current.has(tabKey) && !hasCellMarkers) {
      removedRef.current.add(tabKey);
      localStorage.setItem(
        "fhir4ds.cleanroom.cellsRemoved",
        JSON.stringify([...removedRef.current]),
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasCellMarkers, holdAutoSplit]);
  const onAutoSplit = useCallback(() => {
    if (applyCellify()) setCellViewOpen(true);
  }, [applyCellify]);
  // S16: merged header-row controls for the cell view (Run All / Clear All).
  const [cellControls, setCellControls] = useState<{
    running: boolean;
    canRunAll: boolean;
    hasResults: boolean;
    onRunAll: () => void;
    onClearAll: () => void;
  }>({
    running: false,
    canRunAll: false,
    hasResults: false,
    onRunAll: () => {},
    onClearAll: () => {},
  });

  // S5: per-cell Monaco editors (name -> editor) so the host can splice
  // cell edits back into the master buffer by span.
  const [cellEditors, setCellEditors] = useState<Map<string, any>>(new Map());
  const cellEditorsRef = useRef<Map<string, any>>(new Map());
  cellEditorsRef.current = cellEditors;

  const getOrCreateModel = (key: string) => {
    const monaco = monacoRef.current;
    if (!monaco) return null;
    const uri = monaco.Uri.parse(`inmemory://cql/${key}`);
    let model = monaco.editor.getModel(uri);
    if (!model) {
      model = monaco.editor.createModel(textRef.current, "cql", uri);
      modelsRef.current.set(key, model);
    }
    return model;
  };

  // Extract parameter declarations from the declarations block (parse
  // envelope library_declarations when present; fall back to a light
  // textual scan so the panel stays live even pre-parse).
  const declared = useMemo(() => detectParams(text), [text]);
  useEffect(() => {
    onParamsDetected?.(declared);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [declared.join(",")]);

  // S13 root-cause fix: the plain-editor host is CONDITIONAL (unmounts in
  // cell view). A mount-once effect captured the first div and never
  // re-created the editor when a NEW div mounted after cells->text — the
  // host stayed empty (0 children). Track the CURRENT div identity; the
  // create effect re-runs whenever a new host attaches.
  const [editorHostKey, setEditorHostKey] = useState(0);
  const hostRefCallback = useCallback((el: HTMLDivElement | null) => {
    editorDiv.current = el;
    if (el) setEditorHostKey((k) => k + 1);
  }, []);
  // Latest-callback ref for the mount-only Monaco listener.
  const onTextChangeRef = useRef(onTextChange);
  onTextChangeRef.current = onTextChange;
  const onSelectionChangeRef = useRef(onSelectionChange);
  onSelectionChangeRef.current = onSelectionChange;
  const onRunRef = useRef(onRun);
  onRunRef.current = onRun;
  // Selection presence drives the header button label (Run / Run selection).
  const [selText, setSelText] = useState("");
  // Visual editor step 4 — outline dropdown (symbols + jump-to-define).
  const [outlineOpen, setOutlineOpen] = useState(false);

  useEffect(() => {
    let disposed = false;
    (async () => {
      const monaco = (await import("../lib/monaco-setup")).default;
      const { registerCQLLanguage } = await import("../lib/monaco-cql-language");
      if (disposed || !editorDiv.current) return;
      registerCQLLanguage(monaco);
      monacoRef.current = monaco;
      const model = getOrCreateModel(tabKeyRef.current);
      // S13 Muse: cell-view edits flow through onTextChange but the cached
      // Monaco model is only updated by the [text] sync effect WHILE the
      // editor is mounted — on remount the model may hold stale text. Sync
      // at attach so the editor always shows the current buffer.
      if (model && model.getValue() !== textRef.current) {
        model.setValue(textRef.current);
      }
      const editor = monaco.editor.create(editorDiv.current, {
        model: model ?? undefined,
        value: model ? undefined : textRef.current,
        language: "cql",
        minimap: { enabled: false },
        fontSize: 13,
        automaticLayout: true,
        scrollBeyondLastLine: false,
        tabSize: 2,
        renderWhitespace: "none",
      });
      editor.onDidChangeModelContent(() => {
        // Mount-only listener: route through a ref so the CURRENT
        // onTextChange closure is used (the captured one goes stale on
        // tab switches and would write into the wrong library).
        onTextChangeRef.current(editor.getValue());
      });
      editor.onDidChangeCursorSelection(() => {
        const sel = editor.getSelection();
        const model = editor.getModel();
        const selContent = sel && model ? model.getValueInRange(sel) : "";
        onSelectionChangeRef.current?.(selContent);
        setSelText(selContent);
      });
      editorRef.current = editor;
      editor.addCommand(
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
        () => onRunRef.current?.(),
      );
      // S12: blank-editor-after-cells->text fix. The host REMOUNTS when the
      // cell view closes; the async monaco create can complete before the
      // container has been laid out (height 0) — automaticLayout only
      // observes AFTER creation. Explicit layout() at mount plus a rAF
      // follow-up guarantees the editor renders its model immediately.
      editor.layout();
      requestAnimationFrame(() => {
        if (!disposed) editor.layout();
      });
    })();
    return () => {
      disposed = true;
      editorRef.current?.dispose();
      editorRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorHostKey]);

  // Tab switch: checkpoint the outgoing view state, swap to the
  // incoming model, restore its view state. Content stays in sync via
  // the models themselves (each caches its library's latest text).
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    const prevKey = prevKeyRef.current;
    if (prevKey !== tabKey) {
      viewStatesRef.current.set(prevKey, editor.saveViewState());
      prevKeyRef.current = tabKey;
      setDiags([]);
    }
    const model = getOrCreateModel(tabKey);
    if (model && editor.getModel() !== model) {
      const vs = viewStatesRef.current.get(tabKey);
      editor.setModel(model);
      if (vs) editor.restoreViewState(vs);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tabKey]);

  // Dispose models whose tab no longer exists (library deleted).
  useEffect(() => {
    if (!knownTabKeys || !monacoRef.current) return;
    const live = new Set(knownTabKeys);
    for (const [key, model] of modelsRef.current) {
      if (!live.has(key) && key !== tabKeyRef.current) {
        model.dispose();
        modelsRef.current.delete(key);
        viewStatesRef.current.delete(key);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [knownTabKeys?.join(",")]);

  // Sync external text changes (tab switch, Apply, share, import) into
  // the once-mounted Monaco instance — guarded so user typing (which
  // flows text→state→props) does not reset cursor/scroll position.
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    if (editor.getValue() !== text) {
      const pos = editor.getPosition();
      const reveal = editor.getVisibleRanges()[0]?.top ?? null;
      editor.setValue(text);
      if (pos) {
        editor.setPosition(pos);
        if (reveal != null) editor.setScrollTop(reveal);
      }
    }
  }, [text]);

  // Debounced parse → markers
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const t0 = performance.now();
      const resp = await workerRequest({ type: "parse_cql", text });
      setParseMs(Math.round(performance.now() - t0));
      let env: ParseResult | null = null;
      try {
        env = JSON.parse(resp.envelope);
      } catch {
        return;
      }
      if (!env) return;
      const next = env.diagnostics ?? [];
      setDiags(next);
      onDiagnostics?.(next);
      const monaco = monacoRef.current;
      const editor = editorRef.current;
      if (monaco && editor) {
        monaco.editor.setModelMarkers(
          editor.getModel(),
          "cql-cleanroom",
          next.map((d) => ({
            startLineNumber: d.location?.start_line ?? 1,
            startColumn: (d.location?.start_column ?? 0) + 1,
            endLineNumber: d.location?.end_line ?? d.location?.start_line ?? 1,
            endColumn: (d.location?.end_column ?? (d.location?.start_column ?? 0)) + 1,
            message: `${d.code}: ${d.message}`,
            severity:
              d.severity === "error"
                ? monaco.MarkerSeverity.Error
                : d.severity === "warning"
                  ? monaco.MarkerSeverity.Warning
                  : monaco.MarkerSeverity.Info,
          })),
        );
      }
    }, 400);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const jumpTo = (d: Diagnostics) => {
    const editor = editorRef.current;
    const line = d.location?.start_line;
    if (!editor || !line) return;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: (d.location?.start_column ?? 0) + 1 });
    editor.focus();
  };

  /**
   * S5: splice an edited cell body back into the master buffer by cell
   * ORDER (recompute spans against the CURRENT buffer — bolton
   * spliceCell semantics). The marker line is preserved.
   */
  const spliceCellIntoBuffer = (order: number, newText: string) => {
    const lines = text.split("\n");
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
    if (cellEnd === -1 && cellIdx === order) cellEnd = text.length;
    if (cellStart === -1 || cellEnd === -1) return;
    onTextChange(
      text.slice(0, cellStart) +
        (newText.endsWith("\n") ? newText : newText + "\n") +
        text.slice(cellEnd),
    );
  };

  const jumpToLine = (line: number, name: string) => {
    const editor = editorRef.current;
    if (!editor) return;
    const lineText: string = editor.getModel()?.getLineContent(line) ?? "";
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: Math.max(1, lineText.indexOf(name) + 1) });
    editor.focus();
  };

  interface OutlineRow {
    group: string;
    name: string;
    line: number;
    uses?: number;
    note?: string;
  }
  const outlineGroups = useMemo<Array<{ label: string; rows: OutlineRow[] }>>(() => {
    if (!outlineOpen) return [];
    const syms = extractCqlSymbols(text);
    const withUses = (e: { name: string; line: number }): OutlineRow => ({
      group: "",
      name: e.name,
      line: e.line,
      uses: countReferences(text, e.name, e.line),
    });
    const groups: Array<{ label: string; rows: OutlineRow[] }> = [];
    const add = (label: string, rows: OutlineRow[]) => {
      if (rows.length) groups.push({ label, rows });
    };
    add("Defines", syms.defines.map(withUses));
    add(
      "Functions",
      syms.functions.map(withUses),
    );
    add(
      "Parameters",
      syms.parameters.map(withUses),
    );
    add("Valuesets", syms.valuesets.map((e) => ({ group: "", name: e.name, line: e.line })));
    add("Codesystems", syms.codesystems.map((e) => ({ group: "", name: e.name, line: e.line })));
    add("Codes", syms.codeDecls.map((e) => ({ group: "", name: e.name, line: e.line })));
    add(
      "Includes",
      syms.includes.map((i) => ({
        group: "",
        name: i.name,
        line: i.line,
        note: i.alias !== i.name ? `called ${i.alias}` : undefined,
      })),
    );
    return groups;
  }, [outlineOpen, text]);

  return (
    <section className="pane editor-pane" data-testid="editor-pane">
      <div className="pane-header editor-header cell-mode-header">
        {/* S8 directive 4: Visual editor HIDDEN behind a build flag
            (choice: flag not deletion — the builder machinery may return;
            import.meta.env.VITE_SHOW_VISUAL_EDITOR enables it in dev
            builds only; the product build renders no visual chrome). */}
        {onGraphOpenChange && import.meta.env.VITE_SHOW_VISUAL_EDITOR === "1" && (
          <button
            className="drawer-toggle"
            data-testid="drawer-graph-toggle"
            onClick={() => onGraphOpenChange(!graphOpen)}
          >
            {graphOpen ? "▾" : "▸"} Visual editor
          </button>
        )}
        {onRunCells && cellViewOpen && (
          <div className="editor-actions-cluster" role="group" aria-label="Run actions">
            <button
              type="button"
              className="drawer-toggle"
              data-testid="cell-runall"
              disabled={cellControls.running || !cellControls.canRunAll}
              onClick={cellControls.onRunAll}
              title="Run every cell top-to-bottom (each with its dependency closure)"
            >
              ▶ Run All
            </button>
            {cellControls.hasResults && (
              <button
                type="button"
                className="drawer-toggle"
                data-testid="cell-clearall"
                onClick={cellControls.onClearAll}
                title="Clear all cell outputs"
              >
                ✕ Clear All
              </button>
            )}
          </div>
        )}
        {onRunCells && (
          <button
            className={`drawer-toggle mode-switch${cellViewOpen ? " on" : ""}`}
            data-testid="cell-view-toggle"
            role="switch"
            aria-label="Cell view"
            aria-checked={cellViewOpen}
            disabled={
              cellViewOpen
                ? false
                : !hasCellMarkers && !hasSplittableDefines(text)
            }
            onClick={() =>
              setCellViewOpen((v) => {
                const next = !v;
                if (!next) userClosedCellsRef.current.add(tabKeyRef.current);
                return next;
              })
            }
            title={
              cellViewOpen
                ? "Switch to the plain text editor"
                : hasCellMarkers
                  ? "Switch to the cell-based editor (one card per define)"
                  : hasSplittableDefines(text)
                    ? "Switch to the cell-based editor (Auto-split adds markers)"
                    : "No top-level defines to split"
            }
          >
            {cellViewOpen ? "Text ⇄" : "Cells ⇄"}
          </button>
        )}
        <button
          className="drawer-toggle"
          data-testid="editor-outline"
          title="symbols in this library — click to jump"
          onClick={() => setOutlineOpen((o) => !o)}
        >
          {outlineOpen ? "▾" : "▸"} Outline
        </button>
        {onRun && !(cellViewOpen && onRunCells) && (
          <button
            className="editor-run-btn"
            data-testid="editor-run"
            title={
              selText.trim()
                ? "evaluate the selected expression (Ctrl/Cmd+Enter)"
                : "evaluate the whole library (Ctrl/Cmd+Enter)"
            }
            onClick={() => onRun()}
          >
            {selText.trim() ? "Run selection" : "Run"}
          </button>
        )}
      </div>
      {cellViewOpen && onRunCells ? (
        <CellEditor
          value={text}
          connected={connected ?? false}
          onExplainRow={onExplainRow}
          evidenceSlotFactory={cellEvidenceSlot}
          parameters={parameters}
          onToolbarControls={setCellControls}
          onRunCells={onRunCells}
          onAutoSplit={onAutoSplit}
          renderEditor={(cell, overrideHeight) => (
            <CellMonacoHost
              cellKey={`${tabKey}#cell-${cell.order}`}
              text={cell.text}
              onChange={(v) => spliceCellIntoBuffer(cell.order, v)}
              onMount={(editor) => setCellEditors((m) => new Map(m).set(cell.name, editor))}
              overrideHeight={overrideHeight}
            />
          )}
        />
      ) : (
        <div className="editor-host" data-testid="cql-editor" ref={hostRefCallback} />
      )}
      {outlineOpen && (
        <div
          className="outline-panel"
          data-testid="outline-panel"
          role="listbox"
          onKeyDown={(e) => {
            if (e.key === "Escape") setOutlineOpen(false);
          }}
        >
          {outlineGroups.length === 0 && (
            <p className="pane-hint">No declarations in this library yet.</p>
          )}
          {outlineGroups.map((g) => (
            <div key={g.label} className="outline-group">
              <div className="outline-group-label">{g.label}</div>
              {g.rows.map((r) => (
                <button
                  key={`${g.label}:${r.name}`}
                  className="outline-row"
                  data-testid="outline-item"
                  title={`go to line ${r.line}`}
                  onClick={() => {
                    setOutlineOpen(false);
                    jumpToLine(r.line, r.name);
                  }}
                >
                  <span className="outline-name">{r.name}</span>
                  {r.note && <span className="outline-note">{r.note}</span>}
                  {r.uses != null && (
                    <span className="outline-uses">
                      {r.uses} use{r.uses === 1 ? "" : "s"}
                    </span>
                  )}
                  <span className="outline-line">L{r.line}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
      {diags.length > 0 && (
        <div className="diag-list" data-testid="diag-list">
          {diags.map((d, i) => (
            <DiagnosticsRow key={i} diag={d} onSelect={jumpTo} />
          ))}
        </div>
      )}
      {onGraphOpenChange && graphOpen && import.meta.env.VITE_SHOW_VISUAL_EDITOR === "1" && (
        <div className="drawer-body" data-testid="drawer-graph">
          <p className="pane-hint">
            The builder parses ONE define at a time into an editable
            shape (retrieve + predicates) and splices it back on Apply
            after a parse round-trip. Logic outside the builder grammar
            stays editable as text.
          </p>
          <BuilderPane text={text} onTextChange={onTextChange} />
        </div>
      )}
      {/* REORG 6f.1: execution stats live bottom-right (same convention
          as the console's rows·columns footer). */}
      <span className="pane-meta editor-stat" data-testid="parse-status">
        {diags.length === 0
          ? parseMs != null
            ? `parsed ✓ ${parseMs}ms`
            : "parsing…"
          : `${diags.length} diagnostic${diags.length === 1 ? "" : "s"}`}
      </span>
    </section>
  );
}

/** Light textual scan for `parameter <name> ...` declarations. */
/**
 * S5: one lightweight Monaco instance per cell card. The host owns
 * monaco-setup; edits flow up through onTextChange via the CellEditor's
 * splice machinery — actually, simpler: each cell editor writes its
 * whole value up and the parent splices by cell ORDER against the
 * master buffer (recomputed per render, mirrors bolton spliceCell).
 */
function CellMonacoHost({
  cellKey,
  text,
  onChange,
  onMount,
  overrideHeight,
}: {
  cellKey: string;
  text: string;
  onChange?: (value: string) => void;
  onMount?: (editor: any) => void;
  /** S14: per-cell drag-resize height (px), persisted by the caller. */
  overrideHeight?: number;
}) {
  const divRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<any>(null);
  const textRef = useRef(text);
  textRef.current = text;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const onMountRef = useRef(onMount);
  onMountRef.current = onMount;

  useEffect(() => {
    let disposed = false;
    (async () => {
      const monaco = (await import("../lib/monaco-setup")).default;
      if (disposed || !divRef.current) return;
      const editor = monaco.editor.create(divRef.current, {
        value: textRef.current,
        language: "cql",
        minimap: { enabled: false },
        fontSize: 13,
        automaticLayout: true,
        scrollBeyondLastLine: false,
        tabSize: 2,
        wordWrap: "on",
        renderLineHighlight: "gutter",
        padding: { top: 6 },
      });
      editor.onDidChangeModelContent(() => onChangeRef.current?.(editor.getValue()));
      editorRef.current = editor;
      onMountRef.current?.(editor);
    })();
    return () => {
      disposed = true;
      editorRef.current?.dispose();
      editorRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cellKey]);

  // External text sync (master-buffer changes from other surfaces).
  useEffect(() => {
    const editor = editorRef.current;
    if (editor && editor.getValue() !== text) editor.setValue(text);
  }, [text]);

  // S15: AUTO-FIT — N lines render N*lineHeight + padding exactly; typing
  // grows/shrinks live (recomputed per render from the CURRENT text).
  // Rider: the minimum is ONE line (empty/new cells render a single-line
  // box); 420 cap keeps very long cells on internal scroll.
  const lines = Math.max(1, text.split("\n").length);
  const lineHeight = 19;
  const natural = Math.min(420, Math.max(lineHeight + 16, lines * lineHeight + 16));
  const height = overrideHeight ?? natural;
  return (
    <div
      className="cell-monaco"
      ref={divRef}
      data-testid="cell-monaco"
      style={{ height: `${height}px` }}
    />
  );
}

function detectParams(text: string): string[] {
  const names: string[] = [];
  const re = /^\s*(?:public\s+|private\s+)?parameter\s+"?([A-Za-z][A-Za-z0-9_]*)"?\s/mg;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (!names.includes(m[1])) names.push(m[1]);
  }
  return names;
}
