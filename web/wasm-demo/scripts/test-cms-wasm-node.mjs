/**
 * Node.js WASM test: validates CMS165 + CMS122 SQL against expected results
 * using DuckDB-WASM with the same wasm_eh C++ extensions served in the browser.
 *
 * Usage:
 *   node apps/wasm-demo/scripts/test-cms-wasm-node.mjs
 *
 * This mirrors what the browser does: loads DuckDB-WASM, loads the WASM
 * fhirpath + cql extensions, inserts FHIR resources from NDJSON, and runs
 * the pre-generated SQL (with valueset CTEs baked in).
 */

import { createRequire } from "module";
import { readFileSync, existsSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { Worker } from "worker_threads";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

const DATA_DIR = path.join(__dirname, "../public/data");
const EXT_DIR  = path.join(__dirname, "../public/extensions");

// DuckDB-WASM Node.js async API
const { AsyncDuckDB, VoidLogger, DuckDBDataProtocol } =
  require("../node_modules/@duckdb/duckdb-wasm/dist/duckdb-node.cjs");

const WASM_EH_WORKER =
  path.join(__dirname, "../node_modules/@duckdb/duckdb-wasm/dist/duckdb-node-eh.worker.cjs");
const WASM_EH =
  path.join(__dirname, "../node_modules/@duckdb/duckdb-wasm/dist/duckdb-eh.wasm");

async function initDuckDB() {
  const worker = new Worker(WASM_EH_WORKER);
  const db = new AsyncDuckDB(new VoidLogger(), worker);
  await db.instantiate(WASM_EH, null);
  await db.open({ path: ":memory:", query: { castBigIntToDouble: true }, allowUnsignedExtensions: true });
  const conn = await db.connect();
  await conn.query("SET allow_unsigned_extensions=true;");
  return { db, conn, worker };
}

async function loadExtensions(db, conn) {
  for (const extName of ["fhirpath.duckdb_extension.wasm", "cql.duckdb_extension.wasm"]) {
    const extPath = path.join(EXT_DIR, extName);
    if (!existsSync(extPath)) throw new Error(`Extension not found: ${extPath}`);
    const bytes = readFileSync(extPath);
    db.registerFileBuffer(extName, new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength));
    await conn.query(`LOAD '${extName}'`);
  }
  console.log("  ✓ C++ extensions loaded (fhirpath + cql)");
}

async function loadResources(conn, measureId) {
  await conn.query(`
    CREATE TABLE IF NOT EXISTS resources (
      id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR
    )
  `);
  await conn.query("DELETE FROM resources");

  const ndjsonPath = path.join(DATA_DIR, `${measureId.toLowerCase()}_resources.ndjson`);
  const lines = readFileSync(ndjsonPath, "utf8").split("\n").filter(Boolean);
  const stmt = await conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
  for (const line of lines) {
    const r = JSON.parse(line);
    const resourceJson = typeof r.resource === "string" ? r.resource : JSON.stringify(r.resource);
    await stmt.query(r.id, r.resourceType, resourceJson, r.patient_ref ?? null);
  }
  await stmt.close();
  return lines.length;
}

async function runMeasure(conn, measureId, year = 2025) {
  let sql = readFileSync(path.join(DATA_DIR, `${measureId.toLowerCase()}.sql`), "utf8");
  // The SQL was generated for year+1 (2026) — shift to target year
  const nextYear = year + 1;
  sql = sql
    .replaceAll(`${nextYear}-01-01T00:00:00.000`, `${year}-01-01T00:00:00.000`)
    .replaceAll(`${nextYear}-12-31T23:59:59.999`, `${year}-12-31T23:59:59.999`)
    .replaceAll(`${year}-01-01T00:00:00.000`, `${year}-01-01T00:00:00.000`);  // idempotent

  const t0 = Date.now();
  const table = await conn.query(sql);
  const ms = Date.now() - t0;
  return { table, ms };
}

function compareExpected(table, measureId) {
  const expectedPath = path.join(DATA_DIR, `${measureId.toLowerCase()}_expected.json`);
  const expected = JSON.parse(readFileSync(expectedPath, "utf8"));

  const cols = table.schema.fields.map(f => f.name);
  let correct = 0, total = 0, wrong = [];

  for (let i = 0; i < table.numRows; i++) {
    const patientId = String(table.getChild(cols[0])?.get(i) ?? "");
    const exp = expected[patientId];
    if (!exp) continue;

    for (let c = 1; c < cols.length; c++) {
      const colName = cols[c];
      const actual = Boolean(table.getChild(colName)?.get(i));
      const expKey = colName.toLowerCase().replace(/\s+/g, "-");
      const expVal = exp[expKey] ?? exp[colName];
      if (expVal === undefined) continue;
      total++;
      if (actual === Boolean(expVal)) {
        correct++;
      } else {
        wrong.push({ patientId, col: colName, actual, expected: expVal });
      }
    }
  }
  return { correct, total, wrong };
}

async function main() {
  console.log("DuckDB-WASM CMS Measures Node.js Test\n");

  let { db, conn, worker } = await initDuckDB();
  console.log("  ✓ DuckDB-WASM initialized\n");

  let extLoaded = false;
  try {
    await loadExtensions(db, conn);
    extLoaded = true;
  } catch (e) {
    console.warn(`  ⚠  Extensions failed: ${e.message}`);
    console.warn("  Running without C++ UDFs — results may differ from browser\n");
  }

  let allPassed = true;

  for (const measureId of ["CMS165", "CMS122"]) {
    console.log(`--- ${measureId} ---`);
    const resourceCount = await loadResources(conn, measureId);
    console.log(`  Loaded ${resourceCount} resources`);

    const { table, ms } = await runMeasure(conn, measureId);
    console.log(`  Executed in ${ms}ms — ${table.numRows} patients`);

    const cols = table.schema.fields.map(f => f.name);
    const popSums = {};
    for (let c = 1; c < cols.length; c++) {
      const colName = cols[c];
      let sum = 0;
      for (let i = 0; i < table.numRows; i++) sum += table.getChild(colName)?.get(i) ? 1 : 0;
      popSums[colName] = sum;
    }
    console.log("  Populations:", popSums);

    const { correct, total, wrong } = compareExpected(table, measureId);
    const pct = total > 0 ? ((correct / total) * 100).toFixed(1) : "n/a";
    const pass = pct === "100.0";
    console.log(`  Accuracy: ${correct}/${total} (${pct}%) ${pass ? "✓ PASS" : "✗ FAIL"}`);
    if (!pass && wrong.length > 0) {
      console.log(`  First 5 differences:`);
      wrong.slice(0, 5).forEach(d =>
        console.log(`    ${d.patientId} :: ${d.col}: got ${d.actual}, expected ${d.expected}`)
      );
      allPassed = false;
    }
    console.log();
  }

  await conn.close();
  await db.terminate();
  worker.terminate();

  if (allPassed) {
    console.log("All measures: ✓ PASS (100% accuracy)");
    process.exit(0);
  } else {
    console.log("Some measures: ✗ FAIL — check differences above");
    process.exit(1);
  }
}

main().catch(e => { console.error(e); process.exit(1); });
