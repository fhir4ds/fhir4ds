import { useEffect, useRef, useState } from "react";

/**
 * WorkspacePicker (S22a / AM1): workspaces are DIRECTORIES. Connected
 * mode lists the server-known workspaces (`GET /api/workspaces`) and
 * switches via `POST /api/workspace/switch` (server re-roots the
 * watcher, rebuilds the kernel, bumps the mode nonce). Switching
 * reloads the app so every drawer re-reads the new workspace — the
 * same reload the /api/mode handshake nonce change signals.
 */

export interface WorkspaceInfo {
  name: string;
  path?: string;
  active?: boolean;
  library_count?: number;
}

export async function listWorkspaces(): Promise<WorkspaceInfo[]> {
  try {
    const res = await fetch("/api/workspaces");
    if (!res.ok) return [];
    const body = (await res.json()) as {
      data?: { workspaces?: WorkspaceInfo[] };
    } & { workspaces?: WorkspaceInfo[] };
    return (body?.data ?? body)?.workspaces ?? [];
  } catch {
    return [];
  }
}

export async function switchWorkspace(
  name: string,
): Promise<{ ok: boolean; message: string }> {
  try {
    const res = await fetch("/api/workspace/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: name }),
    });
    const body = (await res.json()) as {
      data?: { ok?: boolean; status?: string; diagnostics?: { message?: string }[] };
      ok?: boolean;
      status?: string;
      diagnostics?: { message?: string }[];
    };
    const d = body?.data ?? body;
    if (d?.ok === false) {
      return {
        ok: false,
        message: d?.diagnostics?.[0]?.message ?? "switch failed",
      };
    }
    return { ok: true, message: d?.status ?? "switched" };
  } catch (e) {
    return { ok: false, message: e instanceof Error ? e.message : String(e) };
  }
}

export function WorkspacePicker({
  activeName,
  onSwitched,
}: {
  /** Current workspace name from the /api/mode handshake. */
  activeName: string;
  /** Fired after a successful switch (App decides reload timing). */
  onSwitched: (name: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<WorkspaceInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void listWorkspaces().then((ws) => {
      if (!cancelled) setItems(ws);
    });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const pick = async (name: string) => {
    if (name === activeName || busy) return;
    setBusy(name);
    setError(null);
    const r = await switchWorkspace(name);
    if (!r.ok) {
      setError(r.message);
      setBusy(null);
      return;
    }
    onSwitched(name);
  };

  return (
    <div className="ws-picker" ref={rootRef} data-testid="workspace-picker-root">
      <button
        type="button"
        className="settings-button ws-picker-button"
        data-testid="workspace-picker"
        title="Switch workspace directory"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="ws-picker-icon" aria-hidden="true">◧</span>{" "}
        <span className="ws-picker-name">{activeName || "workspace"}</span>{" "}
        <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="ws-picker-menu" data-testid="workspace-menu" role="listbox">
          {items.length === 0 && (
            <div className="ws-picker-empty">No workspaces found</div>
          )}
          {items.map((w) => (
            <button
              key={w.name}
              type="button"
              className="ws-picker-item"
              data-testid="workspace-option"
              role="option"
              aria-selected={w.name === activeName}
              disabled={busy !== null}
              onClick={() => void pick(w.name)}
            >
              <span className="ws-picker-check" aria-hidden="true">
                {w.name === activeName ? "✓" : ""}
              </span>
              <span className="ws-picker-label">
                {w.name}
                {typeof w.library_count === "number" && (
                  <span className="ws-picker-meta">
                    {" "}
                    · {w.library_count} lib{w.library_count === 1 ? "" : "s"}
                  </span>
                )}
              </span>
            </button>
          ))}
          {error && <div className="ws-picker-error">{error}</div>}
        </div>
      )}
    </div>
  );
}
