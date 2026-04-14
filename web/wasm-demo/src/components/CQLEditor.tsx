import Editor from "@monaco-editor/react";
import { fixMonacoInputArea } from "../lib/monaco-shadow-fix";

interface CQLEditorProps {
  value: string;
  onChange: (value: string) => void;
}

export function CQLEditor({ value, onChange }: CQLEditorProps) {
  return (
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
  );
}
