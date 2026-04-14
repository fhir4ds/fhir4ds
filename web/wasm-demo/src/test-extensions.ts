/**
 * Standalone test page: loads DuckDB-WASM with C++ extensions (fhirpath + cql)
 * and runs basic queries to verify everything works.
 *
 * Uses Vite ?url imports for same-origin worker/WASM URLs, which avoids the
 * CORS and blob-URL XHR issues that break extension loading.
 */

import * as duckdb from "@duckdb/duckdb-wasm";
import duckdbWorkerUrl from "@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url";
import duckdbWasmUrl from "@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url";

const logEl = document.getElementById("log")!;
const log = (msg: string, cls = "info") => {
  const span = document.createElement("span");
  span.className = cls;
  span.textContent = msg + "\n";
  logEl.appendChild(span);
  console.log(msg);
};

function renderTable(table: any, containerId: string) {
  const el = document.getElementById(containerId)!;
  const cols: string[] = table.schema.fields.map((f: any) => f.name);
  let html = "<table><tr>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>";
  for (let i = 0; i < table.numRows; i++) {
    html +=
      "<tr>" +
      cols
        .map(c => {
          const v = table.getChild(c)?.get(i);
          return `<td>${v === null ? "null" : v}</td>`;
        })
        .join("") +
      "</tr>";
  }
  html += "</table>";
  el.innerHTML += html;
}

async function clearStaleDuckDBStorage() {
  try {
    if (typeof indexedDB !== "undefined" && typeof indexedDB.databases === "function") {
      const dbs = await indexedDB.databases();
      for (const entry of dbs) {
        if (entry.name && /duckdb/i.test(entry.name)) {
          log(`  Clearing stale IndexedDB: ${entry.name}`, "info");
          await new Promise<void>(res => {
            const req = indexedDB.deleteDatabase(entry.name!);
            req.onsuccess = req.onerror = () => res();
          });
        }
      }
    }
  } catch {
    /* ignore */
  }
}

async function main() {
  try {
    log("Clearing stale DuckDB IndexedDB...", "info");
    await clearStaleDuckDBStorage();

    log("Initializing DuckDB-WASM...", "info");
    log(`  Worker: ${duckdbWorkerUrl}`, "info");
    log(`  WASM:   ${duckdbWasmUrl}`, "info");

    const worker = new Worker(duckdbWorkerUrl);
    const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
    await db.instantiate(duckdbWasmUrl, null);
    log("DuckDB instantiated", "ok");

    await db.open({
      path: ":memory:",
      query: { castBigIntToDouble: true },
      allowUnsignedExtensions: true,
    });
    const conn = await db.connect();
    const ver = (await conn.query("SELECT version() AS v")).getChild("v")!.get(0);
    log(`DuckDB ${ver} ready`, "ok");

    // Load extensions
    const extensions = [
      "fhirpath.duckdb_extension.wasm",
      "cql.duckdb_extension.wasm",
    ];

    for (const extName of extensions) {
      try {
        // Approach: fetch extension bytes in main thread and register as buffer.
        // This avoids Emscripten dlopen resolving paths relative to the worker URL
        // (which points into node_modules, not /extensions/).
        const url = new URL(`extensions/${extName}`, window.location.href).href;
        log(`  Fetching: ${url}`, "info");
        const resp = await fetch(url);
        const buffer = new Uint8Array(await resp.arrayBuffer());
        log(`  Size: ${buffer.length.toLocaleString()} bytes, magic: ${Array.from(buffer.slice(0, 4)).map(b => b.toString(16).padStart(2, "0")).join("")}`, "info");

        await db.registerFileBuffer(extName, buffer);
        log(`  LOAD '${extName}'...`, "info");
        await conn.query(`LOAD '${extName}'`);
        log(`  Loaded: ${extName}`, "ok");
      } catch (e: any) {
        log(`  Failed: ${extName} — ${e.message}`, "fail");
      }
    }

    // Test queries
    log("\n--- Query Tests ---", "info");

    const patient = JSON.stringify({
      resourceType: "Patient",
      id: "p1",
      gender: "male",
      birthDate: "1980-01-01",
      name: [{ given: ["John"], family: "Doe" }],
    }).replace(/'/g, "''");

    try {
      const r1 = await conn.query(
        `SELECT fhirpath('${patient}', 'Patient.name.given') AS given_names`,
      );
      log("fhirpath(Patient.name.given):", "ok");
      renderTable(r1, "results");
    } catch (e: any) {
      log(`fhirpath() failed: ${e.message}`, "fail");
    }

    try {
      const r2 = await conn.query(
        `SELECT fhirpath('${patient}', 'Patient.gender') AS gender`,
      );
      log("fhirpath(Patient.gender):", "ok");
      renderTable(r2, "results");
    } catch (e: any) {
      log(`fhirpath(gender) failed: ${e.message}`, "fail");
    }

    try {
      const r3 = await conn.query(`SELECT AgeInYears('${patient}') AS age`);
      log("AgeInYears():", "ok");
      renderTable(r3, "results");
    } catch (e: any) {
      log(`AgeInYears() failed: ${e.message}`, "fail");
    }

    await conn.close();
    await db.terminate();
    worker.terminate();
    log("\nDone.", "ok");
  } catch (e: any) {
    log(`Fatal: ${e.message}`, "fail");
    console.error(e);
  }
}

main();
