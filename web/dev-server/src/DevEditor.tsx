/**
 * DevEditor — local editor wrapper for the dev-server UI (v3, ux2 polish).
 *
 * Same Monaco setup as the reused CQLEditor (language, theme, options,
 * shadow-DOM fix) plus cell affordances:
 *  - `// # %%` marker lines get a stronger blue wash + left border via
 *    decorations, and a 24px glyph-margin gutter area; the cell NAME is
 *    rendered as a margin widget aligned to the marker line (fix 4).
 *  - custom theme `dev-cql`: string tokens render straw/orange (red is
 *    reserved for errors only — the stock sql theme renders strings red).
 *  - imperative `insertCell()` used by the toolbar "+ cell" button.
 */

import { useCallback, useEffect, useRef } from "react";
import Editor from "@monaco-editor/react";
import { fixMonacoInputArea } from "@wasm-demo/lib/monaco-shadow-fix";
import type * as MonacoEditor from "monaco-editor";

const MARKER = /^\s*\/\/\s*#\s*%%/;
const DEFINE_ANYWHERE = /^\s*define\s+(function\s+)?([A-Za-z0-9_]+)\s*[(:]/m;

interface DevEditorHandle {
  insertCell: () => void;
}

interface DevEditorProps {
  value: string;
  onChange: (value: string) => void;
  registerHandle?: (h: DevEditorHandle) => void;
}

let themeDefined = false;

function defineDevTheme(monaco: typeof MonacoEditor) {
  if (themeDefined) return;
  themeDefined = true;
  monaco.editor.defineTheme("dev-cql", {
    base: "vs-dark",
    inherit: true,
    rules: [
      // Fix 4: strings = neutral straw/orange; red stays error-only.
      { token: "string", foreground: "ce9178" },
      { token: "string.sql", foreground: "ce9178" },
      { token: "string.quote", foreground: "ce9178" },
      { token: "string.value", foreground: "d7ba7d" },
      { token: "keyword", foreground: "569cd6" },
      { token: "comment", foreground: "6a9955", fontStyle: "italic" },
    ],
    colors: {},
  });
}

export function DevEditor({ value, onChange, registerHandle }: DevEditorProps) {
  const editorRef = useRef<MonacoEditor.editor.IStandaloneCodeEditor | null>(
    null,
  );
  const monacoRef = useRef<typeof MonacoEditor | null>(null);
  const decorationsRef = useRef<MonacoEditor.editor.IEditorDecorationsCollection | null>(
    null,
  );
  const nameWidgetRefs = useRef<
    { id: string; widget: MonacoEditor.editor.IContentWidget }[]
  >([]);

  const recompute = useCallback(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    const model = editor.getModel();
    if (!model) return;
    const markers: MonacoEditor.editor.IModelDeltaDecoration[] = [];
    const names: { line: number; name: string }[] = [];
    const lineCount = model.getLineCount();
    for (let line = 1; line <= lineCount; line++) {
      if (MARKER.test(model.getLineContent(line))) {
        markers.push({
          range: new monaco.Range(line, 1, line, 1),
          options: {
            isWholeLine: true,
            className: "dev-cell-marker",
          },
        });
        // Cell name: derive from the first define after the marker.
        let name = "";
        for (let l = line + 1; l <= Math.min(lineCount, line + 5); l++) {
          const m = DEFINE_ANYWHERE.exec(model.getLineContent(l));
          if (m?.[2]) {
            name = m[2];
            break;
          }
        }
        names.push({ line, name });
      }
    }
    if (decorationsRef.current) {
      decorationsRef.current.set(markers);
    } else {
      decorationsRef.current = editor.createDecorationsCollection(markers);
    }
    // Refresh name widgets (content widgets aligned to marker lines).
    for (const { widget } of nameWidgetRefs.current) {
      editor.removeContentWidget(widget);
    }
    nameWidgetRefs.current = names.map(({ line, name }) => {
      const id = `dev-cell-name-${line}`;
      const domNode = document.createElement("div");
      domNode.className = "dev-cell-name-gutter";
      domNode.textContent = name;
      const widget: MonacoEditor.editor.IContentWidget = {
        getId: () => id,
        getDomNode: () => domNode,
        getPosition: () => ({
          position: { lineNumber: line, column: 1 },
          preference: [
            monacoRef.current!.editor.ContentWidgetPositionPreference.EXACT,
          ],
        }),
      };
      editor.addContentWidget(widget);
      return { id, widget };
    });
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
          theme="dev-cql"
          value={value}
          onChange={(v) => onChange(v ?? "")}
          onMount={(editor, monaco) => {
            fixMonacoInputArea(editor);
            defineDevTheme(monaco);
            monaco.editor.setTheme("dev-cql");
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
            glyphMargin: true,
          }}
        />
      </div>
    </div>
  );
}

export type { DevEditorHandle };
