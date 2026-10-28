/**
 * Typed client for the Viewing Room worker (main-thread side).
 * Auto-boots on first flatten call; boot status observable for the UI.
 */

import type { CapabilityResponse, FlattenEnvelope, WorkerResponse } from "./protocol";

export interface BootStatus {
  phase: "idle" | "booting" | "ready" | "error";
  wheelVersion?: string;
  error?: string;
  bootMs?: number;
}

type BootListener = (status: BootStatus) => void;

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, { resolve: (r: WorkerResponse) => void; reject: (e: Error) => void }>();
let bootStatus: BootStatus = { phase: "idle" };
const bootListeners = new Set<BootListener>();

function emitBoot(status: BootStatus) {
  bootStatus = status;
  for (const l of bootListeners) l(status);
}

export function onBootStatus(listener: BootListener): () => void {
  bootListeners.add(listener);
  listener(bootStatus);
  return () => bootListeners.delete(listener);
}

export function getBootStatus(): BootStatus {
  return bootStatus;
}

function ensureWorker(): Worker {
  if (worker) return worker;
  worker = new Worker(new URL("../workers/viewing-room.worker.ts", import.meta.url), {
    type: "module",
  });
  worker.onmessage = (e: MessageEvent) => {
    const resp = e.data as WorkerResponse;
    if (resp.type === "boot") {
      const boot = resp as { id: number; type: "boot"; ok: boolean; wheelVersion?: string; bootMs?: number; error?: string };
      if (boot.ok) {
        emitBoot({
          phase: "ready",
          wheelVersion: boot.wheelVersion,
          bootMs: boot.bootMs,
        });
      } else {
        emitBoot({ phase: "error", error: boot.error });
      }
      pending.get(resp.id)?.resolve(resp);
      pending.delete(resp.id);
      return;
    }
    const entry = pending.get(resp.id);
    if (!entry) return;
    pending.delete(resp.id);
  const cap = resp as CapabilityResponse;
    if (cap.ok) entry.resolve(resp);
    else entry.reject(new Error(cap.error ?? "worker error"));
  };
  worker.onerror = (e: ErrorEvent) => {
    emitBoot({ phase: "error", error: e.message || "worker failed to load" });
  };
  return worker;
}

export function boot(): Promise<WorkerResponse> {
  const w = ensureWorker();
  if (bootStatus.phase === "idle") emitBoot({ phase: "booting" });
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    w.postMessage({ id, type: "boot" });
  });
}

/** Parse + generate + execute a ViewDefinition against staged resources. */
export async function flattenView(
  viewDefinition: Record<string, unknown>,
  resources: Array<Record<string, unknown>>,
  setupSql?: string[],
): Promise<FlattenEnvelope> {
  const w = ensureWorker();
  if (bootStatus.phase === "idle") {
    void boot(); // start boot; flatten waits for it in the worker
  }
  const id = nextId++;
  const resp = await new Promise<WorkerResponse>((resolve, reject) => {
    pending.set(id, { resolve, reject });
    w.postMessage({ id, type: "flatten_view", view_definition: viewDefinition, resources, setup_sql: setupSql });
  });
  const cap = resp as { ok: boolean; envelope?: string; error?: string };
  if (!cap.ok || !cap.envelope) {
    return {
      schema: 1,
      ok: false,
      diagnostics: [{ code: "worker_error", message: cap.error ?? "no envelope" }],
    };
  }
  return JSON.parse(cap.envelope) as FlattenEnvelope;
}
