import { useState } from "react";
import Editor, { type OnMount, type BeforeMount } from "@monaco-editor/react";
import type * as MonacoEditor from "monaco-editor";
import { registerCQLLanguage } from "../lib/monaco-cql-language";
import { fixMonacoInputArea } from "../lib/monaco-shadow-fix";

type Monaco = typeof MonacoEditor;

interface Props {
  value: string;
  onChange: (next: string) => void;
  /** Reference solution CQL shown/loaded via the pane footer. */
  solution: string;
  /** Translate the current editor content on demand (View generated SQL). */
  onTranslate: () => Promise<{ sql: string; timeMs: number } | null>;
}

const beforeMount: BeforeMount = (monaco: Monaco) => {
  registerCQLLanguage(monaco as any);
};

const onMount: OnMount = (editor) => {
  fixMonacoInputArea(editor as any);
};

export default function CQLEditor({ value, onChange, solution, onTranslate }: Props) {
  const [showSolution, setShowSolution] = useState(false);
  const [confirmLoad, setConfirmLoad] = useState(false);
  const [showSql, setShowSql] = useState(false);
  const [sqlText, setSqlText] = useState<string | null>(null);
  const [sqlTimeMs, setSqlTimeMs] = useState<number | null>(null);
  const [translating, setTranslating] = useState(false);

  const handleLoadSolution = () => {
    if (value.trim() === solution.trim()) {
      onChange(solution);
      setConfirmLoad(false);
      return;
    }
    if (confirmLoad) {
      onChange(solution);
      setConfirmLoad(false);
      setShowSolution(false);
    } else {
      setConfirmLoad(true);
    }
  };

  /** Re-translate the CURRENT editor content on every click — this is the
   *  "refresh for changes" affordance: edit CQL, click again, see new SQL. */
  const handleViewSql = async () => {
    if (showSql) {
      setShowSql(false);
      return;
    }
    setShowSolution(false);
    setTranslating(true);
    const result = await onTranslate();
    setTranslating(false);
    if (result) {
      setSqlText(result.sql);
      setSqlTimeMs(result.timeMs);
      setShowSql(true);
    }
  };

  return (
    <div className="panel editor">
      <div className="editor-body">
        <Editor
          theme="cql-dark"
          defaultLanguage="cql"
          value={value}
          beforeMount={beforeMount}
          onMount={onMount}
          onChange={(v) => onChange(v ?? "")}
          options={{
            fontSize: 14,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            automaticLayout: true,
            tabSize: 2,
            wordWrap: "on",
            padding: { top: 12, bottom: 12 },
          }}
        />
      </div>
      <div className="editor-footer">
        <button className="btn btn-ghost" onClick={() => { setShowSolution((s) => !s); setConfirmLoad(false); if (!showSolution) setShowSql(false); }}>
          {showSolution ? "Hide solution" : "Show solution"}
        </button>
        <button className="btn btn-ghost" onClick={handleLoadSolution}>
          {confirmLoad ? "Overwrite editor with solution?" : "Load solution"}
        </button>
        {/* View generated SQL hidden pending fix — do not ship broken button.
<button className="btn btn-ghost" onClick={handleViewSql} disabled={translating}>
          {translating ? "Translating…" : showSql ? "Hide generated SQL" : "View generated SQL"}
        </button> */}
      </div>
      {/* Drawers render BELOW the footer in normal flow — buttons stay
          visible and clickable; the editor shrinks instead of being
          overlaid. Only one drawer at a time. */}
      {showSolution && (
        <div className="editor-drawer">
          <div className="drawer-header">
            <span>Solution</span>
            <button className="drawer-close" onClick={() => setShowSolution(false)} aria-label="Close solution">×</button>
          </div>
          <pre className="drawer-body">{solution}</pre>
        </div>
      )}
      {false && showSql && (
        <div className="editor-drawer">
          <div className="drawer-header">
            <span>Generated SQL{sqlTimeMs !== null ? ` · ${sqlTimeMs?.toFixed(1)} ms` : ""}</span>
            <button className="drawer-close" onClick={() => setShowSql(false)} aria-label="Close SQL">×</button>
          </div>
          <pre className="drawer-body">{sqlText ?? "-- Translate to see SQL"}</pre>
        </div>
      )}
    </div>
  );
}
