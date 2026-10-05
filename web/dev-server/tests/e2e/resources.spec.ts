import { test, expect } from "@playwright/test";
import { spawn } from "node:child_process";
import { mkdtempSync, writeFileSync, mkdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

let server = null;
let dir = "";

test.beforeAll(async () => {
  dir = mkdtempSync(join(tmpdir(), "v3res-"));
  mkdirSync(join(dir, "cql"), { recursive: true });
  mkdirSync(join(dir, "valuesets"), { recursive: true });
  mkdirSync(join(dir, "data"), { recursive: true });
  writeFileSync(
    join(dir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "",
      'parameter "MinAge" Integer default 18',
      "",
      "// # %% [name: IsMale]",
      "define IsMale: Patient.gender = 'male'",
      "",
    ].join("\n"),
  );
  writeFileSync(
    join(dir, "valuesets", "vs1.json"),
    JSON.stringify(
      {
        resourceType: "ValueSet",
        id: "vs1",
        url: "http://example.com/vs1",
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
  const patients = [];
  for (let i = 1; i <= 6; i++) {
    patients.push(
      JSON.stringify({
        resourceType: "Patient",
        id: "p" + i,
        gender: i % 2 === 1 ? "male" : "female",
        birthDate: i % 2 === 1 ? "1974-12-25" : "1990-01-01",
      }),
    );
  }
  writeFileSync(join(dir, "data", "patients.ndjson"), patients.join("\n") + "\n");

  server = spawn("/usr/bin/python3", ["-m", "fhir4ds.cli", "dev", dir, "--port", "18901", "--no-open"], {
    env: {
      PYTHONPATH: "/mnt/d/fhir4ds-devserver-v3-20261005",
      PATH: process.env.PATH ?? "",
    },
    stdio: "ignore",
  });
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch("http://127.0.0.1:18901/health");
      if (r.ok) break;
    } catch {
      /* retry */
    }
    await new Promise((res) => setTimeout(res, 500));
  }
}, 120000);

test.afterAll(() => {
  if (server) server.kill();
  try {
    if (dir) rmSync(dir, { recursive: true, force: true });
  } catch {
    /* ignore */
  }
});

test.beforeEach(async ({ page }) => {
  await page.goto("http://127.0.0.1:18901/");
});

test("valueset pane renders, edits, and shows the stale badge", async ({ page }) => {
  await expect(page.locator(".dev-lib", { hasText: "vs1" })).toBeVisible({ timeout: 15000 });
  await page.locator(".dev-lib", { hasText: "vs1" }).click();
  await expect(page.locator(".dev-vspane")).toBeVisible();
  await expect(page.locator(".dev-vsrow")).toHaveCount(2); // head + 1 concept
  await expect(page.locator(".dev-vsurl")).toHaveText("http://example.com/vs1");
  // add a concept server-side
  await page.locator("button", { hasText: "+ concept" }).click();
  await expect(page.locator(".dev-vsrow")).toHaveCount(3, { timeout: 10000 });
  await expect(page.locator(".dev-stale").first()).toBeVisible();
});

test("params table shows the declared parameter and can delete it", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected")).toHaveText("Demographics", { timeout: 15000 });
  await page.locator("button", { hasText: "header" }).click();
  await expect(page.locator(".dev-paramspane")).toBeVisible();
  await expect(page.locator(".dev-paramstable tbody tr")).toHaveCount(1);
  await expect(page.locator(".dev-paramstable")).toContainText("MinAge");
  // delete the parameter — the buffer adopts the transformed text
  await page.locator(".dev-paramstable tbody tr button").click();
  await expect(page.locator(".dev-paramstable")).toContainText("No parameters", { timeout: 10000 });
});

test("tests grid: patient dropdown populated, case runs green", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected")).toHaveText("Demographics", { timeout: 15000 });
  await expect(page.locator(".dev-testspane")).toBeVisible();
  // wait until the patients dropdown is fed by the loaded dataset
  await expect(page.locator("button", { hasText: "+ case" })).toBeEnabled({ timeout: 15000 });
  await page.locator("button", { hasText: "+ case" }).click();
  await expect(page.locator(".dev-testgrid .dev-vsrow")).toHaveCount(2); // head + 1 case
  const patientSelect = page.locator(".dev-testgrid .dev-vsrow").nth(1).locator("select").first();
  await expect(patientSelect.locator("option", { hasText: "p1" })).toBeAttached({ timeout: 10000 });
  const opts = await patientSelect.locator("option").allTextContents();
  expect(opts.filter((o) => /^p\d$/.test(o)).length).toBe(6);
  // IsMale for p1 (male) should pass
  await page.locator("button", { hasText: "Run tests" }).click();
  await expect(page.locator(".dev-testsummary.pass")).toBeVisible({ timeout: 30000 });
});
