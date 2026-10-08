import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let server = null;
let dir = "";

test.beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "v3msr-"));
  mkdirSync(join(dir, "cql"), { recursive: true });
  mkdirSync(join(dir, "valuesets"), { recursive: true });
  mkdirSync(join(dir, "data"), { recursive: true });
  writeFileSync(
    join(dir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "",
      'valueset "BPVS": \'http://example.com/bp\'',
      "",
      "// # %% [name: InIp]",
      "define InIp: true",
      "",
      "// # %% [name: HasBp]",
      'define HasBp: exists([Observation] O where O.code in "BPVS")',
      "",
      "// # %% [name: BirthYear]",
      "define BirthYear: year from Patient.birthDate",
      "",
    ].join("\n"),
  );
  writeFileSync(
    join(dir, "valuesets", "vs1.json"),
    JSON.stringify(
      {
        resourceType: "ValueSet",
        id: "vs1",
        url: "http://example.com/bp",
        compose: {
          include: [
            {
              system: "http://loinc.org",
              concept: [{ code: "8480-6", display: "BP" }],
            },
          ],
        },
      },
      null,
      2,
    ),
  );
  const resources = [];
  for (let i = 1; i <= 6; i++) {
    resources.push(
      JSON.stringify({
        resourceType: "Patient",
        id: "p" + i,
        gender: i % 2 === 1 ? "male" : "female",
        birthDate: i % 2 === 1 ? "1974-12-25" : "1990-01-01",
      }),
    );
    if (i % 2 === 1) {
      resources.push(
        JSON.stringify({
          resourceType: "Observation",
          id: "obs" + i,
          status: "final",
          code: {
            coding: [{ system: "http://loinc.org", code: "8480-6" }],
          },
          subject: { reference: "Patient/p" + i },
        }),
      );
    }
  }
  writeFileSync(join(dir, "data", "patients.ndjson"), resources.join("\n") + "\n");

  server = spawn("/usr/bin/python3", ["-m", "fhir4ds.cli", "dev", dir, "--port", "18971", "--no-open"], {
    env: {
      PYTHONPATH: "/mnt/d/fhir4ds-vsac-cleanroom-20261008",
      PATH: process.env.PATH ?? "",
    },
    stdio: "ignore",
    cwd: dir,
  });
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch("http://127.0.0.1:18971/health");
      if (r.ok) break;
    } catch {
      /* retry */
    }
    await new Promise((res) => setTimeout(res, 500));
  }
}, 120000);

test.afterAll(async () => {
  if (server) {
    server.kill("SIGKILL");
    await new Promise<void>((resolve) => {
      if (server.exitCode !== null) return resolve();
      server.once("exit", () => resolve());
      setTimeout(resolve, 5000);
    });
  }
  try {
    if (dir) rmSync(dir, { recursive: true, force: true });
  } catch {
    /* ignore */
  }
});

test.beforeEach(async ({ page }) => {
  await page.goto("http://127.0.0.1:18971/");
});

test("measure pane: Run disabled until scoring + initial-population mapped", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected", { hasText: "Demographics" })).toBeVisible({ timeout: 15000 });
  await page.locator(".dev-lib.small", { hasText: "Demographics scaffold" }).click();
  const pane = page.locator(".dev-mspane");
  await expect(pane).toBeVisible();
  const run = pane.getByRole("button", { name: "▶ Run measure" });
  await expect(run).toBeDisabled();
  // Ungated reason text is visible beside the disabled Run button.
  await expect(pane.locator(".dev-msrunreason")).toContainText(
    "Select scoring + map initial-population to run",
  );
  // Set scoring but leave initial-population unmapped — still disabled.
  await pane.locator("select").first().selectOption("proportion");
  await expect(run).toBeDisabled();
  await expect(pane.locator(".dev-msrunreason")).toBeVisible();
});

test("measure pane: dropdowns filter to Boolean defines; UNMAPPED + chips are clickable", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected", { hasText: "Demographics" })).toBeVisible({ timeout: 15000 });
  await page.locator(".dev-lib.small", { hasText: "Demographics scaffold" }).click();
  const pane = page.locator(".dev-mspane");
  await expect(pane).toBeVisible();

  // define-types fetched from the server: Boolean defines selectable, non-Boolean hidden w/ note.
  // (Playwright treats <option> elements as hidden — assert via count, not visibility.)
  const ipRow = pane.locator(".dev-msgrid tbody tr").nth(0).locator("select");
  await expect(ipRow.locator("option", { hasText: "InIp" })).toHaveCount(1, { timeout: 20000 });
  await expect(ipRow.locator("option", { hasText: "HasBp" })).toHaveCount(1);
  await expect(ipRow.locator("option", { hasText: "BirthYear" })).toHaveCount(0);
  await expect(pane.locator(".dev-msnote")).toContainText("1 non-Boolean define hidden");
  await expect(pane.locator(".dev-msnote")).toContainText("BirthYear");

  // UNMAPPED badge is a button focusing the initial-population select.
  await pane.locator(".dev-mswarn", { hasText: "UNMAPPED" }).click();
  await expect(ipRow).toBeFocused();

  // Unmapped-define chip (InIp unmapped so far) is a button focusing the IP row.
  await pane.locator(".dev-mschip", { hasText: "InIp exists but unmapped" }).click();
  await expect(ipRow).toBeFocused();
});

test("measure pane: scaffold → map → run shows counts", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected", { hasText: "Demographics" })).toBeVisible({ timeout: 15000 });
  await page.locator(".dev-lib.small", { hasText: "Demographics scaffold" }).click();
  const pane = page.locator(".dev-mspane");
  await expect(pane).toBeVisible();

  await pane.locator("select").first().selectOption("proportion");
  // Mapping selects inside the grid rows: grid row 1 = initial-population.
  await pane.locator(".dev-msgrid tbody tr").nth(0).locator("select").selectOption("InIp");
  await pane.locator(".dev-msgrid tbody tr").nth(4).locator("select").selectOption("HasBp");

  await pane.getByRole("button", { name: "Scaffold preview" }).click();
  await expect(pane.locator(".dev-mspreview")).toBeVisible();
  await expect(pane.locator(".dev-mspreview-head")).toContainText("2 populations mapped");

  const run = pane.getByRole("button", { name: "▶ Run measure" });
  await expect(run).toBeEnabled();
  await expect(pane.locator(".dev-msrunreason")).toHaveCount(0);
  await run.click();
  await expect(pane.locator(".dev-mssummary.pass")).toBeVisible({ timeout: 30000 });
  await expect(pane.locator(".dev-mssummary.pass")).toContainText("initial_population: 6");
  await expect(pane.locator(".dev-mssummary.pass")).toContainText("numerator: 3");
  await expect(pane.locator(".dev-mssummary.pass")).toContainText("6 MeasureReports");
});

test("measure pane: expected-MR compare shows normalized diff + canonical warning", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected", { hasText: "Demographics" })).toBeVisible({ timeout: 15000 });
  await page.locator(".dev-lib.small", { hasText: "Demographics scaffold" }).click();
  const pane = page.locator(".dev-mspane");
  await expect(pane).toBeVisible();

  await pane.locator("select").first().selectOption("proportion");
  await pane.locator(".dev-msgrid tbody tr").nth(0).locator("select").selectOption("InIp");
  await pane.locator(".dev-msgrid tbody tr").nth(4).locator("select").selectOption("HasBp");

  // PASS: expected = 6 per-patient MRs w/ IP=1 + numerator=1 on odd patients.
  const mr = (pid: string, num: number, measure: string) => ({
    resourceType: "MeasureReport",
    status: "complete",
    type: "individual",
    measure,
    subject: { reference: "Patient/" + pid },
    group: [
      {
        id: "group-1",
        population: [
          {
            code: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/measure-population", code: "initial-population" }] },
            count: 1,
          },
          {
            code: { coding: [{ system: "http://terminology.hl7.org/CodeSystem/measure-population", code: "numerator" }] },
            count: num,
          },
        ],
      },
    ],
  });
  const liburl = "urn:cleanroom:lib:Demographics";
  const expected = [];
  for (let i = 1; i <= 6; i++) expected.push(mr("p" + i, i % 2 === 1 ? 1 : 0, liburl));

  const exp = pane.locator(".dev-msexpinput");
  await exp.fill(JSON.stringify(expected));
  await pane.getByRole("button", { name: "▶ Compare" }).click();
  await expect(pane.locator(".dev-msdiff")).toBeVisible({ timeout: 30000 });
  await expect(pane.locator(".dev-msdiff .dev-mssummary.pass")).toContainText("PASS");
  await expect(pane.locator(".dev-mscanonical")).toHaveCount(0);

  // FAIL: mismatching numerator counts (all 1) → FAIL + delta row.
  const wrong = expected.map((r) => ({
    ...r,
    group: [
      {
        id: "group-1",
        population: [
          r.group[0].population[0],
          { ...r.group[0].population[1], count: 1 },
        ],
      },
    ],
  }));
  await exp.fill(JSON.stringify(wrong));
  await pane.getByRole("button", { name: "▶ Compare" }).click();
  await expect(pane.locator(".dev-msdiff .dev-mssummary.fail")).toContainText("FAIL", { timeout: 30000 });
  await expect(pane.locator(".dev-msdiffrow").first()).toContainText("numerator");

  // Canonical warning: expected referencing a different measure canonical.
  const alien = expected.map((r) => ({ ...r, measure: "http://example.com/other-measure" }));
  await exp.fill(JSON.stringify(alien));
  await pane.getByRole("button", { name: "▶ Compare" }).click();
  await expect(pane.locator(".dev-mscanonical")).toBeVisible({ timeout: 30000 });
  await expect(pane.locator(".dev-mscanonical")).toContainText("other-measure");
});

test("measure pane: save → load → compare baseline roundtrip + delete", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected", { hasText: "Demographics" })).toBeVisible({ timeout: 15000 });
  await page.locator(".dev-lib.small", { hasText: "Demographics scaffold" }).click();
  const pane = page.locator(".dev-mspane");
  await expect(pane).toBeVisible();

  await pane.locator("select").first().selectOption("proportion");
  await pane.locator(".dev-msgrid tbody tr").nth(0).locator("select").selectOption("InIp");
  await pane.locator(".dev-msgrid tbody tr").nth(4).locator("select").selectOption("HasBp");

  // Run first so the run-results (and Save-as-baseline) appear.
  await pane.getByRole("button", { name: "▶ Run measure" }).click();
  await expect(pane.locator(".dev-mssummary.pass")).toBeVisible({ timeout: 30000 });

  // Save as expected baseline → versioned file + message.
  const save = pane.getByRole("button", { name: "⬒ Save as expected baseline" });
  await save.click();
  await expect(pane.locator(".dev-msbasemsg")).toContainText("Saved", { timeout: 30000 });
  await expect(pane.locator(".dev-msbasemsg")).toContainText("6 reports");

  // Baseline dropdown lists it; Load unwraps into the paste area w/ provenance.
  const sel = pane.locator(".dev-msbaselinesel");
  await expect(sel.locator("option").filter({ hasText: ".baseline.v1.json" })).toHaveCount(1, { timeout: 10000 });
  const optValue = await sel.locator("option").filter({ hasText: ".baseline.v1.json" }).getAttribute("value");
  await sel.selectOption(optValue!);
  await pane.getByRole("button", { name: "Load" }).click();
  await expect(pane.locator(".dev-msexpinput")).not.toHaveValue("", { timeout: 10000 });
  await expect(pane.locator(".dev-msbasemsg")).toContainText("Loaded");
  await expect(pane.locator(".dev-msbasemsg")).toContainText("6 patients");

  // Compare against the loaded baseline → PASS.
  await pane.getByRole("button", { name: "▶ Compare" }).click();
  await expect(pane.locator(".dev-msdiff")).toBeVisible({ timeout: 30000 });
  await expect(pane.locator(".dev-msdiff .dev-mssummary.pass")).toContainText("PASS");

  // Delete: accept the confirm, dropdown resets, message confirms.
  page.once("dialog", (d) => d.accept());
  await pane.getByRole("button", { name: "Delete" }).click();
  await expect(pane.locator(".dev-msbasemsg")).toContainText("Deleted", { timeout: 10000 });
  await expect(sel).toHaveValue("");
});
