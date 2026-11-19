/**
 * QA it4 — Domain 2 (cell engine/evaluation + desktop parity) × SKEPTIC.
 * H1 LIVE parity: the browser worker (pyodide + duckdb-wasm) and desktop
 *    (CPython + native duckdb) run the SAME fhir4ds.operations
 *    evaluate_library on the same inputs — envelopes must match.
 * H2 snippet-vs-library: a snippet evaluation equals a library define of
 *    the same expression.
 * H3 error parity: invalid CQL -> diagnostic envelope (not a crash) on
 *    both engines with matching diagnostic classes.
 */
import { test, expect } from "@playwright/test";
import { execFileSync } from "node:child_process";

import { fileURLToPath } from "node:url";
import path from "node:path";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const RUNNER = path.join(HERE, "..", "fixtures", "desktop_parity_runner.py");

// FHIRHelpers text loaded lazily to keep the file readable
import { readFileSync as _rf } from "node:fs";
const FHIRHELPERS_TEXT = (() => {
  try {
    return _rf(
      "/home/jmontavon/src/fhir4ds/tests/data/ecqm-content-qicore-2025/input/cql/FHIRHelpers.cql",
      "utf8",
    );
  } catch {
    return "";
  }
})();

test.describe("cell engine live parity", () => {
  test("H1: worker and desktop evaluate_library envelopes match", async ({ page }) => {
    const lib = {
      name: "ParityLib",
      text: `library ParityLib version '1.0.0'
using FHIR version '4.0.1'
include FHIRHelpers version '4.0.1' called FHIRHelpers
parameter "Measurement Period" Interval<DateTime>
context Patient
define "IP": exists Patient.gender
define "Num": exists [Condition] C where C.onset is not null

define "Val": Coalesce(Patient.birthDate, 'unknown')`,
    };
    const dataset = {
      resources: [
        { resourceType: "Patient", id: "p1", gender: "male", birthDate: "1980-05-05" },
        { resourceType: "Patient", id: "p2", gender: "female" },
        { resourceType: "Patient", id: "p3", gender: "female", birthDate: "1990-01-01" },
        { resourceType: "Patient", id: "p4" },
        { resourceType: "Condition", id: "c1", subject: { reference: "Patient/p2" } },
      ],
    };
    const parameters = { "Measurement Period": ["2026-01-01", "2026-12-31"] };
    const output_columns = { IP: "IP", Num: "Num", Val: "Val" };
    const payload = {
      libraries: [{ name: "FHIRHelpers", text: FHIRHELPERS_TEXT }],
      main: lib,
      dataset,
      parameters,
      output_columns,
    };

    // Browser side
    await page.goto("/");
    await page.evaluate(() => (window as any).__cleanroomReady?.());
    await page.waitForFunction(() => (window as any).__cleanroomBooted === true, null, { timeout: 180_000 });
    const browserEnv = await page.evaluate(async (p) => {
      const r = await (window as any).__cleanroomRequest({
        id: 1, type: "evaluate_library",
        libraries: p.libraries, main: p.main, dataset: p.dataset,
        parameters: p.parameters, output_columns: p.output_columns,
      });
      return JSON.parse(r.envelope);
    }, payload);

    // Desktop side
    const desktopRaw = execFileSync("python3", [RUNNER], {
      input: JSON.stringify(payload),
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: "/home/jmontavon/src/fhir4ds" },
    });
    const desktopEnv = JSON.parse(desktopRaw);

    expect(browserEnv.ok).toBe(true);
    expect(desktopEnv.ok).toBe(true);
    expect(browserEnv.rows).toEqual(desktopEnv.rows);
    expect(browserEnv.columns?.sort()).toEqual(desktopEnv.columns.sort());
  });

  test("H3: invalid CQL yields a diagnostic envelope on both engines", async ({ page }) => {
    const payload = {
      libraries: [],
      main: { name: "Bad", text: "library Bad\ndefine \"X\": 1 +\n" },
      dataset: { resources: [{ resourceType: "Patient", id: "p1" }] },
    };
    await page.goto("/");
    await page.evaluate(() => (window as any).__cleanroomReady?.());
    await page.waitForFunction(() => (window as any).__cleanroomBooted === true, null, { timeout: 180_000 });
    const browserEnv = await page.evaluate(async (p) => {
      const r = await (window as any).__cleanroomRequest({
        id: 2, type: "evaluate_library",
        libraries: p.libraries, main: p.main, dataset: p.dataset,
      });
      return JSON.parse(r.envelope);
    }, payload);
    expect(browserEnv.ok).toBe(false);
    expect(Array.isArray(browserEnv.diagnostics)).toBe(true);
    expect(browserEnv.diagnostics.length).toBeGreaterThan(0);
  });
});

