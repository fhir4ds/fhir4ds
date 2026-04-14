/**
 * Node.js WASM API integration tests for CMS165 and CMS122.
 *
 * Uses @duckdb/duckdb-wasm blocking API (DuckDB v1.5.1) to verify that the
 * pre-translated CMS SQL files produce results that match expected.json at
 * ≥99 % accuracy — the same bar used by the Python benchmark runner.
 *
 * Extension loading is not available in Node.js blocking mode (requires async
 * WASM dynamic linking — a browser-only capability). Tests therefore register
 * fhirpath SQL macros as a fallback. The CMS SQL files themselves use only
 * built-in DuckDB JSON functions, so no extension is needed for the CMS tests.
 *
 * Run:
 *   node apps/wasm-demo/test/test-cms-wasm.cjs
 */

"use strict";

const path = require("path");
const fs   = require("fs");

const WASM_DEMO = path.join(__dirname, "..");
const DUCKDB_DIST = path.join(WASM_DEMO, "node_modules/@duckdb/duckdb-wasm/dist");
const DATA_DIR   = path.join(WASM_DEMO, "public/data");

// ─── FHIRPATH SQL MACROS (fallback for Node.js environment) ───────────────────

const FHIRPATH_MACROS = [
  `CREATE OR REPLACE MACRO fhirpath_text(resource, path) AS (
     CASE json_type(json_extract(resource::JSON, '$.' || path))
       WHEN 'ARRAY'
         THEN json_extract_string(resource::JSON, '$.' || path || '[0]')
       ELSE
         COALESCE(
           json_extract_string(resource::JSON, '$[0].' || path),
           json_extract_string(resource::JSON, '$.' || path)
         )
     END
   )`,
  `CREATE OR REPLACE MACRO fhirpath_date(resource, path) AS (
     json_extract_string(resource::JSON, '$.' || path)
   )`,
  `CREATE OR REPLACE MACRO fhirpath_bool(resource, path) AS (
     TRY_CAST(json_extract_string(resource::JSON, '$.' || path) AS BOOLEAN)
   )`,
  `CREATE OR REPLACE MACRO fhirpath_number(resource, path) AS (
     TRY_CAST(json_extract_string(resource::JSON, '$.' || path) AS DOUBLE)
   )`,
];

// ─── HELPERS ─────────────────────────────────────────────────────────────────

function initDB() {
  const dk = require(path.join(WASM_DEMO, "node_modules/@duckdb/duckdb-wasm/dist/duckdb-node-blocking.cjs"));
  const logger = new dk.VoidLogger();
  const bundles = {
    mvp: { mainModule: path.join(DUCKDB_DIST, "duckdb-mvp.wasm"), pthreadWorker: null },
    eh:  { mainModule: path.join(DUCKDB_DIST, "duckdb-eh.wasm"),  pthreadWorker: null },
  };
  // createDuckDB signature: (bundles, logger, runtime) — logger is second arg
  return dk.createDuckDB(bundles, logger, dk.NODE_RUNTIME).then(db => {
    return db.instantiate().then(() => {
      db.open({ path: ":memory:", query: { castBigIntToDouble: true } });
      const conn = db.connect();

      // Register fhirpath SQL macros (not needed by pre-baked CMS SQL but
      // available so any incidental fhirpath_* call succeeds).
      for (const macro of FHIRPATH_MACROS) {
        conn.query(macro);
      }

      conn.query(`CREATE TABLE resources (
        id VARCHAR,
        resourceType VARCHAR,
        resource JSON,
        patient_ref VARCHAR
      )`);

      return { db, conn };
    });
  });
}

function loadNdjson(conn, filePath) {
  conn.query("DELETE FROM resources");
  const lines = fs.readFileSync(filePath, "utf8").split("\n").filter(Boolean);
  const insert = conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
  for (const line of lines) {
    const r = JSON.parse(line);
    const resourceJson = typeof r.resource === "string" ? r.resource : JSON.stringify(r.resource);
    insert.query(r.id, r.resourceType, resourceJson, r.patient_ref ?? null);
  }
  insert.close();
  return lines.length;
}

function parameteriseSql(sql, year) {
  // The pre-baked SQL was generated with year+1 timestamps (e.g. 2026 for 2025 data).
  // Replace only those hardcoded year+1 timestamps; the SQL has no prior-year refs.
  const sqlYear = year + 1;
  return sql
    .replaceAll(`${sqlYear}-01-01T00:00:00.000`, `${year}-01-01T00:00:00.000`)
    .replaceAll(`${sqlYear}-12-31T23:59:59.999`, `${year}-12-31T23:59:59.999`);
}

function runMeasureSql(conn, sql) {
  const result = conn.query(sql);
  const cols = result.schema.fields.map(f => f.name);
  const rows = [];
  for (let i = 0; i < result.numRows; i++) {
    const row = {};
    for (const col of cols) {
      row[col] = result.getChild(col)?.get(i) ?? null;
    }
    rows.push(row);
  }
  return { rows, cols };
}

function computeAccuracy(rows, expected, populationCols) {
  // Map SQL column names to expected.json keys.
  // SQL uses plural "Denominator Exclusions"; expected.json uses singular "denominator-exclusion".
  const COL_KEY_MAP = {
    "denominator-exclusions": "denominator-exclusion",
  };

  let correct = 0;
  let total   = 0;

  for (const row of rows) {
    const patientId = row[Object.keys(row)[0]]; // first col is patient_id
    const exp = expected[patientId];
    if (!exp) continue;

    for (const col of populationCols) {
      let expKey = col.toLowerCase().replace(/\s+/g, "-");
      expKey = COL_KEY_MAP[expKey] ?? expKey;
      const expVal = exp[expKey] ?? exp[col];
      if (expVal === undefined) continue;
      total++;
      if (Boolean(row[col]) === Boolean(expVal)) correct++;
    }
  }

  return total > 0 ? { correct, total, pct: (correct / total) * 100 } : null;
}

// ─── TEST RUNNER ─────────────────────────────────────────────────────────────

async function runTest(label, fn) {
  process.stdout.write(`  ${label} ... `);
  try {
    await fn();
    console.log("PASS");
    return true;
  } catch (err) {
    console.log("FAIL");
    console.error(`    ${err.message}`);
    return false;
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message || "Assertion failed");
}

// ─── MAIN ────────────────────────────────────────────────────────────────────

async function main() {
  console.log("\n=== DuckDB-WASM CMS Measure Tests (Node.js blocking API) ===");
  console.log(`DuckDB version: loading...`);

  const { db, conn } = await initDB();

  // Print the DuckDB version so we know what we're testing against
  const versionResult = conn.query("SELECT version() as v");
  console.log(`DuckDB version: ${versionResult.toArray()[0].v}\n`);

  let passed = 0;
  let failed = 0;

  async function test(label, fn) {
    const ok = await runTest(label, fn);
    if (ok) passed++; else failed++;
  }

  // ── Baseline: fhirpath macros work ────────────────────────────────────────

  await test("fhirpath_text macro returns first scalar", async () => {
    const r = conn.query(`SELECT fhirpath_text('{"id":"p1","name":"Alice"}'::JSON, 'id') as v`);
    assert(r.toArray()[0].v === "p1", `Expected 'p1', got '${r.toArray()[0].v}'`);
  });

  await test("fhirpath_text macro returns first array element", async () => {
    const r = conn.query(`SELECT fhirpath_text('{"given":["Alice","Bob"]}'::JSON, 'given') as v`);
    assert(r.toArray()[0].v === "Alice", `Expected 'Alice', got '${r.toArray()[0].v}'`);
  });

  // ── CMS165 ────────────────────────────────────────────────────────────────

  console.log("\nCMS165 – Controlling High Blood Pressure:");

  await test("NDJSON loads without error", async () => {
    const n = loadNdjson(conn, path.join(DATA_DIR, "cms165_resources.ndjson"));
    assert(n > 0, `Expected > 0 resources, got ${n}`);
    console.log(`\n    (${n} resources loaded)`);
  });

  let cms165Rows, cms165Cols;
  await test("SQL executes successfully", async () => {
    const sqlRaw = fs.readFileSync(path.join(DATA_DIR, "cms165.sql"), "utf8");
    // SQL and expected.json were generated for measurement year 2026 — use as-is.
    const sql = parameteriseSql(sqlRaw, 2026);
    const start = Date.now();
    const result = runMeasureSql(conn, sql);
    const ms = Date.now() - start;
    cms165Rows = result.rows;
    cms165Cols = result.cols;
    assert(cms165Rows.length > 0, "Expected at least 1 patient row");
    console.log(`\n    (${cms165Rows.length} patients, ${ms}ms)`);
  });

  await test("Patient count matches resource file", async () => {
    // 68 distinct patients in the CMS165 test dataset
    const countR = conn.query("SELECT COUNT(DISTINCT patient_ref) as n FROM resources WHERE patient_ref IS NOT NULL");
    const patientCount = Number(countR.toArray()[0].n);
    assert(patientCount > 0, `Expected patients, got ${patientCount}`);
    assert(cms165Rows.length === patientCount,
      `Expected ${patientCount} rows, got ${cms165Rows.length}`);
  });

  await test("Required population columns present", async () => {
    const popCols = ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"];
    for (const col of popCols) {
      assert(cms165Cols.includes(col), `Missing column: ${col}`);
    }
  });

  await test("Accuracy ≥ 99 % vs expected.json", async () => {
    const expected = JSON.parse(fs.readFileSync(path.join(DATA_DIR, "cms165_expected.json"), "utf8"));
    const popCols = cms165Cols.slice(1);
    const acc = computeAccuracy(cms165Rows, expected, popCols);
    assert(acc !== null, "Could not compute accuracy (no matching patients)");
    const pct = acc.pct.toFixed(1);
    console.log(`\n    (${acc.correct}/${acc.total} correct = ${pct}%)`);
    assert(acc.pct >= 99.0, `Accuracy ${pct}% < 99%`);
  });

  // ── CMS122 ────────────────────────────────────────────────────────────────

  console.log("\nCMS122 – Diabetes HbA1c Poor Control:");

  await test("NDJSON loads without error", async () => {
    const n = loadNdjson(conn, path.join(DATA_DIR, "cms122_resources.ndjson"));
    assert(n > 0, `Expected > 0 resources, got ${n}`);
    console.log(`\n    (${n} resources loaded)`);
  });

  let cms122Rows, cms122Cols;
  await test("SQL executes successfully", async () => {
    const sqlRaw = fs.readFileSync(path.join(DATA_DIR, "cms122.sql"), "utf8");
    // SQL and expected.json were generated for measurement year 2026 — use as-is.
    const sql = parameteriseSql(sqlRaw, 2026);
    const start = Date.now();
    const result = runMeasureSql(conn, sql);
    const ms = Date.now() - start;
    cms122Rows = result.rows;
    cms122Cols = result.cols;
    assert(cms122Rows.length > 0, "Expected at least 1 patient row");
    console.log(`\n    (${cms122Rows.length} patients, ${ms}ms)`);
  });

  await test("Required population columns present", async () => {
    const popCols = ["Initial Population", "Denominator", "Denominator Exclusions", "Numerator"];
    for (const col of popCols) {
      assert(cms122Cols.includes(col), `Missing column: ${col}`);
    }
  });

  await test("Accuracy ≥ 99 % vs expected.json", async () => {
    const expected = JSON.parse(fs.readFileSync(path.join(DATA_DIR, "cms122_expected.json"), "utf8"));
    const popCols = cms122Cols.slice(1);
    const acc = computeAccuracy(cms122Rows, expected, popCols);
    assert(acc !== null, "Could not compute accuracy (no matching patients)");
    const pct = acc.pct.toFixed(1);
    console.log(`\n    (${acc.correct}/${acc.total} correct = ${pct}%)`);
    assert(acc.pct >= 99.0, `Accuracy ${pct}% < 99%`);
  });

  // ── Population sanity checks ──────────────────────────────────────────────

  console.log("\nCMS165 population sanity:");

  await test("Numerator ⊆ Denominator", async () => {
    for (const row of cms165Rows) {
      if (row["Numerator"]) {
        assert(row["Denominator"], `Patient ${row[cms165Cols[0]]}: Numerator=true but Denominator=false`);
      }
    }
  });

  await test("Denominator ⊆ Initial Population", async () => {
    for (const row of cms165Rows) {
      if (row["Denominator"]) {
        assert(row["Initial Population"], `Patient ${row[cms165Cols[0]]}: Denominator=true but IP=false`);
      }
    }
  });

  console.log("\nCMS122 population sanity:");

  await test("Numerator ⊆ Denominator", async () => {
    for (const row of cms122Rows) {
      if (row["Numerator"]) {
        assert(row["Denominator"], `Patient ${row[cms122Cols[0]]}: Numerator=true but Denominator=false`);
      }
    }
  });

  // ── Summary ───────────────────────────────────────────────────────────────

  conn.close();
  // Note: DuckDB blocking API does not expose a terminate() method; the DB is
  // cleaned up when the process exits.

  console.log(`\n${"─".repeat(50)}`);
  console.log(`Results: ${passed} passed, ${failed} failed`);
  if (failed > 0) {
    console.error("FAIL");
    process.exit(1);
  } else {
    console.log("All tests PASSED ✓");
  }
}

main().catch(err => {
  console.error("Fatal error:", err);
  process.exit(1);
});
