import { useState, useEffect, useCallback, useRef } from "react";

interface TranslateResult {
  sql: string;
  timeMs: number;
}

interface PyodideWorkerMessage {
  id: number;
  type: "init" | "translate";
  cql?: string;
  audit?: boolean;
}

interface PyodideWorkerResponse {
  id: number;
  ok: boolean;
  sql?: string;
  timeMs?: number;
  error?: string;
}

export function usePyodide() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef<
    Map<number, { resolve: (v: TranslateResult) => void; reject: (e: Error) => void }>
  >(new Map());
  const nextIdRef = useRef(1);

  useEffect(() => {
    let worker: Worker;
    try {
      worker = new Worker(
        new URL("../workers/pyodide.worker.ts", import.meta.url),
        { type: "module" },
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return;
    }

    worker.onmessage = (e: MessageEvent<PyodideWorkerResponse>) => {
      const { id, ok, sql, timeMs, error } = e.data;

      if (id === 0) {
        // Init response
        if (ok) {
          setReady(true);
          setError(null);
          console.log("[Pyodide] Worker ready");
        } else {
          setError(error ?? "Initialization failed");
          console.error("[Pyodide] Init failed:", error);
        }
        return;
      }

      const pending = pendingRef.current.get(id);
      if (!pending) return;
      pendingRef.current.delete(id);

      if (ok && sql !== undefined && timeMs !== undefined) {
        pending.resolve({ sql, timeMs });
      } else {
        pending.reject(new Error(error ?? "Translation failed"));
      }
    };

    worker.onerror = (e) => {
      const msg = "Worker error: " + (e instanceof ErrorEvent ? e.message : "Unknown error");
      setError(msg);
      console.error("[Pyodide] Worker error:", e);
    };

    workerRef.current = worker;

    // Kick off Pyodide initialization
    worker.postMessage({ id: 0, type: "init" } satisfies PyodideWorkerMessage);

    return () => {
      pendingRef.current.forEach(({ reject }) => {
        reject(new Error("Worker terminated"));
      });
      pendingRef.current.clear();
      worker.terminate();
    };
  }, []);

  const translate = useCallback(
    (cql: string, audit?: boolean): Promise<TranslateResult> => {
      const worker = workerRef.current;
      if (!worker) return Promise.reject(new Error("Worker not started"));

      const id = nextIdRef.current++;
      return new Promise((resolve, reject) => {
        pendingRef.current.set(id, { resolve, reject });
        worker.postMessage({ id, type: "translate", cql, audit } satisfies PyodideWorkerMessage);
      });
    },
    [],
  );

  return { ready, error, translate };
}
