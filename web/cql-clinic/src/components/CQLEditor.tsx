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
  /** True while a run is executing (disables the Run button). */
  running: boolean;
  /** Run & Check now — skips the auto-run debounce. */
  onRun: () => void;
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

export default function CQLEditor({ value, onChange, solution, running, onRun }: Props) {
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
        <button className="btn btn-run" onClick={onRun} disabled={running}>
          {running ? "Running…" : "▶ Run & Check"}
        </button>
        <button
          className={`btn btn-ghost${compare ? " btn-ghost--active" : ""}`}
          onClick={() => { setCompare((c) => !c); setConfirmLoad(false); }}
        >
          {compare ? "← Back to editor" : "Compare with solution"}
        </button>
        <button className="btn btn-ghost" onClick={handleLoadSolution}>
          {confirmLoad ? "Overwrite editor with solution?" : "Load solution"}
        </button>
      </div>
    </div>
  );
}
