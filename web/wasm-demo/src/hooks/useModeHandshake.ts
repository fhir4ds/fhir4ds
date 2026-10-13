/**
 * useModeHandshake (c-wasm-bolton S1): resolve the app's mode on boot.
 *
 * connecting → connected | standalone; exposes the ServerTransport
 * instance when connected (the wasm app never branches on engine
 * identity — only on capability availability; S2+ surfaces consume
 * transport.capabilities()).
 */

import { useEffect, useState, useCallback, useMemo } from "react";
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
  /** P1 (S1 Muse): "use in-browser engine anyway" — sticky override to
   *  standalone; retry() clears it. */
  useStandalone: () => void;
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
    handshake(serverUrl ?? "", ctrl.signal).then((s) => {
      setState(s);
      // P5: when connected, probe the events WebSocket — failure downgrades
      // the state to degraded (still connected; watcher warning shown).
      if (s.kind !== "connected") return;
      try {
        const proto = location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(
          `${proto}//${location.host}${serverUrl ?? ""}/api/events`,
        );
        const timer = window.setTimeout(() => {
          ws.close();
          setState((cur) =>
            cur.kind === "connected" ? { ...cur, kind: "degraded" } : cur,
          );
        }, 5000);
        ws.onopen = () => {
          window.clearTimeout(timer);
          ws.close();
        };
        ws.onerror = () => {
          window.clearTimeout(timer);
          setState((cur) =>
            cur.kind === "connected" ? { ...cur, kind: "degraded" } : cur,
          );
        };
      } catch {
        /* probe failure handled by the timer */
      }
    });
    return () => ctrl.abort();
  }, [serverUrl, attempt, overrideStandalone]);

  const connected = state.kind === "connected" && !overrideStandalone;
  const effectiveState: ModeState = overrideStandalone && state.kind === "connected"
    ? { kind: "standalone", reason: "not-found" }
    : state;
  // P7 (S1 Muse): stable transport identity while connected (surfaces
  // subscribe in S2+).
  const transport = useMemo(
    () => (connected ? new HttpTransport(serverUrl ?? "") : null),
    [connected, serverUrl],
  );
  const useStandalone = useCallback(() => setOverrideStandalone(true), []);
  return {
    state: effectiveState,
    transport,
    versionMismatch: connected && !versionPinOk(state),
    retry,
    useStandalone,
  };
}
