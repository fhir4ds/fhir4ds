import { getAssetBase } from "./asset-base";

/**
 * DuckDB-WASM connection helper.
 *
 * The standalone Vite demo imported the worker and wasm files via Vite's
 * `?url` suffix. In the Docusaurus embed we ship them as static assets under
 * `static/bulk-publisher-app/workers/` and reference them by URL — the COI
 * service worker (registered globally in docusaurus.config.ts) injects the
 * CORP headers DuckDB's Emscripten loader needs.
 */

export interface DuckDBConnectionBundle {
  db: any;
  conn: any;
}

/** Clear stale DuckDB IndexedDB entries that can cause FILE_ERROR_NO_SPACE. */
export async function clearStaleDuckDBStorage(): Promise<void> {
  try {
    if (typeof indexedDB !== "undefined" && typeof indexedDB.databases === "function") {
      const dbs = await indexedDB.databases();
      for (const entry of dbs) {
        if (entry.name) {
          await new Promise<void>((res) => {
            const req = indexedDB.deleteDatabase(entry.name!);
            req.onsuccess = req.onerror = () => res();
          });
        }
      }
    }
  } catch {
    // Not all browsers support indexedDB.databases(); silently ignore.
  }
}

export async function createDuckDBConnection(): Promise<DuckDBConnectionBundle> {
  assertCrossOriginIsolation();

  try {
    const duckdb = await import("@duckdb/duckdb-wasm");
    const workerBase = `${getAssetBase()}/workers`;
    const worker = new Worker(`${workerBase}/duckdb-browser-eh.worker.js`, {
      type: "classic",
    });
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    await db.instantiate(`${workerBase}/duckdb-eh.wasm`, null);
    await (db.open as any)({
      path: ":memory:",
      query: { castBigIntToDouble: true },
      allowUnsignedExtensions: true,
      autoInstallExtensions: false,
      autoLoadExtensions: false,
    });

    const conn = await db.connect();
    await loadFHIR4DSExtensions(db, conn);
    return { db, conn };
  } catch (err) {
    throw new Error(`DuckDB-WASM startup failed: ${errorMessage(err)}`);
  }
}

async function loadFHIR4DSExtensions(db: any, conn: any) {
  // DuckDB-WASM's Emscripten loader resolves the .duckdb_extension.wasm
  // path relative to the worker script URL, not the URL passed to
  // registerFileURL. So the extension files MUST live alongside
  // duckdb-browser-eh.worker.js under /workers/. registerFileURL is still
  // called (it's harmless and may help on some DuckDB versions) but the
  // filesystem layout is what actually makes the load succeed.
  const workerBase = `${getAssetBase()}/workers`;
  try {
    await db.registerFileURL(
      "fhirpath.duckdb_extension.wasm",
      `${workerBase}/fhirpath.duckdb_extension.wasm`,
      4 /* DuckDBDataProtocol.HTTP */,
      false,
    );
    await db.registerFileURL(
      "cql.duckdb_extension.wasm",
      `${workerBase}/cql.duckdb_extension.wasm`,
      4 /* DuckDBDataProtocol.HTTP */,
      false,
    );

    await conn.query("LOAD 'fhirpath.duckdb_extension.wasm'");
    await conn.query("LOAD 'cql.duckdb_extension.wasm'");
  } catch (err) {
    throw new Error(
      `FHIR4DS DuckDB extension load failed from ${workerBase}/. Check that fhirpath.duckdb_extension.wasm and cql.duckdb_extension.wasm are deployed alongside duckdb-browser-eh.worker.js and served with cross-origin isolation. ${errorMessage(err)}`,
    );
  }
}

function assertCrossOriginIsolation() {
  if (typeof window === "undefined") return;
  if (window.crossOriginIsolated) return;
  throw new Error(
    "SharedArrayBuffer is unavailable because the page is not cross-origin isolated. Confirm COOP/COEP headers or the COI service worker are active.",
  );
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
