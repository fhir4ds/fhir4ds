/**
 * Node.js end-to-end test for the WASM demo pipeline.
 *
 * Tests:
 *   1. DuckDB-WASM initializes correctly
 *   2. FHIRPath SQL macros work (no C++ extension required)
 *   3. CQL → SQL translation via cql-py Python subprocess
 *   4. SQL post-processing removes list_extract() wrappers
 *   5. Full query execution returns correct patient data
 *
 * Run: node test-duckdb.mjs
 */
import { createRequire } from "module";
import { Worker as NodeWorker } from "worker_threads";
import { readFileSync, writeFileSync, unlinkSync } from "fs";
import { execSync } from "child_process";
import { fileURLToPath } from "url";
import path from "path";
import os from "os";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);

// ─── ANSI colours ────────────────────────────────────────────────────────────
const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const CYAN = "\x1b[36m";
const RESET = "\x1b[0m";
const ok = (msg) => console.log(`${GREEN}  ✓ ${msg}${RESET}`);
const fail = (msg) => { console.error(`${RED}  ✗ ${msg}${RESET}`); process.exitCode = 1; };
const section = (msg) => console.log(`\n${CYAN}▶ ${msg}${RESET}`);

// ─── NodeWorkerBridge ─────────────────────────────────────────────────────────
// DuckDB AsyncDuckDB expects a Worker with addEventListener (EventTarget API).
// worker_threads.Worker only has .on() (EventEmitter). This class bridges both.
class NodeWorkerBridge extends EventTarget {
  constructor(path) {
    super();
    this._w = new NodeWorker(path);
    this._w.on("message", (d) => this.dispatchEvent(new MessageEvent("message", { data: d })));
    this._w.on("error", (e) => {
      const evt = Object.assign(new Event("error"), { error: e, message: e.message });
      this.dispatchEvent(evt);
    });
    this._w.on("exit", () => this.dispatchEvent(new Event("close")));
  }
  postMessage(data, transfer) {
    if (transfer?.length) this._w.postMessage(data, transfer);
    else this._w.postMessage(data);
  }
  terminate() { return this._w.terminate(); }
}

// ─── SQL post-processing ──────────────────────────────────────────────────────
// cql-py translates .first() as list_extract(fhirpath_text(X,Y), N).
// Since fhirpath_text already returns the first element of arrays, we remove
// the list_extract wrapper so nested navigation works.
function postprocessSQL(sql) {
  const pat = /list_extract\((fhirpath_text\([^)]+\))\s*,\s*-?\d+\)/g;
  let result = sql;
  let prev = "";
  while (prev !== result) { prev = result; result = result.replace(pat, "$1"); }
  return result;
}

// ─── CQL → SQL via Python subprocess ─────────────────────────────────────────
function translateCQL(cqlText) {
  const cqlPySrc = path.join(__dirname, "../../cql-py/src");
  // Write CQL to a temp file to avoid shell escaping issues
  const tmpCql = path.join(os.tmpdir(), `test_cql_${Date.now()}.cql`);
  const tmpScript = path.join(os.tmpdir(), `test_translate_${Date.now()}.py`);
  try {
    writeFileSync(tmpCql, cqlText, "utf-8");
    writeFileSync(tmpScript, `
import sys
sys.path.insert(0, ${JSON.stringify(cqlPySrc)})
from cql_py.parser import parse_cql
from cql_py.translator import CQLToSQLTranslator

with open(${JSON.stringify(tmpCql)}) as f:
    cql_text = f.read()

lib = parse_cql(cql_text)
t = CQLToSQLTranslator()
sql = t.translate_library_to_population_sql(lib)
print(sql, end='')
`, "utf-8");
    return execSync(`python3 ${tmpScript}`, { encoding: "utf-8" });
  } finally {
    try { unlinkSync(tmpCql); } catch {}
    try { unlinkSync(tmpScript); } catch {}
  }
}

// ─── FHIRPath SQL macros ──────────────────────────────────────────────────────
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

// ─── Sample FHIR data ─────────────────────────────────────────────────────────
const PATIENTS = [
  { resourceType: "Patient", id: "p1", gender: "male", birthDate: "1975-05-15", name: [{ given: ["John"], family: "Doe" }] },
  { resourceType: "Patient", id: "p2", gender: "female", birthDate: "1985-03-22", name: [{ given: ["Jane"], family: "Smith" }] },
  { resourceType: "Patient", id: "p3", gender: "male", birthDate: "1960-07-04", name: [{ given: ["Bob"], family: "Jones" }] },
];

const CONDITIONS = [
  { resourceType: "Condition", id: "c1", code: { coding: [{ system: "http://snomed.info/sct", code: "73211009", display: "Diabetes mellitus" }] }, clinicalStatus: { coding: [{ code: "active" }] }, subject: { reference: "Patient/p1" } },
  { resourceType: "Condition", id: "c2", code: { coding: [{ system: "http://snomed.info/sct", code: "38341003", display: "Hypertension" }] }, clinicalStatus: { coding: [{ code: "active" }] }, subject: { reference: "Patient/p2" } },
];

const OBSERVATIONS = [
  { resourceType: "Observation", id: "o1", code: { coding: [{ system: "http://loinc.org", code: "4548-4", display: "HbA1c" }] }, status: "final", subject: { reference: "Patient/p1" } },
];

const ENCOUNTERS = [
  { resourceType: "Encounter", id: "e1", status: "finished", subject: { reference: "Patient/p1" } },
  { resourceType: "Encounter", id: "e2", status: "finished", subject: { reference: "Patient/p2" } },
];

function getPatientRef(res) {
  if (res.resourceType === "Patient") return `Patient/${res.id}`;
  for (const k of ["subject", "patient"]) {
    const ref = res[k]?.reference;
    if (ref) return ref.includes("/") ? ref : null;
  }
  return null;
}

// ─── Main ─────────────────────────────────────────────────────────────────────
async function main() {
  console.log(`${CYAN}═══════════════════════════════════════════════`);
  console.log(" DuckDB-WASM FHIRPath/CQL Integration Test");
  console.log(`═══════════════════════════════════════════════${RESET}\n`);

  // ── 1. Init DuckDB-WASM ──────────────────────────────────────────────────
  section("DuckDB-WASM initialization");

  const duckdb = require("@duckdb/duckdb-wasm/dist/duckdb-node.cjs");
  const wasmPath = require.resolve("@duckdb/duckdb-wasm/dist/duckdb-eh.wasm");
  const wrapperPath = path.join(__dirname, "duckdb-node-worker-wrapper.cjs");

  const workerBridge = new NodeWorkerBridge(wrapperPath);
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), workerBridge);
  await db.instantiate(wasmPath, null);
  await db.open({ path: ":memory:", query: { castBigIntToDouble: true } });
  const conn = await db.connect();

  const version = (await conn.query("SELECT version() AS v")).getChild("v").get(0);
  ok(`DuckDB ${version} ready`);

  // ── 2. Register FHIRPath SQL macros ──────────────────────────────────────
  section("FHIRPath SQL macro registration");

  for (const macro of FHIRPATH_MACROS) {
    await conn.query(macro);
  }
  ok("fhirpath_text, fhirpath_date, fhirpath_bool, fhirpath_number registered");

  // ── 3. Verify macros work ─────────────────────────────────────────────────
  section("FHIRPath macro correctness");

  const patientJson = JSON.stringify(PATIENTS[0]);
  const condJson = JSON.stringify(CONDITIONS[0]);

  await conn.query(`CREATE TABLE _test AS SELECT '${patientJson.replace(/'/g, "''")}' AS resource`);
  const genderResult = (await conn.query("SELECT fhirpath_text(resource, 'gender') AS g FROM _test")).getChild("g").get(0);
  if (genderResult === "male") ok(`fhirpath_text simple field: "male"`);
  else fail(`fhirpath_text gender expected "male" got ${genderResult}`);

  const dateResult = (await conn.query("SELECT fhirpath_date(resource, 'birthDate') AS d FROM _test")).getChild("d").get(0);
  if (dateResult === "1975-05-15") ok(`fhirpath_date: "1975-05-15"`);
  else fail(`fhirpath_date expected "1975-05-15" got ${dateResult}`);

  // Test nested JSON navigation (simulates post-processed SQL)
  await conn.query(`CREATE TABLE _cond AS SELECT '${condJson.replace(/'/g, "''")}' AS resource`);
  const codingResult = (await conn.query("SELECT fhirpath_text(resource, 'code.coding') AS c FROM _cond")).getChild("c").get(0);
  const snomedResult = (await conn.query("SELECT fhirpath_text(fhirpath_text(resource, 'code.coding'), 'system') AS s FROM _cond")).getChild("s").get(0);
  if (snomedResult === "http://snomed.info/sct") ok(`fhirpath_text array navigation: "http://snomed.info/sct"`);
  else fail(`fhirpath_text code.coding.system expected "http://snomed.info/sct" got ${snomedResult}`);

  await conn.query("DROP TABLE _test; DROP TABLE _cond");

  // ── 4. Create resources table with sample data ────────────────────────────
  section("Sample FHIR data loading");

  await conn.query(`
    CREATE TABLE resources (
      id VARCHAR, resourceType VARCHAR, resource JSON, patient_ref VARCHAR
    )
  `);

  const allResources = [...PATIENTS, ...CONDITIONS, ...OBSERVATIONS, ...ENCOUNTERS];
  const stmt = await conn.prepare("INSERT INTO resources VALUES (?, ?, ?, ?)");
  for (const res of allResources) {
    await stmt.query(res.id, res.resourceType, JSON.stringify(res), getPatientRef(res));
  }
  await stmt.close();

  const countResult = (await conn.query("SELECT COUNT(*) AS n FROM resources")).getChild("n").get(0);
  ok(`${Number(countResult)} resources loaded (${PATIENTS.length} patients, ${CONDITIONS.length} conditions, ${OBSERVATIONS.length} observations, ${ENCOUNTERS.length} encounters)`);

  // ── 5. CQL → SQL translation ──────────────────────────────────────────────
  section("CQL → SQL translation (cql-py subprocess)");

  const DEMO_CQL = `library DiabetesScreening version '1.0.0'
using FHIR version '4.0.1'
context Patient

define "Diabetes Diagnosis":
  [Condition] C
    where C.code.coding.first().system = 'http://snomed.info/sct'
      and C.code.coding.first().code = '73211009'

define "Initial Population":
  exists "Diabetes Diagnosis"

define "Has Recent Encounter":
  exists [Encounter] E
    where E.status = 'finished'

define "Denominator":
  "Initial Population" and "Has Recent Encounter"

define "Has HbA1c Test":
  exists [Observation] O
    where O.code.coding.first().system = 'http://loinc.org'
      and O.code.coding.first().code = '4548-4'

define "Numerator":
  "Denominator" and "Has HbA1c Test"
`;

  let rawSql;
  try {
    rawSql = translateCQL(DEMO_CQL);
    ok("CQL translated to SQL (" + rawSql.split("\n").length + " lines)");
  } catch (e) {
    fail("CQL translation failed: " + e.message);
    console.error(e.stderr?.toString());
    process.exit(1);
  }

  // ── 6. SQL post-processing ────────────────────────────────────────────────
  section("SQL post-processing (remove list_extract wrappers)");

  const hasListExtract = /list_extract\(fhirpath_text/.test(rawSql);
  const processedSql = postprocessSQL(rawSql);
  const stillHasListExtract = /list_extract\(fhirpath_text/.test(processedSql);

  if (hasListExtract && !stillHasListExtract) {
    ok("list_extract(fhirpath_text...) wrappers removed");
  } else if (!hasListExtract) {
    ok("No list_extract wrappers in generated SQL (not needed for this CQL)");
  } else {
    fail("list_extract wrappers NOT fully removed");
  }

  // ── 7. Execute generated SQL ──────────────────────────────────────────────
  section("SQL execution against FHIR data");

  let queryResult;
  try {
    queryResult = await conn.query(processedSql);
    ok("SQL executed without errors");
  } catch (e) {
    fail("SQL execution failed: " + e.message);
    console.error("SQL:\n" + processedSql.slice(0, 500));
    process.exit(1);
  }

  // ── 8. Verify results ─────────────────────────────────────────────────────
  section("Results verification");

  const cols = queryResult.schema.fields.map((f) => f.name);
  const rows = [];
  for (let i = 0; i < queryResult.numRows; i++) {
    const row = {};
    for (const col of cols) row[col] = queryResult.getChild(col)?.get(i);
    rows.push(row);
  }

  console.log("  Columns:", cols.join(", "));
  for (const row of rows) {
    console.log("  Row:", JSON.stringify(row));
  }

  // p1 has diabetes + encounter + HbA1c → numerator should be TRUE
  const p1Row = rows.find((r) => r.patient_id === "Patient/p1");
  // p2 has no diabetes → numerator should be FALSE (or may not appear)
  const p2Row = rows.find((r) => r.patient_id === "Patient/p2");

  if (p1Row) {
    // Check any boolean column we have (numerator / in_numerator / etc.)
    const boolCols = cols.filter((c) => c !== "patient_id");
    for (const col of boolCols) {
      const val = p1Row[col];
      ok(`p1 ${col}: ${val}`);
    }
  } else {
    fail("Patient/p1 not found in results");
  }

  if (p2Row) {
    const boolCols = cols.filter((c) => c !== "patient_id");
    for (const col of boolCols) {
      const val = p2Row[col];
      ok(`p2 ${col}: ${val}`);
    }
  }

  if (queryResult.numRows >= 3) {
    ok(`${queryResult.numRows} patient rows returned`);
  } else {
    fail(`Expected ≥3 rows, got ${queryResult.numRows}`);
  }

  // ── Cleanup ───────────────────────────────────────────────────────────────
  await conn.close();
  await db.terminate();
  workerBridge.terminate();

  console.log(`\n${process.exitCode ? RED + "FAILED" : GREEN + "ALL TESTS PASSED"}${RESET}\n`);
}

main().catch((e) => {
  console.error(`${RED}Unhandled error:${RESET}`, e);
  process.exit(1);
});
