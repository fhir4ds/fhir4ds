/**
 * Dev-server UI smoke (Playwright, chromium).
 *
 * Boots the real Python dev server (`fhir4ds dev`) on a scratch workspace
 * and asserts the three UX-polish surfaces: visible editor text, cell
 chips in the rail, and run producing visible inline output.
 */
import { test, expect } from "@playwright/test";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import fs from "fs";
import os from "os";

const PORT = 18901;
const BASE = `http://127.0.0.1:${PORT}`;

let server: ChildProcess | null = null;
let workdir: string | null = null;

test.beforeAll(async () => {
  workdir = fs.mkdtempSync(path.join(os.tmpdir(), "ds-e2e-"));
  fs.mkdirSync(path.join(workdir, "cql"), { recursive: true });
  fs.mkdirSync(path.join(workdir, "data"), { recursive: true });
  fs.writeFileSync(
    path.join(workdir, "cql", "Demographics.cql"),
    [
      "library Demographics version '1.0.0'",
      "using FHIR version '4.0.1'",
      "context Patient",
      "",
      "// # %%",
      "define IsMale: Patient.gender = 'male'",
      "",
    ].join("\n"),
  );
  fs.writeFileSync(
    path.join(workdir, "data", "patients.ndjson"),
    [
      JSON.stringify({ resourceType: "Patient", id: "p1", gender: "male", birthDate: "1974-12-25" }),
      JSON.stringify({ resourceType: "Patient", id: "p2", gender: "female", birthDate: "1990-01-01" }),
    ].join("\n"),
  );
  server = spawn(
    "/usr/bin/python3",
    ["-m", "fhir4ds.cli", "dev", workdir, "--port", String(PORT), "--no-open"],
    { env: { PATH: process.env.PATH, PYTHONPATH: "/mnt/d/fhir4ds-devserver-ux-20261003" }, stdio: "ignore" },
  );
  // Wait for /health.
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`${BASE}/health`);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("dev server did not become healthy");
});

test.afterAll(() => {
  server?.kill();
  if (workdir) fs.rmSync(workdir, { recursive: true, force: true });
});

test("editor shows library text with visible cells", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-lib.selected")).toHaveText(
    "Demographics",
    { timeout: 30_000 },
  );
  // Editor content is rendered by Monaco (token spans split words, so
  // assert on the container's full text rather than a phrase locator).
  await expect
    .poll(async () => {
      const t = await page.locator(".view-lines").textContent();
      return t?.includes("define") && t?.includes("IsMale");
    }, { timeout: 30_000 })
    .toBe(true);
  // Hint bar explains the model.
  await expect(page.getByText(/shared header/)).toBeVisible();
});

test("cell chip exists and run produces visible output", async ({ page }) => {
  await page.goto(BASE);
  await expect(page.locator(".dev-cellname")).toHaveText("IsMale", {
    timeout: 30_000,
  });
  await expect(page.locator(".dev-cellrow")).toHaveCount(1);
  const chip = page.locator(".dev-chip").first();
  await expect(chip).toBeVisible();
  // Run the cell via the rail button (mode defaults to strict cell).
  await page.locator(".dev-cellrun").first().click();
  // Inline result rows appear beneath the cell row in the rail.
  await expect(page.locator(".dev-cellresult-row").first()).toBeVisible({
    timeout: 60_000,
  });
  // The chip flips to ok after the run completes.
  await expect(page.locator(".dev-chip.ok").first()).toBeVisible({ timeout: 60_000 });
});
