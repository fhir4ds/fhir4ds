/**
 * Mode handshake (c-wasm-bolton S1).
 *
 * Four states per the FDD v2 Muse gate — never a boolean:
 *   connecting → connected | standalone (| degraded after WS failure)
 *
 * The app fetches `/api/mode` on boot (additive endpoint; `/health` stays).
 * 200 + server:true mounts ServerTransport. 404 / fetch failure = static
 * hosting → standalone. `nonce` detects stale handshakes after server
 * restarts (embed); `server_range` is a documented node-semver range the
 * UI parses for the version-pin banner (never magic).
 */

export type ModeState =
  | { kind: "connecting" }
  | {
      kind: "connected";
      version: string;
      serverRange: string;
      workspace: string;
      nonce: string;
    }
  /** P5 (S1 Muse): handshake OK but the events WebSocket failed — stay
   *  connected (HTTP transport works); the status bar shows a watcher
   *  warning. Entered by the hook from transport socket failure. */
  | {
      kind: "degraded";
      version: string;
      serverRange: string;
      workspace: string;
      nonce: string;
    }
  | { kind: "standalone"; reason: "not-found" | "unreachable" };

export interface ModeInfo {
  server: boolean;
  version?: string;
  server_range?: string;
  workspace?: string;
  nonce?: string;
}

/** Parse a node-semver range against a version — the documented contract
 *  for the version-pin banner (subset: >=X.Y.Z with optional || branches
 *  and * wildcards; enough for ranges this server emits). */
export function versionSatisfies(version: string, range: string): boolean {
  // Compare only X.Y.Z-ish prefixes; ignore prerelease tags for the pin.
  const parse = (v: string): [number, number, number] | null => {
    const m = /^(\d+)\.(\d+)\.(\d+)/.exec(v.trim());
    return m ? [+m[1], +m[2], +m[3]] : null;
  };
  const branches = range.split("||").map((b) => b.trim());
  return branches.some((branch) => {
    const gte = /^>=\s*(\d+)\.(\d+)\.(\d+)/.exec(branch);
    if (!gte) return branch === "*" || branch === "";
    const min: [number, number, number] = [+gte[1], +gte[2], +gte[3]];
    const got = parse(version);
    if (!got) return false;
    for (let i = 0; i < 3; i++) {
      if (got[i] !== min[i]) return got[i] > min[i];
    }
    return true; // equal satisfies >=
  });
}

export async function handshake(
  base = "",
  signal?: AbortSignal,
): Promise<ModeState> {
  try {
    const res = await fetch(`${base}/api/mode`, { signal });
    if (res.status === 404) {
      return { kind: "standalone", reason: "not-found" };
    }
    if (!res.ok) {
      // A server that is alive but erroring is still a server; treat
      // 5xx as unreachable-standalone for S1 (the retry affordance in
      // the engine badge covers recovery).
      return { kind: "standalone", reason: "unreachable" };
    }
    const body = (await res.json()) as { data?: ModeInfo } & ModeInfo;
    const info: ModeInfo = body?.data ?? body;
    if (info?.server === true && info.version && info.nonce) {
      return {
        kind: "connected",
        version: info.version,
        serverRange: info.server_range ?? ">=0.0.0",
        workspace: info.workspace ?? "workspace",
        nonce: info.nonce,
      };
    }
    return { kind: "standalone", reason: "not-found" };
  } catch {
    return { kind: "standalone", reason: "unreachable" };
  }
}

/** Version-pin check per FDD v2: blocking banner when the server version
 *  falls outside the documented range; never silently degrade. */
export function versionPinOk(state: ModeState): boolean {
  if (state.kind !== "connected") return true;
  return versionSatisfies(state.version, state.serverRange);
}
