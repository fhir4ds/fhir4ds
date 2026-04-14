import Editor from "@monaco-editor/react";
import { fixMonacoInputArea } from "../lib/monaco-shadow-fix";

interface SQLOutputProps {
  value: string;
}

export function SQLOutput({ value }: SQLOutputProps) {
  return (
    <div className="editor-pane">
      <div className="pane-body">
        <Editor
          language="sql"
          theme="vs-dark"
          value={value}
          onMount={fixMonacoInputArea}
          options={{
            readOnly: true,
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily: "var(--font-mono)",
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            wordWrap: "on",
            padding: { top: 8 },
            renderLineHighlight: "none",
            automaticLayout: true,
            domReadOnly: true,
          }}
        />
      </div>
    </div>
  );
}
