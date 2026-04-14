/**
 * WorkspaceLayout: A flexible 3-pane layout with a toggle toolbar.
 * Each pane can be independently shown/hidden. The toggle state is
 * managed externally (in App) so it persists across tab switches.
 */
import { type ReactNode } from "react";

export interface PaneConfig {
  id: string;
  label: string;
  icon: string;
  content: ReactNode;
  /** Optional badge text (e.g. "editable", "read-only") */
  badge?: string;
  /** Optional theme for the badge */
  badgeType?: "default" | "readonly" | "calculated";
}

export interface WorkspaceLayoutProps {
  panes: [PaneConfig, PaneConfig, PaneConfig];
  visiblePanes: Record<string, boolean>;
  onTogglePane: (paneId: string) => void;
  footer?: ReactNode;
}

export function WorkspaceLayout({
  panes,
  visiblePanes,
  onTogglePane,
  footer,
}: WorkspaceLayoutProps) {
  const activePanes = panes.filter((p) => visiblePanes[p.id] !== false);
  const colCount = activePanes.length;

  return (
    <div className="workspace">
      {/* Toggle toolbar */}
      <div className="workspace-toolbar" data-testid="workspace-toolbar">
        {panes.map((pane) => {
          const isActive = visiblePanes[pane.id] !== false;
          return (
            <button
              key={pane.id}
              className={`workspace-toggle${isActive ? " workspace-toggle--active" : ""}`}
              onClick={() => onTogglePane(pane.id)}
              title={`${isActive ? "Hide" : "Show"} ${pane.label}`}
              data-testid={`toggle-${pane.id}`}
            >
              <span className="workspace-toggle-icon">{pane.icon}</span>
              <span className="workspace-toggle-label">{pane.label}</span>
            </button>
          );
        })}
      </div>

      {/* Pane grid */}
      <div
        className="workspace-grid"
        style={{
          gridTemplateColumns: colCount > 0 ? `repeat(${colCount}, 1fr)` : "1fr",
        }}
      >
        {activePanes.map((pane) => (
          <div key={pane.id} className="workspace-pane" data-testid={`pane-${pane.id}`}>
            <div className="pane-header">
              <span className="pane-title">{pane.label}</span>
              {pane.badge && (
                <span className={`pane-badge ${pane.badgeType || ""}`}>
                  {pane.badge}
                </span>
              )}
            </div>
            <div className="workspace-pane-body">{pane.content}</div>
          </div>
        ))}
        {colCount === 0 && (
          <div className="workspace-empty">
            <p>All panels are hidden. Use the toolbar above to show a panel.</p>
          </div>
        )}
      </div>

      {/* Footer (Results Table) spans full width */}
      {footer && <div className="workspace-footer">{footer}</div>}
    </div>
  );
}
