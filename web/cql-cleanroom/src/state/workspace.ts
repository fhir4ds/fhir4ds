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
export const WORKSPACE_SCHEMA_VERSION = 4;

/** WORKBENCH_REORG §3.3/§3.5 — a saved evaluation run. Local-only
 * (IndexedDB document; NEVER in zip or share links — INV-4). */
export interface RunEntry {
  id: string;
  name: string;
  createdAt: number;
  libraryHash: string;
  datasetHash: string;
  /** Row-shaped memberships {patients: {pid: {populations: ...}}}. */
  artifact: { patients: Record<string, { populations: Record<string, boolean | null> }> };
}

export const RUN_HISTORY_CAP = 20;

export interface WorkspaceLibrary {
  name: string;
  text: string;
}

/** §3.5 View drawer config — MeasureReport VD overrides (F8). */
export interface WorkspaceViewConfig {
  overrides: Record<string, { name?: string; path?: string }>;
}

export interface WorkspaceState {
  schemaVersion: number;
  libraries: WorkspaceLibrary[];
  dataset: { resources: unknown[] } | null;
  cases: unknown[] | null;
  prefs: Record<string, unknown>;
  /** FHIR Measure resource (population mapping authority); null = none. */
  measure: Record<string, unknown> | null;
  viewConfig: WorkspaceViewConfig | null;
  /** Local run history (§3.3); capped, pruned oldest-first. */
  runHistory: RunEntry[];
  /** Preferred Results tab (§3.1): cql | measure | view. */
  activeTabPref: string;
  /** Terminology (PASS2 G2): workspace ValueSet resources, url-deduped,
   *  overriding dataset valueset_resources on evaluate. Never null. */
  terminology: { valuesets: Array<Record<string, unknown>> };
  savedAt: number;
}

/** v1 → vN migrations run in order; each returns the upgraded state. */
const MIGRATIONS: Record<number, (s: Record<string, unknown>) => Record<string, unknown>> = {
  // v1 -> v2: View drawer config (§3.5). F8: overrides persist in
  // workspace.json ONLY (no loose zip entry); migrate defaults null.
  1: (s) => ({ ...s, viewConfig: null }),
  // v2 -> v3 (WORKBENCH_REORG): local run history + Results tab pref.
  // Runs are IndexedDB-only — the zip never carries them (INV-4).
  2: (s) => ({ ...s, runHistory: [], activeTabPref: "cql" }),
  // v3 -> v4 (PASS2): terminology override storage. Default is an EMPTY
  // list, never null — consumers iterate without guards.
  3: (s) => ({ ...s, terminology: { valuesets: [] } }),
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
    measure: (current.measure as Record<string, unknown> | null) ?? null,
    viewConfig: (current.viewConfig as WorkspaceViewConfig | null) ?? null,
    runHistory: (current.runHistory as RunEntry[]) ?? [],
    activeTabPref: (current.activeTabPref as string) ?? "cql",
    terminology:
      (current.terminology as WorkspaceState["terminology"] | undefined) ?? {
        valuesets: [],
      },
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
    "00-placeholder": new Uint8Array(0),
  };
  delete files["00-placeholder"];
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
  if (state.measure) {
    files["measure.json"] = utf8Encode(JSON.stringify(state.measure, null, 1));
  }
  // PASS2 G2: terminology rides as a LOOSE valuesets.json entry (the
  // dataset.ndjson convention) — mega ValueSets would bloat workspace.json.
  if (state.terminology?.valuesets?.length) {
    files["valuesets.json"] = utf8Encode(
      JSON.stringify(state.terminology.valuesets, null, 1),
    );
  }
  // F8: view overrides ride INSIDE workspace.json (not a loose entry).
  // INV-4: runHistory is local-only — deliberately absent from the zip.
  const metaOut: Record<string, unknown> = {
    schemaVersion: WORKSPACE_SCHEMA_VERSION,
    format: "cql-cleanroom-workspace",
    libraries: state.libraries,
    prefs: state.prefs,
    activeTabPref: state.activeTabPref,
  };
  if (state.viewConfig) {
    metaOut.viewConfig = state.viewConfig;
  }
  files["workspace.json"] = utf8Encode(JSON.stringify(metaOut, null, 1));
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
  let measure: Record<string, unknown> | null = null;
  if (files["measure.json"]) {
    const parsed = JSON.parse(decode(files["measure.json"]));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      measure = parsed as Record<string, unknown>;
    }
  }
  let valuesets: Array<Record<string, unknown>> = [];
  if (files["valuesets.json"]) {
    const parsed = JSON.parse(decode(files["valuesets.json"]));
    if (Array.isArray(parsed)) {
      valuesets = parsed.filter(
        (v) => v && typeof v === "object" && !Array.isArray(v),
      ) as Array<Record<string, unknown>>;
    }
  }
  // SO-caught bug: route the parsed payload through migrate() so OLD
  // zips (schemaVersion < 4) gain every defaulted field — direct field
  // reads would yield undefined terminology on v3 zips.
  const migrated = migrate({
    schemaVersion: (meta.schemaVersion as number) ?? 1,
    libraries,
    dataset,
    cases,
    prefs: (meta.prefs as Record<string, unknown>) ?? {},
    measure,
    viewConfig: meta.viewConfig ?? null,
    activeTabPref: (meta.activeTabPref as string) ?? "cql",
    terminology: { valuesets },
    savedAt: Date.now(),
  });
  return {
    libraries: migrated.libraries,
    dataset,
    cases,
    measure,
    viewConfig: migrated.viewConfig,
    runHistory: [], // local-only: imports never restore runs (INV-4)
    activeTabPref: migrated.activeTabPref,
    prefs: migrated.prefs,
    terminology: migrated.terminology,
  };
}

function utf8Encode(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

function safe(name: string): string {
  return name.replace(/[^A-Za-z0-9_-]+/g, "_");
}
