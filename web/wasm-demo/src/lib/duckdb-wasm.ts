import { getAssetBase } from "./asset-base";

// Vite resolves these ?url imports to same-origin local paths. DuckDB's
// Emscripten loader can then resolve extension side modules correctly.
import duckdbWorkerUrl from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbWasmUrl from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";
import { registerCQLMacros } from "./cql-macros";

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

export async function createDuckDBConnection(
  wasmAppUrl?: string,
): Promise<DuckDBConnectionBundle> {
  assertCrossOriginIsolation();

  try {
    const duckdb = await import("@duckdb/duckdb-wasm");
    const worker = new Worker(duckdbWorkerUrl, { type: "classic" });
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    await db.instantiate(duckdbWasmUrl, null);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    await (db.open as any)({
      path: ":memory:",
      query: { castBigIntToDouble: true },
      allowUnsignedExtensions: true,
      autoInstallExtensions: false,
      autoLoadExtensions: false,
    });

    const conn = await db.connect();
    await loadFHIR4DSExtensions(db, conn, wasmAppUrl);
    return { db, conn };
  } catch (err) {
    throw new Error(`DuckDB-WASM startup failed: ${errorMessage(err)}`);
  }
}

async function loadFHIR4DSExtensions(db: any, conn: any, wasmAppUrl?: string) {
  const extBase = `${getAssetBase(wasmAppUrl)}/extensions/`;
  try {
    await db.registerFileURL(
      "fhirpath.duckdb_extension.wasm",
      extBase + "fhirpath.duckdb_extension.wasm",
      4 /* DuckDBDataProtocol.HTTP */,
      false,
    );
    await db.registerFileURL(
      "cql.duckdb_extension.wasm",
      extBase + "cql.duckdb_extension.wasm",
      4 /* DuckDBDataProtocol.HTTP */,
      false,
    );

    await conn.query("LOAD 'fhirpath.duckdb_extension.wasm'");
    await conn.query("LOAD 'cql.duckdb_extension.wasm'");
    await registerCQLMacros(conn);
  } catch (err) {
    throw new Error(
      `FHIR4DS DuckDB extension load failed from ${extBase}. Check that fhirpath.duckdb_extension.wasm and cql.duckdb_extension.wasm are deployed and served with cross-origin isolation. ${errorMessage(err)}`,
    );
  }
}

function assertCrossOriginIsolation() {
  if (typeof window === "undefined") return;
  if (window.crossOriginIsolated) return;
  throw new Error(
    "SharedArrayBuffer is unavailable because the page is not cross-origin isolated. Confirm COOP/COEP headers or the website COI service worker are active.",
  );
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}
