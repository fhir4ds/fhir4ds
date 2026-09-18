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
}

const beforeMount: BeforeMount = (monaco: Monaco) => {
  registerCQLLanguage(monaco as any);
};

const onMount: OnMount = (editor) => {
  fixMonacoInputArea(editor as any);
};

export default function CQLEditor({ value, onChange, solution }: Props) {
  const [showSolution, setShowSolution] = useState(false);
  const [confirmLoad, setConfirmLoad] = useState(false);

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
        <button className="btn btn-ghost" onClick={() => { setShowSolution((s) => !s); setConfirmLoad(false); }}>
          {showSolution ? "Hide solution" : "Show solution"}
        </button>
        <button className="btn btn-ghost" onClick={handleLoadSolution}>
          {confirmLoad ? "Overwrite editor with solution?" : "Load solution"}
        </button>
      </div>
      {/* Solution drawer renders BELOW the footer in normal flow — buttons
          stay visible and clickable; the editor shrinks instead of being
          overlaid. */}
      {showSolution && (
        <div className="editor-drawer">
          <div className="drawer-header">
            <span>Solution</span>
            <button className="drawer-close" onClick={() => setShowSolution(false)} aria-label="Close solution">×</button>
          </div>
          <pre className="drawer-body">{solution}</pre>
        </div>
      )}
    </div>
  );
}
