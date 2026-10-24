/**
 * Diagnostics list: code + severity + message cards (design §4).
 */

import type { Diagnostic } from "../lib/protocol";

export function DiagnosticsList({ diagnostics }: { diagnostics: Diagnostic[] }) {
  if (!diagnostics.length) {
    return <div className="empty-hint">No diagnostics.</div>;
  }
  return (
    <div data-testid="diagnostics-list">
      {diagnostics.map((d, i) => (
        <div key={i} className="diagnostic-card">
          <div className="diag-code">
            {d.code}
            {d.severity ? ` · ${d.severity}` : ""}
          </div>
          <div className="diag-message">{d.message}</div>
        </div>
      ))}
    </div>
  );
}
