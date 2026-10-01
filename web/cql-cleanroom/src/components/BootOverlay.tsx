import { useEffect, useState } from "react";

export type BootState =
  | { phase: "idle" }
  | { phase: "booting"; step: string; startedAt: number }
  | { phase: "ready"; wheelVersion: string; bootMs: number }
  | { phase: "error"; error: string };

export function BootOverlay({ state }: { state: BootState }) {
  if (state.phase === "ready" || state.phase === "idle") return null;
  return (
    <div className="boot-overlay" role="status" aria-live="polite">
      {state.phase === "booting" ? (
        <>
          <div className="boot-spinner" aria-hidden="true" />
          <div className="boot-title">CQL Cleanroom</div>
          <div className="boot-step" data-testid="boot-step">
            {state.step}
          </div>
          <div className="boot-hint">
            First boot downloads the engine (~40–60s); later boots are cached.
          </div>
        </>
      ) : (
        <>
          <div className="boot-title">Boot failed</div>
          <div className="boot-error" data-testid="boot-error">
            {state.error}
          </div>
        </>
      )}
    </div>
  );
}

/** Display the loaded wheel version (S2: pin visibility). */
export function VersionBadge({
  wheelVersion,
}: {
  wheelVersion: string | null;
}) {
  if (!wheelVersion) return null;
  return (
    <span className="version-badge" title="fhir4ds-v2 wheel bundled in this build">
      fhir4ds-v2 {wheelVersion}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Singleton worker client (StrictMode-safe; one Pyodide boot per page)
// ---------------------------------------------------------------------------

let sharedWorker: Worker | null = null;
let bootListeners: Array<(m: any) => void> = [];
let requestListeners = new Map<number, (m: any) => void>();
let nextReqId = 1;

function getWorker(): Worker {
  if (sharedWorker) return sharedWorker;
  sharedWorker = new Worker(
    new URL("../workers/cleanroom.worker.ts", import.meta.url),
    { type: "module" },
  );
  sharedWorker.onmessage = (e: MessageEvent) => {
    const m = e.data as { id?: number; type?: string };
    for (const fn of bootListeners) fn(m);
    if (m && typeof m.id === "number" && requestListeners.has(m.id)) {
      const fn = requestListeners.get(m.id)!;
      requestListeners.delete(m.id);
      fn(m);
    }
  };
  sharedWorker.postMessage({ id: 0, type: "boot" });
  return sharedWorker;
}

/**
 * Request/response over the singleton worker (id-correlated). Used by the
 * app panels and the e2e capability suite.
 */
export function workerRequest(msg: Record<string, unknown>): Promise<any> {
  const worker = getWorker();
  const id = nextReqId++;
  return new Promise((resolve) => {
    requestListeners.set(id, resolve);
    worker.postMessage({ ...msg, id });
  });
}

export function useBootProgress(): BootState {
  const [state, setState] = useState<BootState>({ phase: "idle" });
  useEffect(() => {
    setState({ phase: "booting", step: "Loading engine…", startedAt: Date.now() });
    const listener = (msg: any) => {
      if (msg.type !== "boot") return;
      if (msg.ok) {
        setState({
          phase: "ready",
          wheelVersion: msg.wheelVersion,
          bootMs: msg.bootMs,
        });
      } else {
        setState({ phase: "error", error: msg.error ?? "unknown boot failure" });
      }
    };
    bootListeners.push(listener);
    getWorker(); // idempotent: boots once per page
    return () => {
      bootListeners = bootListeners.filter((f) => f !== listener);
    };
  }, []);
  return state;
}

// e2e bridge: expose workerRequest on window for Playwright
if (typeof window !== "undefined") {
  (window as any).__cleanroomRequest = workerRequest;
  (window as any).__cleanroomReady = () =>
    new Promise<boolean>((resolve) => {
      const check = () =>
        resolve(Boolean((window as any).__cleanroomBooted));
      const listener = (msg: any) => {
        if (msg.type === "boot") {
          (window as any).__cleanroomBooted = msg.ok;
          resolve(msg.ok);
        }
      };
      if ((window as any).__cleanroomBooted !== undefined) {
        check();
        return;
      }
      bootListeners.push(listener);
      getWorker();
    });
}
