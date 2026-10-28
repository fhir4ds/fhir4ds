import { useCallback, useEffect, useState } from "react";
import {
  browseFolders,
  type BrowseEntry,
} from "../lib/workspaceBrowser";
import { Spinner } from "./Spinner";

/**
 * S32: server-side folder picker for Open Workspace / Save Workspace
 * (connected mode). Browses /api/fs/browse roots; directories that
 * carry a workspace layout are selectable (Open) or targetable (Save).
 */
export function WorkspaceFolderModal({
  mode,
  onClose,
  onPick,
}: {
  mode: "open" | "save";
  onClose: () => void;
  onPick: (path: string, name: string) => void;
}) {
  const [entries, setEntries] = useState<BrowseEntry[]>([]);
  const [path, setPath] = useState<string | null>(null);
  const [parent, setParent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<BrowseEntry | null>(null);

  const load = useCallback((p?: string) => {
    setLoading(true);
    setError(null);
    setSelected(null);
    browseFolders(p)
      .then((r) => {
        setEntries(r.entries ?? []);
        setPath(r.path ?? null);
        setParent(r.parent ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const canConfirm =
    mode === "open"
      ? Boolean(selected?.workspace)
      : Boolean(path); // save: any browsable folder is a valid target

  return (
    <div
      className="modal-backdrop"
      data-testid="workspace-folder-modal"
      role="dialog"
      aria-label={mode === "open" ? "Open workspace folder" : "Save workspace package"}
    >
      <div className="modal-card workspace-folder-modal">
        <header className="modal-head">
          <span className="modal-title">
            {mode === "open" ? "Open Workspace" : "Save Workspace"}
          </span>
          <button
            type="button"
            className="footer-dismiss"
            aria-label="close"
            data-testid="workspace-folder-close"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="modal-path" data-testid="workspace-folder-path">
          {path ?? "Choose a starting location"}
        </div>
        {error && (
          <p className="pane-error" data-testid="workspace-folder-error">
            {error}
          </p>
        )}
        <div className="folder-list" data-testid="workspace-folder-list">
          {loading ? (
            <div className="nav-empty">
              <Spinner label="loading folders" />
            </div>
          ) : (
            <>
              {parent && (
                <button
                  type="button"
                  className="folder-row folder-up"
                  data-testid="workspace-folder-up"
                  onDoubleClick={() => load(parent)}
                  onClick={() => load(parent)}
                >
                  ↰ ..
                </button>
              )}
              {entries.map((e) => (
                <button
                  type="button"
                  key={e.path}
                  className={`folder-row${selected?.path === e.path ? " selected" : ""}`}
                  data-testid={`workspace-folder-entry-${e.name}`}
                  data-workspace={e.workspace ? "true" : undefined}
                  onClick={() => setSelected(e)}
                  onDoubleClick={() => {
                    if (mode === "open" && e.workspace) {
                      onPick(e.path, e.name);
                    } else {
                      load(e.path);
                    }
                  }}
                >
                  <span className="folder-glyph">📁</span>
                  <span className="folder-name">{e.name}</span>
                  {e.workspace && (
                    <span className="nav-item-pill">workspace</span>
                  )}
                </button>
              ))}
              {entries.length === 0 && !parent && (
                <p className="pane-hint">no subdirectories</p>
              )}
            </>
          )}
        </div>
        <footer className="modal-actions">
          <button
            type="button"
            className="settings-button"
            onClick={onClose}
          >
            Cancel
          </button>
          {mode === "open" ? (
            <button
              type="button"
              className="settings-button primary"
              disabled={!canConfirm}
              title={
                selected && !selected.workspace
                  ? "not a workspace (no cql/ or Library/)"
                  : undefined
              }
              onClick={() => {
                if (selected?.workspace) onPick(selected.path, selected.name);
                else if (selected) load(selected.path);
              }}
            >
              {selected && !selected.workspace ? "Browse" : "Open Workspace"}
            </button>
          ) : (
            <button
              type="button"
              className="settings-button primary"
              disabled={!canConfirm}
              onClick={() => {
                if (path) onPick(path, path.split("/").pop() ?? path);
              }}
            >
              Save Here
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
