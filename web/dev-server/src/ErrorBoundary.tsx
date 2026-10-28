import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  app?: string;
}

interface State {
  error: Error | null;
}

/**
 * Top-level crash boundary: renders a readable panel with a reload
 * button instead of a blank screen when the app throws during render.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[${this.props.app ?? "app"}] render crash:`, error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          style={{
            margin: "40px auto",
            maxWidth: 640,
            padding: "20px 24px",
            background: "#1e1e1e",
            border: "1px solid #f14c4c",
            borderRadius: 8,
            color: "#d4d4d4",
            fontFamily: "monospace",
            fontSize: 13,
            lineHeight: 1.5,
          }}
        >
          <h2 style={{ marginTop: 0, color: "#f14c4c", fontSize: 16 }}>
            Something broke while rendering{this.props.app ? ` (${this.props.app})` : ""}
          </h2>
          <p style={{ whiteSpace: "pre-wrap", wordBreak: "break-word", margin: "10px 0" }}>
            {this.state.error.message || String(this.state.error)}
          </p>
          <button
            type="button"
            className="dev-errorboundary-reload"
            onClick={() => window.location.reload()}
            style={{
              marginTop: 8,
              padding: "6px 14px",
              background: "#094771",
              color: "#fff",
              border: "none",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
