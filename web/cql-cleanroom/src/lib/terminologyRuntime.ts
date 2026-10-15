/**
 * Terminology settings + runtime valueset resolution + cache
 * (c-cleanroom-redo S1R, per the user's 3-pillar model).
 *
 * - Credentials live in Settings (browser IndexedDB via the workspace
 *   autosave; the VSAC key rides requests at call time and is NEVER logged
 *   — conductor ruling 1 — and never persisted server-side).
 * - Pre-run resolution: urls declared by the library but absent from the
 *   workspace terminology resolve from the configured source (VSAC / FHIR
 *   server) via the dev-server expansion endpoint; results cache in
 *   IndexedDB keyed by canonical url+version (manual clear; TTL parked).
 * - Works for BOTH engines: resolution happens in the App dataset-merge
 *   layer (evalDataset), before any executor/worker path — mode-uniform
 *   (conductor ruling 2).
 */

import type { ServerMode } from "./serverConnection";

export interface TerminologySettings {
  vsacApiKey: string;
  fhirTermServerBase: string; // "" = default (cts.nlm.nih.gov/fhir)
}

export const DEFAULT_TERMINOLOGY_SETTINGS: TerminologySettings = {
  vsacApiKey: "",
  fhirTermServerBase: "",
};

const TERM_CACHE_DB = "fhir4ds-term-cache";
const TERM_CACHE_STORE = "expansions";
const SETTINGS_KEY = "terminologySettings";

// -- settings persistence (IndexedDB, simple KV) -------------------------

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(TERM_CACHE_DB, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(TERM_CACHE_STORE)) {
        db.createObjectStore(TERM_CACHE_STORE);
      }
      if (!db.objectStoreNames.contains("settings")) {
        db.createObjectStore("settings");
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function kvGet<T>(store: string, key: string): Promise<T | null> {
  try {
    const db = await openDb();
    return await new Promise<T | null>((resolve, reject) => {
      const tx = db.transaction(store, "readonly");
      const req = tx.objectStore(store).get(key);
      req.onsuccess = () => resolve((req.result as T) ?? null);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;
  }
}

async function kvPut(store: string, key: string, value: unknown): Promise<void> {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(store, "readwrite");
      tx.objectStore(store).put(value, key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    /* cache writes are best-effort */
  }
}

export async function loadTerminologySettings(): Promise<TerminologySettings> {
  return (await kvGet<TerminologySettings>("settings", SETTINGS_KEY)) ?? DEFAULT_TERMINOLOGY_SETTINGS;
}

export async function saveTerminologySettings(s: TerminologySettings): Promise<void> {
  await kvPut("settings", SETTINGS_KEY, s);
}

export async function clearTerminologyCache(): Promise<void> {
  try {
    const db = await openDb();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(TERM_CACHE_STORE, "readwrite");
      tx.objectStore(TERM_CACHE_STORE).clear();
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } catch {
    /* best-effort */
  }
}

// -- expansion cache + retrieval -----------------------------------------

export interface CachedExpansion {
  url: string;
  concepts: { system?: string; code?: string; display?: string }[];
  fetchedAt: number;
}

function cacheKey(url: string, version?: string): string {
  return version ? `${url}|${version}` : url;
}

/** Extract `valueset "X": <url>` declarations from CQL library text. */
export function declaredValuesetUrls(libraryText: string): string[] {
  const urls: string[] = [];
  const re = /^\s*valueset\s+"?([A-Za-z0-9_]+)"?\s*:\s*(\S+)/gm;
  let m: RegExpExecArray | null;
  while ((m = re.exec(libraryText)) !== null) {
    const raw = m[2].replace(/^['"]/, "").replace(/['",;]+$/, "");
    if (raw.startsWith("http://") || raw.startsWith("https://") || raw.startsWith("urn:")) {
      urls.push(raw);
    }
  }
  return urls;
}

async function fetchExpansion(
  url: string,
  settings: TerminologySettings,
): Promise<CachedExpansion | null> {
  try {
    const res = await fetch("/api/terminology/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        ...(settings.vsacApiKey ? { api_key: settings.vsacApiKey } : {}),
        ...(settings.fhirTermServerBase ? { base_url: settings.fhirTermServerBase } : {}),
      }),
    });
    const body = (await res.json()) as { data?: Record<string, unknown> };
    const d = body?.data ?? (body as Record<string, unknown>);
    if (d?.ok === false) return null;
    const concepts =
      (d?.concepts as CachedExpansion["concepts"]) ?? [];
    return { url, concepts, fetchedAt: Date.now() };
  } catch {
    // Transport failures degrade to unresolved (typed run diagnostic path).
    return null;
  }
}

/**
 * Pre-run resolution pass (conductor ruling 2 — mode-uniform): resolve urls
 * declared by the library but missing from workspace terminology. Cache
 * hits avoid the network; misses fetch + store. Returns hydrated ValueSet
 * resources ready for the evalDataset merge + per-url resolution failures
 * for typed diagnostics.
 */
export async function resolveRuntimeValuesets(
  libraryText: string,
  workspaceUrls: Set<string>,
  settings: TerminologySettings,
  mode: ServerMode,
): Promise<{ hydrated: Record<string, unknown>[]; unresolved: string[] }> {
  const out: Record<string, unknown>[] = [];
  const unresolved: string[] = [];
  if (mode.kind !== "connected") {
    // Standalone: no retrieval source; every missing url is unresolved
    // (today's behavior — workspace valuesets only).
    for (const url of declaredValuesetUrls(libraryText)) {
      if (!workspaceUrls.has(url)) unresolved.push(url);
    }
    return { hydrated: out, unresolved };
  }
  for (const url of declaredValuesetUrls(libraryText)) {
    if (workspaceUrls.has(url)) continue; // user overrides win
    const key = cacheKey(url);
    let exp = await kvGet<CachedExpansion>(TERM_CACHE_STORE, key);
    if (!exp) {
      exp = await fetchExpansion(url, settings);
      if (exp) await kvPut(TERM_CACHE_STORE, key, exp);
    }
    if (!exp) {
      unresolved.push(url);
      continue;
    }
    out.push({
      resourceType: "ValueSet",
      url,
      name: url.split("/").pop() ?? url,
      compose: {
        include: exp.concepts.length
          ? [
              {
                system: exp.concepts[0]?.system ?? "",
                concept: exp.concepts.map((c) => ({
                  code: c.code ?? "",
                  display: c.display ?? "",
                })),
              },
            ]
          : [],
      },
    });
  }
  return { hydrated: out, unresolved };
}
