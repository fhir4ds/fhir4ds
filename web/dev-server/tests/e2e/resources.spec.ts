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
  // Library binds terminology via `valueset "BPVS"` + IsBp uses in-valueset
  // over the CodeableConcept path (bare primitives like gender cannot
  // drive in-valueset — no system to match).
  writeFileSync(
    join(dir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "",
      'parameter "MinAge" Integer default 18',
      "",
      "valueset \"BPVS\": 'http://example.com/bp'",
      "",
      "// # %% [name: IsMale]",
      "define IsMale: Patient.gender = 'male'",
      "",
      "// # %% [name: IsBp]",
      'define IsBp: exists([Observation] O where O.code in "BPVS")',
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
    // Odd patients carry a LOINC-coded Observation so IsBp is true for them.
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

  server = spawn("/usr/bin/python3", ["-m", "fhir4ds.cli", "dev", dir, "--port", "18961", "--no-open"], {
    env: {
      PYTHONPATH: "/mnt/d/fhir4ds-devserver-v3-20261005",
      PATH: process.env.PATH ?? "",
    },
    stdio: "ignore",
    cwd: dir,
  });
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    try {
      const r = await fetch("http://127.0.0.1:18961/health");
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
    // The spawn is a direct python process; wait for exit so the port frees
    // before any later run can race a leftover server.
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
  await page.goto("http://127.0.0.1:18961/");
});

test("valueset pane renders, edits, and shows the stale banner", async ({ page }) => {
  await expect(page.locator(".dev-lib", { hasText: "vs1" })).toBeVisible({ timeout: 15000 });
  await page.locator(".dev-lib", { hasText: "vs1" }).click();
  await expect(page.locator(".dev-vspane")).toBeVisible();
  await expect(page.locator(".dev-vsrow")).toHaveCount(2); // head + 1 concept
  await expect(page.locator(".dev-vsurl")).toHaveText("http://example.com/bp");
  // used-by footer names the declaring library (FIX 1 binding)
  await expect(page.locator(".dev-vsusedby")).toContainText("Demographics.BPVS", { timeout: 10000 });
  // add a concept server-side
  await page.locator("button", { hasText: "+ concept" }).click();
  await expect(page.locator(".dev-vsrow")).toHaveCount(3, { timeout: 10000 });
  // FIX 2: visible stale state — banner names the remedy
  await expect(page.locator(".dev-stale").first()).toContainText("Restart kernel", { timeout: 10000 });
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
  await expect(patientSelect.locator("option", { hasText: "p1" })).toBeAttached({ timeout: 30000 });
  const opts = await patientSelect.locator("option").allTextContents();
  expect(opts.filter((o) => /^p\d$/.test(o)).length).toBe(6);
  // IsMale for p1 (male) should pass
  await page.locator("button", { hasText: "Run tests" }).click();
  await expect(page.locator(".dev-testsummary.pass")).toBeVisible({ timeout: 30000 });
});

// Muse FIX 1/2 blocker chain: valueset edit -> stale banner + Run disabled ->
// restart kernel -> IsBp test goes RED -> revert -> restart -> GREEN.
test("red-green chain: valueset edit flips IsBp after restart, reverts green", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected")).toHaveText("Demographics", { timeout: 15000 });
  // Wait for the boxes to render (IsBp box present).
  await expect(page.locator(".dev-box-title").filter({ hasText: "IsBp" })).toBeVisible({ timeout: 15000 });

  // Seed a green test first: IsBp for p1 (p1 has a coded Observation) = true.
  await expect(page.locator("button", { hasText: "+ case" })).toBeEnabled({ timeout: 15000 });
  await page.locator("button", { hasText: "+ case" }).click();
  const row = page.locator(".dev-testgrid .dev-vsrow").nth(1);
  await expect(row.locator("select").first().locator("option", { hasText: "p1" })).toBeAttached({ timeout: 30000 });
  await row.locator("select").first().selectOption("p1");
  // target_kind default is define; pick IsBp in the target select.
  // Row selects: [0]=patient, [1]=target_kind, [2]=target name, [3]=expect.
  const targetSelect = row.locator("select").nth(2);
  await targetSelect.selectOption({ label: "IsBp" });
  // expect select: default true — p1 should pass.
  await page.locator("button", { hasText: "Run tests" }).click();
  await expect(page.locator(".dev-testsummary.pass")).toBeVisible({ timeout: 30000 });

  // Edit the valueset: change the concept code so nothing matches anymore.
  await page.locator(".dev-lib", { hasText: "vs1" }).click();
  await expect(page.locator(".dev-vspane")).toBeVisible();
  const codeInput = page.locator(".dev-vsrow").nth(1).locator("input").nth(1);
  await codeInput.fill("9999-9");
  await page.locator(".dev-vsrow").nth(1).locator("button", { hasText: "Save" }).click();
  await expect(page.locator(".dev-stale").first()).toContainText("Restart kernel", { timeout: 10000 });

  // FIX 2: Run buttons are disabled while terminology is stale.
  await page.locator(".dev-lib", { hasText: "Demographics" }).click();
  await expect(page.locator(".dev-box-title").filter({ hasText: "IsBp" })).toBeVisible({ timeout: 15000 });
  await expect(page.locator(".dev-boxbar .dev-cellrun").first()).toBeDisabled();

  // Restart the kernel (reloads terminology), run the test again -> RED.
  await page.locator("button", { hasText: "Restart kernel" }).click();
  await expect(page.locator(".dev-kerneldot.idle")).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".dev-lib", { hasText: "Demographics" })).toBeVisible();
  await page.locator(".dev-lib", { hasText: "Demographics" }).click();
  await expect(page.locator(".dev-box-title").filter({ hasText: "IsBp" })).toBeVisible({ timeout: 15000 });
  await page.locator("button", { hasText: "Run tests" }).click();
  await expect(page.locator(".dev-testsummary.fail")).toBeVisible({ timeout: 30000 });

  // Revert the code edit, restart again -> GREEN.
  await page.locator(".dev-lib", { hasText: "vs1" }).click();
  await expect(page.locator(".dev-vspane")).toBeVisible();
  const reverted = page.locator(".dev-vsrow").nth(1).locator("input").nth(1);
  await reverted.fill("8480-6");
  await page.locator(".dev-vsrow").nth(1).locator("button", { hasText: "Save" }).click();
  await expect(page.locator(".dev-stale").first()).toContainText("Restart kernel", { timeout: 10000 });
  await page.locator("button", { hasText: "Restart kernel" }).click();
  await expect(page.locator(".dev-kerneldot.idle")).toBeVisible({ timeout: 30000 });
  await page.locator(".dev-lib", { hasText: "Demographics" }).click();
  await expect(page.locator(".dev-box-title").filter({ hasText: "IsBp" })).toBeVisible({ timeout: 15000 });
  await page.locator("button", { hasText: "Run tests" }).click();
  await expect(page.locator(".dev-testsummary.pass")).toBeVisible({ timeout: 30000 });
});

test("stale state propagates from API-originated edits (no pane interaction)", async ({ page }) => {
  await expect(page.locator(".dev-lib.selected")).toHaveText("Demographics", { timeout: 15000 });
  await expect(page.locator(".dev-box-title").filter({ hasText: "IsBp" })).toBeVisible({ timeout: 15000 });
  // No stale banner before the edit.
  await expect(page.locator(".dev-stale")).toHaveCount(0);

  // Edit the valueset via the API (not the pane) — the page must still learn.
  const response = await page.request.post("http://127.0.0.1:18961/api/valueset/edit", {
    data: {
      path: join(dir, "valuesets", "vs1.json"),
      edit: { action: "update", system: "http://loinc.org", code: "9999-9", old_code: "8480-6" },
    },
  });
  expect(response.ok()).toBeTruthy();

  // The banner + Run-disable arrive through the 'stale' WS event.
  await expect(page.locator(".dev-stale").first()).toContainText("Restart kernel", { timeout: 10000 });
  await expect(page.locator(".dev-boxbar .dev-cellrun").first()).toBeDisabled();

  // Revert via the API, restart, banner clears everywhere.
  const revert = await page.request.post("http://127.0.0.1:18961/api/valueset/edit", {
    data: {
      path: join(dir, "valuesets", "vs1.json"),
      edit: { action: "update", system: "http://loinc.org", code: "8480-6", old_code: "9999-9" },
    },
  });
  expect(revert.ok()).toBeTruthy();
  await page.locator("button", { hasText: "Restart kernel" }).click();
  await expect(page.locator(".dev-kerneldot.idle")).toBeVisible({ timeout: 30000 });
  await expect(page.locator(".dev-stale")).toHaveCount(0, { timeout: 10000 });
});
