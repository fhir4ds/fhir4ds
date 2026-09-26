import type { EditorTab } from "../../lib/editorTabs";

/**
 * WORKBENCH_REORG phase 3 — the editor-column tab strip. One tab per
 * open workspace resource; the active tab's host renders below (see
 * hosts.tsx). Library tabs carry their name; others carry the resource
 * label the nav drawer shows.
 */

const KIND_GLYPH: Record<string, string> = {
  library: "📄",
  measure: "📊",
  valueset: "Ⓣ",
  parameter: "P",
  test: "▦",
  expected: "✓",
  view: "👁",
};

export function EditorTabs({
  tabs,
  activeId,
  labels,
  onSelect,
  onClose,
}: {
  tabs: EditorTab[];
  activeId: string | null;
  /** TabId → display label (resolved by the owner from workspace state). */
  labels: Record<string, string>;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
}) {
  if (tabs.length === 0) return null;
  return (
    <div className="editor-tabs" data-testid="editor-tabs" role="tablist">
      {tabs.map((t) => {
        const testId = `editor-tab-${t.kind}-${t.resourceId}`;
        return (
          <div
            key={t.id}
            className={`editor-tab ${t.id === activeId ? "active" : ""}`}
            data-testid={testId}
          >
            <button
              className="editor-tab-btn"
              role="tab"
              aria-selected={t.id === activeId}
              title={labels[t.id] ?? t.id}
              onClick={() => onSelect(t.id)}
            >
              <span className="editor-tab-glyph" aria-hidden>
                {KIND_GLYPH[t.kind] ?? "•"}
              </span>
              <span className="editor-tab-label">{labels[t.id] ?? t.resourceId}</span>
            </button>
            <button
              className="editor-tab-close"
              data-testid={`editor-tab-close-${t.kind}-${t.resourceId}`}
              title="close tab"
              aria-label={`close ${labels[t.id] ?? t.id}`}
              onClick={(e) => {
                e.stopPropagation();
                onClose(t.id);
              }}
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
