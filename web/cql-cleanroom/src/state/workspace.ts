/**
 * C1-U7 workspace store: IndexedDB persistence with schemaVersion v1
 * and a migration hook (plan §3.2 state/), zip export/import via fflate.
 *
 * Stored entities (all inside one "workspace" record for v1 simplicity):
 *  - libraries: [{ name, text }]  (main library first)
 *  - dataset: { resources: [...] } | null
 *  - cases: TestCase[] | null
 *  - prefs: { autoRun?: boolean }
 */

import { zipSync, unzipSync } from "fflate";

const DB_NAME = "cql-cleanroom";
const STORE = "workspace";
export const WORKSPACE_SCHEMA_VERSION = 1;

export interface WorkspaceLibrary {
  name: string;
  text: string;
}

export interface WorkspaceState {
  schemaVersion: number;
  libraries: WorkspaceLibrary[];
  dataset: { resources: unknown[] } | null;
  cases: unknown[] | null;
  prefs: Record<string, unknown>;
  savedAt: number;
}

/** v1 → vN migrations run in order; each returns the upgraded state. */
const MIGRATIONS: Record<number, (s: Record<string, unknown>) => Record<string, unknown>> = {
  // example for future versions:
  // 1: (s) => ({ ...s, newField: defaultValue }),
};

export function migrate(state: Record<string, unknown>): WorkspaceState {
  let version = (state.schemaVersion as number) ?? 1;
  let current = state;
  while (version < WORKSPACE_SCHEMA_VERSION) {
    const step = MIGRATIONS[version];
    current = step ? step(current) : current;
    version += 1;
  }
  return {
    schemaVersion: WORKSPACE_SCHEMA_VERSION,
    libraries: (current.libraries as WorkspaceLibrary[]) ?? [],
    dataset: (current.dataset as { resources: unknown[] } | null) ?? null,
    cases: (current.cases as unknown[]) ?? null,
    prefs: (current.prefs as Record<string, unknown>) ?? {},
    savedAt: (current.savedAt as number) ?? Date.now(),
  };
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("indexedDB open failed"));
  });
}

export async function saveWorkspace(state: Omit<WorkspaceState, "schemaVersion" | "savedAt">): Promise<void> {
  const db = await openDb();
  const record: WorkspaceState = {
    ...state,
    schemaVersion: WORKSPACE_SCHEMA_VERSION,
    savedAt: Date.now(),
  };
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(record, "current");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("indexedDB put failed"));
  });
  db.close();
}

export async function loadWorkspace(): Promise<WorkspaceState | null> {
  const db = await openDb();
  const raw = await new Promise<unknown>((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get("current");
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("indexedDB get failed"));
  });
  db.close();
  if (!raw || typeof raw !== "object") return null;
  return migrate(raw as Record<string, unknown>);
}

export async function clearWorkspace(): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete("current");
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("indexedDB delete failed"));
  });
  db.close();
}

// ---------------------------------------------------------------------------
// Zip export/import (fflate; single source of truth = WorkspaceState)
// ---------------------------------------------------------------------------

export function exportWorkspaceZip(state: Omit<WorkspaceState, "schemaVersion" | "savedAt">): Uint8Array {
  const files: Record<string, Uint8Array> = {
    "workspace.json": utf8Encode(
      JSON.stringify(
        {
          schemaVersion: WORKSPACE_SCHEMA_VERSION,
          format: "cql-cleanroom-workspace",
          libraries: state.libraries,
          prefs: state.prefs,
        },
        null,
        1,
      ),
    ),
  };
  state.libraries.forEach((lib, i) => {
    const name = `${String(i + 1).padStart(2, "0")}-${safe(lib.name)}.cql`;
    files[name] = utf8Encode(lib.text);
  });
  if (state.dataset?.resources?.length) {
    files["dataset.ndjson"] = utf8Encode(
      state.dataset.resources.map((r) => JSON.stringify(r)).join("\n") + "\n",
    );
  }
  if (state.cases?.length) {
    files["cases.json"] = utf8Encode(JSON.stringify(state.cases, null, 1));
  }
  return zipSync(files);
}

export function importWorkspaceZip(bytes: Uint8Array): Omit<WorkspaceState, "schemaVersion" | "savedAt"> {
  const files = unzipSync(bytes);
  const decode = (b: Uint8Array) => new TextDecoder().decode(b);
  if (!files["workspace.json"]) {
    throw new Error("not a cleanroom workspace zip: workspace.json missing");
  }
  const meta = JSON.parse(decode(files["workspace.json"]));
  if (meta.format !== "cql-cleanroom-workspace") {
    throw new Error(`unexpected workspace format: ${String(meta.format)}`);
  }
  const libraries: WorkspaceLibrary[] = Array.isArray(meta.libraries)
    ? meta.libraries
    : [];
  let dataset: { resources: unknown[] } | null = null;
  if (files["dataset.ndjson"]) {
    const lines = decode(files["dataset.ndjson"])
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    dataset = { resources: lines.map((l) => JSON.parse(l)) };
  }
  let cases: unknown[] | null = null;
  if (files["cases.json"]) {
    cases = JSON.parse(decode(files["cases.json"]));
  }
  return {
    libraries,
    dataset,
    cases,
    prefs: (meta.prefs as Record<string, unknown>) ?? {},
  };
}

function utf8Encode(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

function safe(name: string): string {
  return name.replace(/[^A-Za-z0-9_-]+/g, "_");
}
