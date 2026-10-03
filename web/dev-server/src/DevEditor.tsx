/**
 * DevEditor — local editor wrapper for the dev-server UI.
 *
 * Same Monaco setup as the reused CQLEditor (language, theme, options,
 * shadow-DOM fix) plus v2 cell affordances:
 *  - `on # %% [name: X]` marker lines get a colored left border + subtle
 *    background via Monaco deltaDecorations so cells are visible IN the code.
 *  - exposes an imperative `insertCell()` used by the toolbar "+ cell"
 *    button to append a marker + define skeleton.
 */

import { useCallback, useEffect, useRef } from "react";
import Editor from "@monaco-editor/react";
import { fixMonacoInputArea } from "@wasm-demo/lib/monaco-shadow-fix";
import type * as MonacoEditor from "monaco-editor";

const MARKER = /^\s*\/\/\s*#\s*%%/;

interface DevEditorHandle {
  insertCell: () => void;
}

interface DevEditorProps {
  value: string;
  onChange: (value: string) => void;
  registerHandle?: (h: DevEditorHandle) => void;
}

export function DevEditor({ value, onChange, registerHandle }: DevEditorProps) {
  const editorRef = useRef<MonacoEditor.editor.IStandaloneCodeEditor | null>(
    null,
  );
  const monacoRef = useRef<typeof MonacoEditor | null>(null);
  const decorationsRef = useRef<MonacoEditor.editor.IEditorDecorationsCollection | null>(
    null,
  );

  const recompute = useCallback(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    const model = editor.getModel();
    if (!model) return;
    const markers: MonacoEditor.editor.IModelDeltaDecoration[] = [];
    const lineCount = model.getLineCount();
    for (let line = 1; line <= lineCount; line++) {
      if (MARKER.test(model.getLineContent(line))) {
        markers.push({
          range: new monaco.Range(line, 1, line, 1),
          options: {
            isWholeLine: true,
            className: "dev-cell-marker",
            linesDecorationsClassName: "dev-cell-marker-glyph",
          },
        });
      }
    }
    if (decorationsRef.current) {
      decorationsRef.current.set(markers);
    } else {
      decorationsRef.current = editor.createDecorationsCollection(markers);
    }
  }, []);

  // Recompute decorations whenever the buffer changes.
  useEffect(() => {
    recompute();
  }, [value, recompute]);

  const insertCell = useCallback(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const model = editor.getModel();
    if (!model) return;
    // Append at end of file, before any trailing blank lines.
    let last = model.getLineCount();
    while (last > 1 && model.getLineContent(last).trim() === "") last -= 1;
    const col = model.getLineMaxColumn(last);
    const pos = { lineNumber: last, column: col };
    const needsNl = model.getValue().trim() !== "";
    const skeleton = `${needsNl ? "\n\n" : ""}// # %%\ndefine NewCell: 'TODO'`;
    editor.executeEdits("dev-add-cell", [
      {
        range: new (monacoRef.current!.Range)(
          pos.lineNumber,
          col,
          pos.lineNumber,
          col,
        ),
        text: skeleton,
      },
    ]);
    editor.focus();
  }, []);

  useEffect(() => {
    registerHandle?.({ insertCell });
  }, [insertCell, registerHandle]);

  return (
    <div className="editor-pane">
      <div className="pane-body">
        <Editor
          language="sql"
          theme="vs-dark"
          value={value}
          onChange={(v) => onChange(v ?? "")}
          onMount={(editor, monaco) => {
            fixMonacoInputArea(editor);
            editorRef.current = editor;
            monacoRef.current = monaco;
            recompute();
          }}
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
  );
}

export type { DevEditorHandle };
