import Editor from "@monaco-editor/react";
import { fixMonacoInputArea } from "../../lib/monaco-shadow-fix";

interface QuestionnaireEditorProps {
  value: string;
  onChange: (value: string) => void;
  error?: string | null;
}

export function QuestionnaireEditor({ value, onChange, error }: QuestionnaireEditorProps) {
  return (
    <div className="editor-pane sdc-editor-pane">
      {error && (
        <div className="sdc-editor-error">
          <span className="sdc-editor-error-icon">⚠</span>
          {error}
        </div>
      )}
      <div className="pane-body">
        <Editor
          language="json"
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
            tabSize: 2,
            formatOnPaste: true,
          }}
        />
      </div>
    </div>
  );
}
