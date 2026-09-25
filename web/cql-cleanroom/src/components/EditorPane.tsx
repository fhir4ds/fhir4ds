import { useEffect, useMemo, useRef, useState } from "react";
import { workerRequest } from "./BootOverlay";
import type { Diagnostics, ParseResult } from "../lib/protocol";

/**
 * C1-U5: Monaco CQL editor with live diagnostics.
 *
 * - parse_cql on a 400ms debounce; Diagnostics.location → Monaco markers
 * - declarations block → parameter panel (values kept client-side and
 *   forwarded as default parameter bindings at evaluation time)
 * - data-testids for the e2e suite (editor, marker, params)
 */

export interface ParamBinding {
  name: string;
  value: string;
}

interface Props {
  text: string;
  onTextChange: (text: string) => void;
  onDiagnostics?: (diags: Diagnostics[]) => void;
  onParamsDetected?: (names: string[]) => void;
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
}: Props) {
  const editorDiv = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const [diags, setDiags] = useState<Diagnostics[]>([]);
  const [parseMs, setParseMs] = useState<number | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Extract parameter declarations from the declarations block (parse
  // envelope library_declarations when present; fall back to a light
  // textual scan so the panel stays live even pre-parse).
  const declared = useMemo(() => detectParams(text), [text]);
  useEffect(() => {
    onParamsDetected?.(declared);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [declared.join(",")]);

  // Monaco mount (once)
  // Latest-callback ref for the mount-only Monaco listener.
  const onTextChangeRef = useRef(onTextChange);
  onTextChangeRef.current = onTextChange;

  useEffect(() => {
    let disposed = false;
    (async () => {
      const monaco = (await import("../lib/monaco-setup")).default;
      const { registerCQLLanguage } = await import("../lib/monaco-cql-language");
      if (disposed || !editorDiv.current) return;
      registerCQLLanguage(monaco);
      const editor = monaco.editor.create(editorDiv.current, {
        value: text,
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
      editorRef.current = editor;
      monacoRef.current = monaco;
    })();
    return () => {
      disposed = true;
      editorRef.current?.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  return (
    <section className="pane editor-pane" data-testid="editor-pane">
      <div className="pane-header">
        <h2>Library</h2>
        <span className="pane-meta" data-testid="parse-status">
          {diags.length === 0
            ? parseMs != null
              ? `parsed ✓ ${parseMs}ms`
              : "parsing…"
            : `${diags.length} diagnostic${diags.length === 1 ? "" : "s"}`}
        </span>
      </div>
      <div className="editor-host" data-testid="cql-editor" ref={editorDiv} />
      {diags.length > 0 && (
        <div className="diag-list" data-testid="diag-list">
          {diags.map((d, i) => (
            <DiagnosticsRow key={i} diag={d} onSelect={jumpTo} />
          ))}
        </div>
      )}
    </section>
  );
}

/** Light textual scan for `parameter <name> ...` declarations. */
function detectParams(text: string): string[] {
  const names: string[] = [];
  const re = /^\s*(?:public\s+|private\s+)?parameter\s+"?([A-Za-z][A-Za-z0-9_]*)"?\s/mg;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (!names.includes(m[1])) names.push(m[1]);
  }
  return names;
}
