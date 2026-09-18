import { useState } from "react";
import Editor, { DiffEditor, type OnMount, type BeforeMount } from "@monaco-editor/react";
import type * as MonacoEditor from "monaco-editor";
import { registerCQLLanguage } from "../lib/monaco-cql-language";
import { fixMonacoInputArea } from "../lib/monaco-shadow-fix";

type Monaco = typeof MonacoEditor;

interface Props {
  value: string;
  onChange: (next: string) => void;
  /** Reference solution CQL compared via the diff toggle / loaded via the footer. */
  solution: string;
  /** Last run's timings, shown right-aligned in the footer. */
  translateTimeMs: number | null;
  executionTimeMs: number | null;
}

const beforeMount: BeforeMount = (monaco: Monaco) => {
  registerCQLLanguage(monaco as any);
};

const onMount: OnMount = (editor) => {
  fixMonacoInputArea(editor as any);
};

const editorOptions = {
  fontSize: 14,
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  automaticLayout: true,
  tabSize: 2,
  wordWrap: "on",
  padding: { top: 12, bottom: 12 },
} as const;

export default function CQLEditor({ value, onChange, solution, translateTimeMs, executionTimeMs }: Props) {
  const [compare, setCompare] = useState(false);
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
      setCompare(false);
    } else {
      setConfirmLoad(true);
    }
  };

  return (
    <div className="panel editor">
      {/* Both editors stay mounted; layers toggle visibility. Unmounting a
          DiffEditor and remounting a plain Editor races Monaco's model
          disposal ("TextModel got disposed before DiffEditorWidget model got
          reset") and leaves the restored editor without an input area. */}
      <div className="editor-body">
        <div className={`editor-layer${compare ? " editor-layer--hidden" : ""}`}>
          <Editor
            theme="cql-dark"
            defaultLanguage="cql"
            value={value}
            beforeMount={beforeMount}
            onMount={onMount}
            onChange={(v) => onChange(v ?? "")}
            options={editorOptions}
          />
        </div>
        <div className={`editor-layer${compare ? "" : " editor-layer--hidden"}`}>
          <DiffEditor
            theme="cql-dark"
            language="cql"
            original={solution}
            modified={value}
            beforeMount={beforeMount}
            options={{
              ...editorOptions,
              readOnly: true,
              renderOverviewRuler: false,
              renderSideBySide: true,
              originalEditable: false,
            }}
          />
        </div>
      </div>
      <div className="editor-footer">
        <button
          className={`btn btn-ghost${compare ? " btn-ghost--active" : ""}`}
          onClick={() => { setCompare((c) => !c); setConfirmLoad(false); }}
        >
          {compare ? "← Back to editor" : "Compare with solution"}
        </button>
        <button className="btn btn-ghost" onClick={handleLoadSolution}>
          {confirmLoad ? "Overwrite editor with solution?" : "Load solution"}
        </button>
        {translateTimeMs !== null && executionTimeMs !== null && (
          <span className="meta editor-footer__timings" title="last run — auto-runs 1.2s after you stop typing">
            translated {translateTimeMs.toFixed(1)} ms · executed {executionTimeMs.toFixed(1)} ms
          </span>
        )}
      </div>
    </div>
  );
}
