/**
 * useModeHandshake (c-wasm-bolton S1): resolve the app's mode on boot.
 *
 * connecting → connected | standalone; exposes the ServerTransport
 * instance when connected (the wasm app never branches on engine
 * identity — only on capability availability; S2+ surfaces consume
 * transport.capabilities()).
 */

import { useEffect, useState, useCallback } from "react";
import { handshake, versionPinOk, type ModeState } from "../transport/handshake";
import { HttpTransport } from "../transport/http-transport";

export interface ModeHandshake {
  state: ModeState;
  /** ServerTransport when connected; null otherwise. Connected mode
   *  NEVER initializes Pyodide (perf guarantee, FDD v2). */
  transport: HttpTransport | null;
  /** True when connected but the server version is outside the
   *  documented range — UI must show the blocking banner. */
  versionMismatch: boolean;
  retry: () => void;
}

export function useModeHandshake(serverUrl?: string): ModeHandshake {
  const [state, setState] = useState<ModeState>({ kind: "connecting" });
  const [attempt, setAttempt] = useState(0);
  // Explicit override: user chose "use in-browser engine anyway" —
  // sticky for the session; retry() clears it.
  const [overrideStandalone, setOverrideStandalone] = useState(false);

  const retry = useCallback(() => {
    setOverrideStandalone(false);
    setState({ kind: "connecting" });
    setAttempt((n) => n + 1);
  }, []);

  useEffect(() => {
    if (overrideStandalone) return;
    const ctrl = new AbortController();
    handshake(serverUrl ?? "", ctrl.signal).then(setState);
    return () => ctrl.abort();
  }, [serverUrl, attempt, overrideStandalone]);

  const connected = state.kind === "connected" && !overrideStandalone;
  return {
    state: overrideStandalone && state.kind === "connected"
      ? { kind: "standalone", reason: "not-found" }
      : state,
    transport: connected ? new HttpTransport(serverUrl ?? "") : null,
    versionMismatch: connected && !versionPinOk(state),
    retry,
  };
}
