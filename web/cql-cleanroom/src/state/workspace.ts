/**
 * C1-U7 workspace store: IndexedDB persistence with schemaVersion and a
 * migration hook (plan §3.2 state/), zip export/import via fflate.
 *
 * WORKBENCH_V6 (schemaVersion 6): singleton workspace state becomes
 * resource collections — measures[] with an activeMeasureId, authored
 * expected MeasureReports, stored ViewDefinitions, per-measure parameter
 * bindings. Libraries gain stable ids (nav/tabs key on id, not index).
 *
 * Stored entities (all inside one "workspace" record for simplicity):
 *  - libraries: [{ id, name, text }]
 *  - measures: [{ id, mainLibraryId, resource }]
 *  - expectedReports: { measureId: MeasureReport[] } (authored)
 *  - viewDefs: [{ id, name, resource }] (stored ViewDefinition resources)
 *  - viewConfig: LEGACY override map kept until the View pane goes
 *    stored-mode (WORKBENCH_V6 phase 3); seeded alongside viewDefs.
 *  - paramValues: { param: value } (global, v7; v6 per-measure
 *    paramBindings collapse on migrate)
 *  - dataset: { resources: [...] } | null  (Tests drawer data)
 *  - cases: legacy row-form expectations, kept in sync with
 *    expectedReports for v5 zip interop
 *  - runHistory: local-only (never in zip — INV-4)
 */

import { zipSync, unzipSync } from "fflate";
import { buildDerivedView, type ViewOverrides } from "../lib/viewDerivation";
import {
  casesFromReports,
  expectedReportsFromCases,
} from "../lib/expectedReports";
import { toParametersResource } from "../lib/params";

const DB_NAME = "cql-cleanroom";
const STORE = "workspace";
export const WORKSPACE_SCHEMA_VERSION = 7;

/** WORKBENCH_REORG §3.3/§3.5 — a saved evaluation run. Local-only
 * (IndexedDB document; NEVER in zip or share links — INV-4). */
/** REORG 6g — everything needed to REPLAY a run's output (results
 *  table, SQL, AST, executed CQL) without re-evaluating. Selection runs
 *  carry the synthesized `__snippet__` wrapper text as `cql`. */
export interface RunEntryPayload {
  mode: "library" | "selection";
  cql: string;
  sql?: string;
  rows?: Array<Record<string, unknown>>;
  columns?: string[];
  column_types?: Record<string, string>;
  ms?: number | null;
  diags?: import("../lib/protocol").Diagnostics[];
}

/** Row-shaped memberships of a successful run. */
export interface RunArtifact {
  patients: Record<string, { populations: Record<string, boolean | null> }>;
}

export interface RunEntry {
  id: string;
  name: string;
  createdAt: number;
  libraryHash: string;
  datasetHash: string;
  /** null for FAILED runs (no artifact — the diff baseline skips them). */
  artifact: RunArtifact | null;
  payload?: RunEntryPayload;
}

export const RUN_HISTORY_CAP = 20;

export interface WorkspaceLibrary {
  /** Stable id ("lib_<n>") — nav/tabs key on this, never on index. */
  id: string;
  name: string;
  text: string;
}

/** A stored Measure + its evaluated entrypoint library. */
export interface WorkspaceMeasureEntry {
  id: string; // "msr_<n>"
  /** Entry library id (v5 "entrypoint index" successor). */
  mainLibraryId: string;
  /** Authored Measure resource; null = entry exists but no populations
   *  authored yet (MeasurePane bootstrap mode). */
  resource: Record<string, unknown> | null;
}

/** A stored ViewDefinition resource (WORKBENCH_V6). */
export interface WorkspaceViewDefEntry {
  id: string; // "vd_<n>"
  name: string;
  resource: Record<string, unknown>;
}

/** §3.5 View drawer config — MeasureReport VD overrides (F8).
 *  LEGACY: superseded by viewDefs in phase 3; kept so the current
 *  ViewPane override UI keeps persisting until then. */
export interface WorkspaceViewConfig {
  overrides: Record<string, { name?: string; path?: string }>;
}

export interface WorkspaceState {
  schemaVersion: number;
  libraries: WorkspaceLibrary[];
  dataset: { resources: unknown[] } | null;
  cases: unknown[] | null;
  prefs: Record<string, unknown>;
  /** Stored Measures (FHIR Measure resources) — replaces v5 `measure`. */
  measures: WorkspaceMeasureEntry[];
  /** The measure driving column-2 auto-recalc (nav dot). */
  activeMeasureId: string | null;
  /** Authored expected MeasureReports, keyed by measure id. */
  expectedReports: Record<string, Array<Record<string, unknown>>>;
  viewDefs: WorkspaceViewDefEntry[];
  /** Parameter values by CQL parameter name — GLOBAL, not per-measure:
   *  parameters belong to the primary library's declarations, and a
   *  shared set holds the union as measures multiply (v7). */
  paramValues: Record<string, string>;
  /** Local run history (§3.3); capped, pruned oldest-first. */
  runHistory: RunEntry[];
  /** Preferred results lens (§3.1): cql | measure | view. */
  activeTabPref: string;
  /** Terminology (PASS2 G2): workspace ValueSet resources, url-deduped,
   *  overriding dataset valueset_resources on evaluate. Never null. */
  terminology: { valuesets: Array<Record<string, unknown>> };
  /** LEGACY v5 param values (migration input only; see paramBindings). */
  viewConfig: WorkspaceViewConfig | null;
  savedAt: number;
}

/** Fresh unique-ish library id (caller guarantees uniqueness in state). */
export function newLibraryId(libraries: WorkspaceLibrary[]): string {
  let n = libraries.length;
  const taken = new Set(libraries.map((l) => l.id));
  while (taken.has(`lib_${n}`)) n += 1;
  return `lib_${n}`;
}

export function newMeasureId(measures: WorkspaceMeasureEntry[]): string {
  let n = measures.length;
  const taken = new Set(measures.map((m) => m.id));
  while (taken.has(`msr_${n}`)) n += 1;
  return `msr_${n}`;
}

export function newViewDefId(viewDefs: WorkspaceViewDefEntry[]): string {
  let n = viewDefs.length;
  const taken = new Set(viewDefs.map((v) => v.id));
  while (taken.has(`vd_${n}`)) n += 1;
  return `vd_${n}`;
}

/** Attach ids to id-less libraries (imports, examples, share decode). */
export function withLibraryIds(
  libs: Array<{ name: string; text: string }>,
): WorkspaceLibrary[] {
  return libs.map((l, i) => ({ id: `lib_${i}`, name: l.name, text: l.text }));
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
  // v4 -> v5: parameter drawer values (Measurement Period etc.).
  4: (s) => ({ ...s, paramValues: {} }),
  // v5 -> v6 (WORKBENCH_V6): singletons → collections. Library ids are
  // positional for migrated state; the single v5 measure becomes
  // measures[0] pinned to the first library; paramValues moves under
  // paramBindings[msr_0]; authored expectedReports derive from legacy
  // case rows; stored viewDefs seed from viewConfig overrides (the
  // legacy field rides along until the View pane goes stored-mode).
  5: (s) => {
    const libs = withLibraryIds(
      ((s.libraries as Array<{ name: string; text: string }>) ?? []).map(
        (l) => ({ name: l.name, text: l.text }),
      ),
    );
    const measure = s.measure as Record<string, unknown> | null | undefined;
    const measures: WorkspaceMeasureEntry[] = measure
      ? [
          {
            id: "msr_0",
            mainLibraryId: libs[0]?.id ?? "lib_0",
            resource: measure,
          },
        ]
      : [];
    const paramValues =
      (s.paramValues as Record<string, string> | undefined) ?? {};
    const overrides =
      (s.viewConfig as WorkspaceViewConfig | null | undefined)?.overrides ?? {};
    const viewDefs: WorkspaceViewDefEntry[] =
      measure && Object.keys(overrides).length
        ? [
            {
              id: "vd_0",
              name: "MeasureReportPopulations",
              resource: buildDerivedView(measure, overrides as ViewOverrides),
            },
          ]
        : [];
    return {
      ...s,
      libraries: libs,
      measures,
      activeMeasureId: measures[0]?.id ?? null,
      expectedReports: {
        ...(measures[0]
          ? {
              [measures[0].id]: expectedReportsFromCases(
                s.cases as unknown[] | null | undefined,
              ),
            }
          : {}),
      },
      viewDefs,
      paramBindings: measures[0] ? { [measures[0].id]: paramValues } : {},
    };
  },
  // v6 -> v7: parameters go GLOBAL — the per-measure maps collapse into
  // one name→value record (later measures win on conflicts; in practice
  // there is exactly one).
  6: (s) => {
    const perMeasure =
      (s.paramBindings as Record<string, Record<string, string>> | undefined) ??
      {};
    const merged: Record<string, string> = {};
    for (const values of Object.values(perMeasure)) Object.assign(merged, values);
    return { ...s, paramValues: merged };
  },
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
    measures: (current.measures as WorkspaceMeasureEntry[]) ?? [],
    activeMeasureId:
      (current.activeMeasureId as string | null | undefined) ?? null,
    expectedReports:
      (current.expectedReports as WorkspaceState["expectedReports"]) ?? {},
    viewDefs: (current.viewDefs as WorkspaceViewDefEntry[]) ?? [],
    paramValues: (current.paramValues as Record<string, string>) ?? {},
    runHistory: (current.runHistory as RunEntry[]) ?? [],
    activeTabPref: (current.activeTabPref as string) ?? "cql",
    terminology:
      (current.terminology as WorkspaceState["terminology"] | undefined) ?? {
        valuesets: [],
      },
    viewConfig: (current.viewConfig as WorkspaceViewConfig | null) ?? null,
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
//
// v7 layout: NN-name.cql, dataset.ndjson, cases.json, valuesets.json,
// parameters.json (FHIR Parameters view of the bound values), measures.json
// (entries + embedded expectedReports), viewdefs.json,
// workspace.json (meta: libraries with ids, activeMeasureId,
// paramValues, prefs, activeTabPref, legacy viewConfig).
// v6 zips (paramBindings) and v5 zips (measure.json + paramValues) still
// import via MIGRATIONS.
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
  // WORKBENCH_V6: measures + authored expectedReports ride as ONE entry
  // per measure (interop form travels with its expectations).
  if (state.measures.length) {
    files["measures.json"] = utf8Encode(
      JSON.stringify(
        state.measures.map((m) => ({
          id: m.id,
          mainLibraryId: m.mainLibraryId,
          resource: m.resource,
          expectedReports: state.expectedReports[m.id] ?? [],
        })),
        null,
        1,
      ),
    );
  }
  if (state.viewDefs.length) {
    files["viewdefs.json"] = utf8Encode(JSON.stringify(state.viewDefs, null, 1));
  }
  // PASS2 G2: terminology rides as a LOOSE valuesets.json entry (the
  // dataset.ndjson convention) — mega ValueSets would bloat workspace.json.
  if (state.terminology?.valuesets?.length) {
    files["valuesets.json"] = utf8Encode(
      JSON.stringify(state.terminology.valuesets, null, 1),
    );
  }
  // v7: the FHIR Parameters view of the bound values — interop artifact
  // for real engines; workspace.json keeps carrying the raw state.
  const bound = Object.entries(state.paramValues ?? {}).filter(
    ([, v]) => typeof v === "string" && v.trim() !== "",
  );
  if (bound.length) {
    files["parameters.json"] = utf8Encode(
      JSON.stringify(toParametersResource(Object.fromEntries(bound)), null, 1),
    );
  }
  // INV-4: runHistory is local-only — deliberately absent from the zip.
  const metaOut: Record<string, unknown> = {
    schemaVersion: WORKSPACE_SCHEMA_VERSION,
    format: "cql-cleanroom-workspace",
    libraries: state.libraries,
    prefs: state.prefs,
    activeTabPref: state.activeTabPref,
    activeMeasureId: state.activeMeasureId,
    paramValues: state.paramValues,
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
  let valuesets: Array<Record<string, unknown>> = [];
  if (files["valuesets.json"]) {
    const parsed = JSON.parse(decode(files["valuesets.json"]));
    if (Array.isArray(parsed)) {
      valuesets = parsed.filter(
        (v) => v && typeof v === "object" && !Array.isArray(v),
      ) as Array<Record<string, unknown>>;
    }
  }

  // WORKBENCH_V6 zips: measures.json (entries + expectedReports) +
  // viewdefs.json. v5 zips: measure.json + paramValues — shaped as a v5
  // state and routed through MIGRATIONS[5] so both eras land on v6
  // fields (the SO-caught bug pattern: ALWAYS migrate on import).
  let measures: WorkspaceMeasureEntry[] = [];
  let expectedReports: WorkspaceState["expectedReports"] = {};
  let viewDefs: WorkspaceViewDefEntry[] = [];
  let paramBindings: Record<string, Record<string, string>> = {};
  let measureV5: Record<string, unknown> | null = null;
  let viewConfigV5: WorkspaceViewConfig | null =
    (meta.viewConfig as WorkspaceViewConfig | null | undefined) ?? null;
  let schemaVersion = (meta.schemaVersion as number) ?? 1;

  if (files["measures.json"]) {
    const parsed = JSON.parse(decode(files["measures.json"]));
    if (Array.isArray(parsed)) {
      for (const entry of parsed) {
        if (!entry || typeof entry !== "object") continue;
        const e = entry as Record<string, unknown>;
        // resource === null is legal (MeasurePane bootstrap mode); only a
        // non-null resource must actually be a Measure.
        if (
          e.resource &&
          (e.resource as Record<string, unknown>).resourceType !== "Measure"
        ) {
          continue;
        }
        const id = typeof e.id === "string" ? e.id : newMeasureId(measures);
        measures.push({
          id,
          mainLibraryId:
            typeof e.mainLibraryId === "string"
              ? e.mainLibraryId
              : libraries[0]?.id ?? "lib_0",
          resource: (e.resource as Record<string, unknown>) ?? null,
        });
        if (Array.isArray(e.expectedReports)) {
          expectedReports[id] = e.expectedReports.filter(
            (r: unknown) =>
              r &&
              typeof r === "object" &&
              (r as Record<string, unknown>).resourceType === "MeasureReport",
          ) as Array<Record<string, unknown>>;
        }
      }
    }
    if (files["viewdefs.json"]) {
      const parsedVd = JSON.parse(decode(files["viewdefs.json"]));
      if (Array.isArray(parsedVd)) {
        viewDefs = parsedVd.filter((v) => {
          // ViewDefinition payloads carry their TARGET resource under
          // `resource` (e.g. "MeasureReport") — there is no resourceType.
          if (!v || typeof v !== "object") return false;
          const res = (v as { resource?: unknown }).resource;
          return !!res && typeof res === "object";
        }) as WorkspaceViewDefEntry[];
      }
    }
    paramBindings =
      (meta.paramBindings as Record<string, Record<string, string>> | undefined) ??
      {};
    schemaVersion = Math.max(schemaVersion, 5 + 1);
  } else if (files["measure.json"]) {
    const parsed = JSON.parse(decode(files["measure.json"]));
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      measureV5 = parsed as Record<string, unknown>;
    }
  }

  // SO-caught bug: route the parsed payload through migrate() so OLD
  // zips (schemaVersion < 6) gain every defaulted field — direct field
  // reads would yield undefined collections on pre-v6 zips.
  const migrated = migrate({
    schemaVersion,
    libraries,
    dataset,
    cases,
    prefs: (meta.prefs as Record<string, unknown>) ?? {},
    measure: measureV5,
    viewConfig: viewConfigV5,
    activeTabPref: (meta.activeTabPref as string) ?? "cql",
    terminology: { valuesets },
    paramValues: (meta.paramValues as Record<string, string>) ?? {},
    measures,
    activeMeasureId: meta.activeMeasureId ?? measures[0]?.id ?? null,
    expectedReports,
    viewDefs,
    paramBindings,
    savedAt: Date.now(),
  });
  // Keep legacy `cases` in sync with authored reports when v6 data is
  // present (v5 cases ride through the migration untouched).
  const migratedCases =
    measures.length && (migrated.expectedReports[measures[0].id]?.length ?? 0) > 0
      ? casesFromReports(migrated.expectedReports[measures[0].id])
      : cases;
  return {
    libraries: migrated.libraries,
    dataset,
    cases: migratedCases,
    measures: migrated.measures,
    activeMeasureId: migrated.activeMeasureId,
    expectedReports: migrated.expectedReports,
    viewDefs: migrated.viewDefs,
    paramValues: migrated.paramValues,
    runHistory: [], // local-only: imports never restore runs (INV-4)
    activeTabPref: migrated.activeTabPref,
    prefs: migrated.prefs,
    terminology: migrated.terminology,
    viewConfig: migrated.viewConfig,
  };
}

function utf8Encode(s: string): Uint8Array {
  return new TextEncoder().encode(s);
}

function safe(name: string): string {
  return name.replace(/[^A-Za-z0-9_-]+/g, "_");
}
