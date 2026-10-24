import { useEffect, useState } from "react";

/**
 * WorkspacePicker (S22a / AM1): workspaces are DIRECTORIES. Connected
 * mode lists the server-known workspaces (`GET /api/workspaces`) and
 * switches via `POST /api/workspace/switch` (server re-roots the
 * watcher, rebuilds the kernel, bumps the mode nonce). Switching
 * reloads the app so every drawer re-reads the new workspace — the
 * same reload the /api/mode handshake nonce change signals.
 *
 * S26 (item 9): the header flyout control is RETIRED — the list now
 * renders as DropdownMenu items inside File > Workspace. The exported
 * listWorkspaces/switchWorkspace stay the API; WorkspaceMenuItems is
 * the menu rendering.
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

/**
 * S26 (item 9): File > Workspace menu items — workspaces with the
 * active one checked; click = switch + caller-driven reload.
 */
export function WorkspaceMenuItems({
  activeName,
  onSwitched,
  onError,
}: {
  activeName: string;
  onSwitched: (name: string) => void;
  onError?: (message: string) => void;
}) {
  const [items, setItems] = useState<WorkspaceInfo[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    void listWorkspaces().then((ws) => {
      if (!cancelled) setItems(ws);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  const pick = async (name: string) => {
    if (name === activeName || busy) return;
    setBusy(name);
    const r = await switchWorkspace(name);
    if (!r.ok) {
      onError?.(r.message);
      setBusy(null);
      return;
    }
    onSwitched(name);
  };
  if (items.length === 0) {
    return <div className="ws-picker-empty">No workspaces found</div>;
  }
  return (
    <>
      {items.map((w) => (
        <button
          key={w.name}
          type="button"
          className="dropdown-item ws-picker-item"
          data-testid="workspace-option"
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
    </>
  );
}
