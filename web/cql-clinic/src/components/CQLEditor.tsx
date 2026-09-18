import { useEffect, useRef, useState } from "react";
import Editor, { DiffEditor, type OnMount, type DiffOnMount, type BeforeMount } from "@monaco-editor/react";
import type * as MonacoEditor from "monaco-editor";
import { registerCQLLanguage } from "../lib/monaco-cql-language";
import { fixMonacoInputArea } from "../lib/monaco-shadow-fix";

type Monaco = typeof MonacoEditor;

interface Props {
  value: string;
  onChange: (next: string) => void;
  /** Reference solution CQL compared via the diff toggle / loaded via the footer. */
  solution: string;
}

const beforeMount: BeforeMount = (monaco: Monaco) => {
  registerCQLLanguage(monaco as any);
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

export default function CQLEditor({ value, onChange, solution }: Props) {
  const [compare, setCompare] = useState(false);
  const [confirmLoad, setConfirmLoad] = useState(false);
  const editorRef = useRef<MonacoEditor.editor.IStandaloneCodeEditor | null>(null);
  const diffRef = useRef<MonacoEditor.editor.IStandaloneDiffEditor | null>(null);

  // Both layers stay mounted, so the revealed one was laid out while
  // display:none — its geometry is stale (worst inside the web component's
  // shadow DOM, where the diff editor's gutter overflows onto the footer and
  // swallows clicks). Force a relayout on whichever editor becomes visible.
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      (compare ? diffRef.current : editorRef.current)?.layout();
    });
    return () => cancelAnimationFrame(id);
  }, [compare]);

  const handleEditorMount: OnMount = (editor) => {
    editorRef.current = editor;
    fixMonacoInputArea(editor as any);
  };

  const handleDiffMount: DiffOnMount = (diffEditor) => {
    diffRef.current = diffEditor;
  };

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
            onMount={handleEditorMount}
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
            onMount={handleDiffMount}
            options={{
              ...editorOptions,
              readOnly: true,
              renderOverviewRuler: false,
              // Inline (GitHub-style) diff: the editor pane is ~half the
              // clinic width, and side-by-side panes that narrow wrap long
              // CQL lines at different points, so the two sides drift out
              // of visual sync. Inline keeps removed/added rows stacked.
              renderSideBySide: false,
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
      </div>
    </div>
  );
}
